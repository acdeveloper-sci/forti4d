"""
visual_graph.py
Generates DOT (Graphviz) files of the call graph for the Fortran corpus.

Usage:
  python visual_graph.py                        # full graph + simplified (all EPs)
  python visual_graph.py --entry mcdes          # only the subgraph for mcdes
  python visual_graph.py --entry util0 util1    # subgraph for two executables
  python visual_graph.py --list                 # list available entry points
  python visual_graph.py --use                  # include USE edges (modules)

Rendering (requires Graphviz):
  dot -Tpng graph_mcdes.dot        -o graph_mcdes.png
  dot -Tsvg graph_complete.dot     -o graph_complete.svg
  dot -Tpdf graph_simple.dot       -o graph_simple.pdf
"""

import argparse
import csv
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================
from forti4d.config import RESULTS_PATH

GRAPH_CSV = RESULTS_PATH / "dep_02_unit_graph.csv"
CONSOL_PATH = RESULTS_PATH / "report_consolidated.csv"

# Base colors
COLOR_ENTRY = "#4472C4"  # blue   — selected entry point
COLOR_REACH = "#70AD47"  # green  — reachable
COLOR_NO_REACH = "#A6A6A6"  # grey   — dead code
COLOR_SHARED = "#FFD966"  # yellow — reachable from multiple EPs
COLOR_UNKNOWN = "#F2F2F2"  # light grey — no data in consolidated

# Palette for multiple entry points (up to 8)
PALETTE_EP = [
    "#4472C4",  # blue
    "#ED7D31",  # orange
    "#C00000",  # red
    "#7030A0",  # purple
    "#00B050",  # dark green
    "#00B0F0",  # sky blue
    "#9E480E",  # brown
    "#FF69B4",  # pink
]

# Edge styles
EDGE_STYLE = {
    "CALL": 'style=solid color="#333333"',
    "FUNC_CALL": 'style=solid color="#1F7A1F"',
    "USE": 'style=dashed color="#2E74B5" penwidth=0.8',
}

# Shapes by unit type
SHAPE = {
    "PROGRAM": "doubleoctagon",
    "IMPLICIT-MAIN": "doubleoctagon",
    "MODULE": "hexagon",
    "SUBROUTINE": "box",
    "FUNCTION": "ellipse",
    "BLOCK_DATA": "diamond",
}
SHAPE_DEFAULT = "box"


# =============================================================================
# DATA LOADING
# =============================================================================


