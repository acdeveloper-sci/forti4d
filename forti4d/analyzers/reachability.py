import csv
import sys
from collections import defaultdict, deque
from pathlib import Path

from forti4d.analyzers.inventory import load_inventory
from forti4d import config

# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================


def load_graph(rows=None, results_dir=None):
    """
    Returns:
      graph      : dict  graph_node (str) -> set of destination graph_nodes (str)
      nodes_upper: dict  name.upper() -> name_in_graph  (for lookup)

    Graph nodes are in uppercase (subroutines/functions) or prefixed with
    'MAIN__file.f90' (for IMPLICIT-MAIN). Uses in-memory `rows` if given,
    otherwise reads dep_02_unit_graph.csv from results_dir.
    """
    graph = defaultdict(set)

    if rows is None:
        graph_csv = Path(results_dir) / "dep_02_unit_graph.csv"
        try:
            with open(graph_csv, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        except FileNotFoundError:
            print(f"ERROR: {graph_csv} not found")
            sys.exit(1)

    for row in rows:
        source = row.get("Source_Unit", "").strip()
        target = row.get("Target_Unit", "").strip()
        dp_type = row.get("Dep_Type", "").strip()
        if source and target and dp_type in ("CALL", "USE", "FUNC_CALL"):
            graph[source].add(target)

    # Case-insensitive index of all graph nodes
    all_index = set(graph.keys())
    for targets in graph.values():
        all_index |= targets
    nodes_upper = {n.upper(): n for n in all_index}

    return graph, nodes_upper


def node_in_graph(inventory_unit: dict, nodes_upper: dict) -> str:
    """
    Returns the graph node name corresponding to an inventory unit,
    or '' if it cannot be mapped.

    Rules:
      - IMPLICIT-MAIN  ->  "MAIN__<file>"  (same as dependencies.py)
      - other types    ->  name in uppercase (the graph uses caps)
    """
    utype = inventory_unit.get("Type", "")
    uname = inventory_unit.get("Name", "")
    file = inventory_unit.get("File", "")

    if utype == "IMPLICIT-MAIN":
        candidate = f"MAIN__{file}"
    else:
        candidate = uname.upper()

    # Verify that the node actually exists in the graph
    return nodes_upper.get(candidate.upper(), "")


# =============================================================================
# REACHABILITY ANALYSIS (BFS)
# =============================================================================


def calculate_reachability(graph: dict, seeds: list) -> dict:
    """
    BFS from each seed (graph node name).
    Returns visited: graph_node -> set of seeds that reach it.
    """
    visited = defaultdict(set)

    for seed in seeds:
        if seed not in graph and seed not in {d for ds in graph.values() for d in ds}:
            # isolated node: only reaches itself
            visited[seed].add(seed)
            continue

        tail = deque([seed])
        seen = {seed}
        while tail:
            current = tail.popleft()
            visited[current].add(seed)
            for neighbor in graph.get(current, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    tail.append(neighbor)

    return visited


# =============================================================================
# MAIN ANALYSIS
# =============================================================================


def analyze_reachability(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes. Returns None for report_reachability
    when there's a load error (no file written at all, same as the
    original); an empty list when there's no data to analyze (headers-only
    file is still written, same as the original)."""
    inputs = inputs or {}
    print("--- Reachability / Dead Code Analysis ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory(
            rows=inputs.get("inventory_report"), csv_path=Path(results_dir) / "inventory_report.csv"
        )
    except Exception as e:
        print(f"ERROR loading inventory: {e}")
        return {"report_reachability": None}

    if not inventory_list:
        print("Inventory is empty.")
        return {"report_reachability": []}

    # 2. Identify entry points
    eps_units = [
        u
        for u in inventory_list
        if u.get("Type") in ("PROGRAM", "IMPLICIT-MAIN") and u.get("Parent", "GLOBAL") == "GLOBAL"
    ]

    if not eps_units:
        print("No entry points found (PROGRAM / IMPLICIT-MAIN) — writing empty report.")
        return {"report_reachability": []}

    print(f"Entry points detected: {len(eps_units)}")

    # 3. Load graph with case-insensitive index
    graph, nodes_upper = load_graph(rows=inputs.get("dep_02_unit_graph"), results_dir=results_dir)
    print(f"Graph loaded: {sum(len(v) for v in graph.values())} edges " f"({len(graph)} source nodes)")

    # 4. Map entry points to graph nodes and prepare seeds for BFS
    #    ep_label: human-readable name of the entry point (for Via_Entradas column)
    seeds = []  # graph nodes used as seed
    ep_label = {}  # graph_node -> readable label

    for u in eps_units:
        node = node_in_graph(u, nodes_upper)
        label = u["Name"]
        if node:
            seeds.append(node)
            ep_label[node] = label
            print(f"  {label:25} -> node graph: {node}")
        else:
            # The entry point does not appear in the graph at all
            # (no outgoing or incoming dependencies recorded)
            seeds.append(label)  # we use the name inventory
            ep_label[label] = label
            print(f"  {label:25} -> (no node in graph)")

    # 5. BFS
    visited = calculate_reachability(graph, seeds)

    # 6. Build reverse index: graph_node -> entry point labels
    #    To convert visited nodes to human-readable labels
    def ep_labels_for(graph_node: str) -> list:
        return sorted(ep_label.get(ep, ep) for ep in visited.get(graph_node, set()))

    # 7. Classify all inventory units
    #
    # Status logic:
    #   ENTRY_POINT    : is an entry point
    #   REACHABLE      : appears in visited (via graph node or inventory name)
    #                    or its parent is reachable/entry (transitive reachability)
    #   UNREACHABLE    : none of the above
    #
    # The inventory may contain lower/mixed-case names; the graph uses
    # uppercase.  We build an upper(node) -> node index for lookup.
    visited_upper = {k.upper(): k for k in visited}

    def is_reached(name_inv: str) -> str:
        """Returns the graph node if the inventory name is visited."""
        return visited_upper.get(name_inv.upper(), "")

    rows = []
    count = {"REACHABLE": 0, "UNREACHABLE": 0, "ENTRY_POINT": 0}

    for u in inventory_list:
        uname = u["Name"]
        utype = u.get("Type", "UNKNOWN")
        parent = u.get("Parent", "GLOBAL")
        file = u.get("File", "")

        # Compute the equivalent graph node for this unit
        node_g = node_in_graph(u, nodes_upper)

        # Is it an entry point?
        if u in eps_units:
            status = "ENTRY_POINT"
            way = uname
            reason = "Entry point (PROGRAM/IMPLICIT-MAIN)"

        # Does it appear in visited via its graph node?
        elif node_g and node_g in visited:
            status = "REACHABLE"
            way = "; ".join(ep_labels_for(node_g))
            reason = ""

        # Does its direct name appear in visited?
        elif is_reached(uname):
            node_enc = is_reached(uname)
            status = "REACHABLE"
            way = "; ".join(ep_labels_for(node_enc))
            reason = ""

        # Is its parent (container module) reachable or an entry point?
        elif parent != "GLOBAL":
            parent_node = node_in_graph({"Type": "MODULE", "Name": parent, "File": ""}, nodes_upper) or parent
            if parent_node in visited or is_reached(parent):
                node_parent = parent_node if parent_node in visited else is_reached(parent)
                status = "REACHABLE"
                way = "; ".join(ep_labels_for(node_parent))
                reason = f"Contained in reachable module: {parent}"
            elif parent in [u2["Name"] for u2 in eps_units]:
                status = "REACHABLE"
                way = parent
                reason = f"Contained in entry point: {parent}"
            else:
                status = "UNREACHABLE"
                way = ""
                reason = f"Container module not reached: {parent}"
        else:
            status = "UNREACHABLE"
            way = ""
            node_in_g = node_g or uname.upper()
            if node_in_g in {k for k in graph} | {d for ds in graph.values() for d in ds}:
                reason = "In graph but not reachable from any entry point"
            else:
                reason = "Does not appear in the dependency graph"

        count[status] += 1
        rows.append(
            {
                "File": file,
                "Unit": uname,
                "Type": utype,
                "Parent": parent,
                "Status": status,
                "Via_Entry_Points": way,
                "Reason": reason,
            }
        )

    # 8. Sort: UNREACHABLE first, then ENTRY_POINT, then REACHABLE
    order = {"UNREACHABLE": 0, "ENTRY_POINT": 1, "REACHABLE": 2}
    rows.sort(key=lambda x: (order[x["Status"]], x["File"].lower(), x["Unit"].lower()))

    return {"report_reachability": rows}


def write_reachability(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    rows = data["report_reachability"]
    if rows is None:
        return  # load error — nothing written at all, same as before

    columns = ["File", "Unit", "Type", "Parent", "Status", "Via_Entry_Points", "Reason"]
    output_file = Path(results_dir) / "report_reachability.csv"
    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    if not rows:
        return  # empty inventory / no entry points — headers-only, no summary

    # 10. Console summary
    count = {"REACHABLE": 0, "UNREACHABLE": 0, "ENTRY_POINT": 0}
    for r in rows:
        count[r["Status"]] += 1

    total = len(rows)
    n_dead = count["UNREACHABLE"]
    n_live = count["REACHABLE"]
    n_ep = count["ENTRY_POINT"]

    print(f"\nTotal units analyzed : {total}")
    print(f"  ENTRY_POINT        : {n_ep}")
    print(f"  REACHABLE          : {n_live}")
    print(f"  UNREACHABLE (dead) : {n_dead}  ({n_dead/total*100:.1f}%)")

    if n_dead > 0:
        print("\nUnits not reachable from any entry point:")
        deads = [r for r in rows if r["Status"] == "UNREACHABLE"]
        # Group by file for readability
        current_file = None
        for r in deads:
            if r["File"] != current_file:
                current_file = r["File"]
                print(f"\n  [{current_file}]")
            type_str = f"[{r['Type']}]"
            parent_str = f" (in {r['Parent']})" if r["Parent"] != "GLOBAL" else ""
            print(f"    {r['Unit']:30} {type_str}{parent_str}")

    print(f"\nGenerated: {output_file}")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_reachability(source_dir, results_dir, inputs=inputs)
    write_reachability(results_dir, data)
    return data


if __name__ == "__main__":
    main()