def load_consolidated() -> dict:
    """dict: name.upper() -> consolidated row."""
    if not CONSOL_PATH.exists():
        return {}
    meta = {}
    with open(CONSOL_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            n = row.get("Unit", "").strip()
            if n:
                meta[n.upper()] = row
    return meta


def load_raw_graph() -> list:
    """Returns rows from dep_02_unit_graph.csv."""
    with open(GRAPH_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def friendly_name(node: str, meta: dict) -> str:
    """
    MAIN__chcump.f90 → chcump   (IMPLICIT-MAIN)
    GEOLEC           → GEOLEC   (no change)
    """
    if node.startswith("MAIN__"):
        file = node[6:]
        no_ext = re.sub(r"\.\w+$", "", file)
        if no_ext.upper() in meta:
            return meta[no_ext.upper()]["Unit"]
        return no_ext
    return node


def build_friendly_graph(raw_edges: list, meta: dict) -> list:
    """
    Resolves MAIN names and returns a list of
    (origin_inv, target_inv, type_dep).
    """
    result = []
    for e in raw_edges:
        source = friendly_name(e["Source_Unit"], meta)
        target = friendly_name(e["Target_Unit"], meta)
        result.append((source, target, e["Dep_Type"]))
    return result


# =============================================================================
# BFS FROM SELECTED ENTRY POINTS
# =============================================================================


def available_entry_points(meta: dict) -> list:
    """List of entry point names (State=ENTRANCE)."""
    return sorted(row["Unit"] for row in meta.values() if row.get("Status") == "ENTRY_POINT")


def bfs_from(seed: str, adjacency: dict) -> set:
    """BFS on the friendly graph. Returns set of reached nodes."""
    visited = {seed}
    tail = deque([seed])
    while tail:
        current = tail.popleft()
        for neighbor in adjacency.get(current.upper(), []):
            if neighbor.upper() not in {v.upper() for v in visited}:
                visited.add(neighbor)
                tail.append(neighbor)
    return visited


def calculate_scope(entry_names: list, edges_friendly: list) -> dict:
    """
    For each entry point in entry_names, calculate the set of nodes
    reached by BFS.

    Returns dict: node_name -> set of entry points reached by it.
    """
    # Build adjacency map: origin.upper() -> [destination, ...]
    adjacency = defaultdict(list)
    for source, target, _ in edges_friendly:
        adjacency[source.upper()].append(target)

    scope_by_ep = {}  # ep -> set of nodes
    for ep in entry_names:
        scope_by_ep[ep] = bfs_from(ep, adjacency)

    # Invert: node -> set of EPs that reach it
    node_eps = defaultdict(set)
    for ep, nodes in scope_by_ep.items():
        for n in nodes:
            node_eps[n].add(ep)

    return dict(node_eps)


# =============================================================================
# COLOURS
# =============================================================================


def assign_colors_ep(entry_names: list) -> dict:
    """dict: ep_name -> color_hex (for the multi-EP color palette)."""
    return {ep: PALETTE_EP[i % len(PALETTE_EP)] for i, ep in enumerate(entry_names)}


def node_color(name_inv: str, meta: dict, node_eps: dict, colors_ep: dict, entry_names_sel: list) -> tuple:
    """
    Returns (fillcolor, fontcolor) for the node.

    Logic:
      - If it is one of the selected entry points → EP color
      - If reached by a single EP → that EP's color (lighter shade)
      - If reached by multiple EPs → COLOR_SHARED
      - If not reached (dead code in filtered context) → COLOR_NO_REACH
      - No data → COLOR_UNKNOWN
    """
    eps_that_reach = node_eps.get(name_inv, set()) & set(entry_names_sel)
    row = meta.get(name_inv.upper(), {})
    type_ = row.get("Type", "")
    is_ep = name_inv in entry_names_sel

    if is_ep:
        color = colors_ep.get(name_inv, COLOR_ENTRY)
        return color, "#FFFFFF"

    if not eps_that_reach:
        return COLOR_NO_REACH, "#000000"

    if len(eps_that_reach) == 1:
        # Same EP color but lighter: use standard green
        # if there is a single selected EP, or the EP color in multi-EP mode
        if len(entry_names_sel) == 1:
            return COLOR_REACH, "#000000"
        else:
            return COLOR_REACH, "#000000"

    # Reached by several EPs
    return COLOR_SHARED, "#000000"


# =============================================================================
# DOT GENERATION
# =============================================================================


def dot_id(name: str) -> str:
    return '"' + name.replace('"', '\\"') + '"'


def generate_dot(
    edges_friendly: list,
    meta: dict,
    allowed_nodes: set,
    node_eps: dict,
    colors_ep: dict,
    entry_names_sel: list,
    include_use: bool,
    title: str,
) -> str:

    ok_types = {"CALL", "FUNC_CALL"}
    if include_use:
        ok_types.add("USE")

    # Filter edges
    edges = [(o, d, t) for o, d, t in edges_friendly if t in ok_types and o in allowed_nodes and d in allowed_nodes]

    # Nodes that appear on any edge + selected entry points
    used_nodes = set(entry_names_sel)
    for o, d, _ in edges:
        used_nodes.add(o)
        used_nodes.add(d)
    used_nodes &= allowed_nodes

    # Group by file
    file_nodes = defaultdict(list)
    for n in sorted(used_nodes):
        row = meta.get(n.upper(), {})
        file = row.get("File", "NO_FILE")
        file_nodes[file].append(n)

    lines = []
    lines.append(f"digraph {title} {{")
    lines.append("  rankdir=LR;")
    lines.append("  compound=true;")
    lines.append('  graph [fontname="Helvetica" fontsize=10 bgcolor="#F8F8F8"];')
    lines.append('  node  [fontname="Helvetica"];')
    lines.append('  edge  [fontname="Helvetica" fontsize=8 arrowsize=0.7];')
    lines.append("")

    # Dynamic legend
    lines.append("  subgraph cluster_legend {")
    lines.append('    label="Legend" fontsize=9 style=dotted rank=sink;')
    if len(entry_names_sel) == 1:
        ep = entry_names_sel[0]
        c = colors_ep[ep]
        lines.append(
            f'    _ep  [label="{ep}" shape=doubleoctagon style=filled fillcolor="{c}" fontcolor=white fontsize=8];'
        )
        lines.append(
            f'    _alc [label="Reachable"  shape=box style=filled fillcolor="{COLOR_REACH}"    fontcolor=black fontsize=8];'
        )
        lines.append(f'    _ep -> _alc [style=solid label="CALL" fontsize=7];')
    else:
        for ep, c in colors_ep.items():
            safe = ep.replace('"', '\\"').replace("-", "_").replace(" ", "_")
            lines.append(
                f'    _ep_{safe} [label="{ep}" shape=doubleoctagon style=filled fillcolor="{c}" fontcolor=white fontsize=8];'
            )
        lines.append(
            f'    _comp [label="Shared"    shape=box style=filled fillcolor="{COLOR_SHARED}" fontcolor=black fontsize=8];'
        )
        lines.append(
            f'    _alc  [label="Reachable" shape=box style=filled fillcolor="{COLOR_REACH}"  fontcolor=black fontsize=8];'
        )
    lines.append("  }")
    lines.append("")

    # Clusters per file
    for cid, file in enumerate(sorted(file_nodes.keys())):
        nodes = sorted(file_nodes[file])
        label_file = file.replace('"', '\\"')
        lines.append(f"  subgraph cluster_{cid} {{")
        lines.append(f'    label="{label_file}" fontsize=8 style=rounded color="#CCCCCC";')
        for n in nodes:
            row = meta.get(n.upper(), {})
            type_ = row.get("Type", "")
            cc = row.get("CC", "")
            fan_in = row.get("Fan_In", "")
            shape = SHAPE.get(type_, SHAPE_DEFAULT)

            fillcolor, fontcolor = node_color(n, meta, node_eps, colors_ep, entry_names_sel)

            parts = [n]
            if cc:
                parts.append(f"CC={cc}")
            if fan_in:
                parts.append(f"Fi={fan_in}")
            label = r"\n".join(parts)
            tooltip = f"{type_} | {file}" if type_ else file

            lines.append(
                f"    {dot_id(n)} [shape={shape} style=filled "
                f'fillcolor="{fillcolor}" fontcolor="{fontcolor}" '
                f'fontsize=9 label="{label}" tooltip="{tooltip}"];'
            )
        lines.append("  }")

    lines.append("")
    lines.append("  // --- Aristas ---")
    for source, target, dep_type in sorted(set(edges)):
        style = EDGE_STYLE.get(dep_type, "")
        lines.append(f"  {dot_id(source)} -> {dot_id(target)} [{style}];")

    lines.append("}")
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Generates DOT graphs from the Fortran call graph.")
    parser.add_argument(
        "--entry",
        nargs="+",
        metavar="NAME",
        help="Entry point(s) to graph. Without this flag, it generates the complete graph.",
    )
    parser.add_argument("--list", action="store_true", help="List available entry points and exit.")
    parser.add_argument(
        "--use", action="store_true", help="Include USE edges (module dependencies). Default: CALL/FUNC_CALL only."
    )
    args = parser.parse_args()

    if not GRAPH_CSV.exists():
        print(f"ERROR: Not found {GRAPH_CSV}")
        sys.exit(1)

    meta = load_consolidated()
    raw_edges = load_raw_graph()
    edges_am = build_friendly_graph(raw_edges, meta)
    available_eps = available_entry_points(meta)

    # --list
    if args.list:
        print("Entry points available:")
        for ep in available_eps:
            row = meta.get(ep.upper(), {})
            type_ = row.get("Type", "")
            file = row.get("File", "")
            print(f"  {ep:25}  [{type_}]  {file}")
        return

    include_use = args.use

    # -------------------------------------------------------------------------
    # Filtering mode: --entry specified
    # -------------------------------------------------------------------------
    if args.entry:
        # Resolve names (case-insensitive)
        ep_upper = {ep.upper(): ep for ep in available_eps}
        entry_sel = []
        for name in args.entry:
            if name.upper() in ep_upper:
                entry_sel.append(ep_upper[name.upper()])
            else:
                print(f"NOTICE: '{name}' is not a known entry point. Ignored.")

        if not entry_sel:
            print("ERROR: None of the indicated entry points exist.")
            print("Use --list to see the available ones.")
            sys.exit(1)

        print(f"Selected entry points: {', '.join(entry_sel)}")

        # BFS from the selected
        node_eps = calculate_scope(entry_sel, edges_am)
        colors_ep = assign_colors_ep(entry_sel)

        # Allowed nodes = all nodes reached from any of the EPs
        nodes_perm = set(node_eps.keys())

        # Output file name
        safe_names = "_".join(re.sub(r"[^a-zA-Z0-9]", "", ep) for ep in entry_sel)
        output = RESULTS_PATH / f"graph_{safe_names}.dot"

        title = "CallGraph_" + safe_names
        dot = generate_dot(
            edges_am,
            meta,
            allowed_nodes=nodes_perm,
            node_eps=node_eps,
            colors_ep=colors_ep,
            entry_names_sel=entry_sel,
            include_use=include_use,
            title=title,
        )
        RESULTS_PATH.mkdir(parents=True, exist_ok=True)
        output.write_text(dot, encoding="utf-8")
        print(f"Generated: {output}  ({len(nodes_perm)} nodes)")
        print(f"\nTo render:")
        stem = output.stem
        print(f"  dot -Tpng {output} -o {RESULTS_PATH / (stem + '.png')}")
        print(f"  dot -Tsvg {output} -o {RESULTS_PATH / (stem + '.svg')}")

    # -------------------------------------------------------------------------
    # Full mode: without --entry
    # -------------------------------------------------------------------------
    else:
        n_call = sum(1 for e in raw_edges if e["Dep_Type"] == "CALL")
        n_func = sum(1 for e in raw_edges if e["Dep_Type"] == "FUNC_CALL")
        n_use = sum(1 for e in raw_edges if e["Dep_Type"] == "USE")
        print(f"Graph: {len(meta)} nodes  |  {n_call} CALL  {n_func} FUNC_CALL  {n_use} USE")

        node_eps = calculate_scope(available_eps, edges_am)
        colors_ep = assign_colors_ep(available_eps)

        # Complete graph: all nodes of the consolidated
        all_nodes = set(row["Unit"] for row in meta.values())

        dot_full = generate_dot(
            edges_am,
            meta,
            allowed_nodes=all_nodes,
            node_eps=node_eps,
            colors_ep=colors_ep,
            entry_names_sel=available_eps,
            include_use=True,
            title="CallGraph_Complete",
        )
        RESULTS_PATH.mkdir(parents=True, exist_ok=True)
        (RESULTS_PATH / "graph_complete.dot").write_text(dot_full, encoding="utf-8")
        print(f"Generated:{RESULTS_PATH / 'graph_complete.dot'}")

        # Simple graph: only reachable, no USE
        achievable = {n for n, eps in node_eps.items() if eps} | set(available_eps)

        dot_simple = generate_dot(
            edges_am,
            meta,
            allowed_nodes=achievable,
            node_eps=node_eps,
            colors_ep=colors_ep,
            entry_names_sel=available_eps,
            include_use=False,
            title="CallGraph_Simple",
        )
        (RESULTS_PATH / "graph_simple.dot").write_text(dot_simple, encoding="utf-8")
        print(f"Generated:{RESULTS_PATH / 'graph_simple.dot'}")

        print()
        print("Torender:")
        print("  dot -Tpng  graph_simple.dot   -o graph_simple.png")
        print("  dot -Tsvg  graph_complete.dot -o graph_complete.svg")
        print()
        print("For a specific executable:")
        print("  python visual_graph.py --list")
        print("  python visual_graph.py --entry mcdes")


if __name__ == "__main__":
    main()
