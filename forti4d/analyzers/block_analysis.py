import csv
import sys
import os
from collections import Counter, defaultdict

try:
    from forti4d.analyzers.inventory import load_inventory
except ImportError:

    def load_inventory():
        return []


# =============================================================================
# MASTER DEFINITIONS (STRUCTURE GRAMMAR)
# =============================================================================

INIT_BUILDERS = {
    "IF_CONSTRUCT",
    "DO_CONSTRUCT",
    "DO_WHILE_CONSTRUCT",
    "SELECT_CONSTRUCT",
    "SELECT_TYPE_CONSTRUCT",
    "BLOCK_CONSTRUCT",
    "INTERFACE_BLOCK",
    "TYPE_DEFINITION",
    "ASSOCIATE_CONSTRUCT",
    "FORALL_CONSTRUCT",
    "WHERE_CONSTRUCT",
    "CRITICAL_CONSTRUCT",
}

# EXHAUSTIVE LIST OF CLOSINGS TO AVOID STACK OVERFLOW
END_BUILDERS = {
    "END_IF_STMT",
    "END_DO_STMT",
    "END_SELECT_STMT",
    "END_BLOCK_STMT",
    "END_ASSOCIATE_STMT",
    "END_FORALL_STMT",
    "END_WHERE_STMT",
    "END_CRITICAL_STMT",
    "END_INTERFACE_STMT",
    "END_TYPE_STMT",
    "END_FUNCTION_STMT",
    "END_SUBROUTINE_STMT",
    "END_MODULE_STMT",
    "END_PROGRAM_STMT",
}

KINDS_SPECIFICATION = {
    "VAR_DECLARATION",
    "PARAMETER_STMT",
    "USE_STMT",
    "IMPLICIT_STMT",
    "IMPORT_STMT",
    "NAMELIST_STMT",
    "DATA_STMT",
    "COMMON_STMT",
    "EQUIVALENCE_STMT",
    "INCLUDE_STMT",
    "EXTERNAL_STMT",
    "INTRINSIC_STMT",
}


def classify_intention(kind, content):
    kind = kind.strip()

    # 1. Major Structure
    if kind == "CONTAINS_STMT":
        return "STRUCTURE_CONTAINS"

    # 2. Specification (Declarations)
    if kind in KINDS_SPECIFICATION:
        return "SPECIFICATION"

    # 3. Flow Control (Hierarchy)
    if kind in INIT_BUILDERS:
        return "STRUCTURE_OPEN"
    if kind in END_BUILDERS:
        return "STRUCTURE_CLOSE"

    # 4. Executable Actions
    if kind in ("ALLOCATION_STMT", "DEALLOCATE_STMT", "NULLIFY_STMT"):
        return "MEMORY_MGMT"
    if kind == "IO_STMT":
        return "INPUT_OUTPUT"
    if kind == "ASSIGNMENT_STMT":
        return "CALCULATION"
    if kind == "CONTROL_STMT":
        return "FLOW_CONTROL"  # GOTO, CYCLE, EXIT, STOP

    # 5. Structure dividers (do not change depth but are visible)
    if kind in ("ELSE_STMT", "CASE_STMT"):
        return "BLOCK_DIVIDER"

    # 6. Visual noise
    # COMMENT: profiler produces "COMMENT", not "COMMENT_LINE"
    # Unit headers (SUBROUTINE, FUNCTION, etc.): structural boundaries, not logic
    if kind in (
        "BLANK_LINE",
        "COMMENT",
        "SUBROUTINE_UNIT",
        "FUNCTION_UNIT",
        "MODULE_UNIT",
        "PROGRAM_UNIT",
        "BLOCK_DATA_UNIT",
    ):
        return "WHITESPACE"

    return "OTHER"


# =============================================================================
# TOPOLOGICAL ANALYSIS ENGINE (STACK TRACKING)
# =============================================================================


def analyze_topology(lines):
    """
    Iterates over lines maintaining a depth stack and generating
    consolidated blocks by (Level, Type).
    """
    if not lines:
        return []

    blocks = []
    stack = []

    # Current block state
    # We start with a dummy block to simplify the loop logic
    curr_block = {"start": lines[0]["n"], "end": lines[0]["n"], "dp": 0, "type": "START", "detail": Counter()}

    for l in lines:
        itype = classify_intention(l["kind"], l["content"])

        # --- Depth Logic (Aligned Visualization) ---
        # We want:
        # IF (...)      -> Level 0
        #   CALCULATION -> Level 1
        # END IF        -> Level 0

        visual_dp = len(stack)

        if itype == "STRUCTURE_OPEN":
            # The opening is printed at the current level, then we go deeper
            stack.append(l["kind"])
            # dp_visual stays at len(stack)-1 (the level before entering)
            # But since we just appended, len is N+1. Subtract 1.
            visual_dp = len(stack) - 1

        elif itype == "STRUCTURE_CLOSE":
            # We go shallower first, then print at the destination level
            if stack:
                stack.pop()
            visual_dp = len(stack)

        else:
            # Normal content: at the current stack level
            visual_dp = len(stack)

        # --- Block Cut Logic ---
        # We cut when:
        # 1. Visual depth changes (entering/leaving a structure)
        # 2. Intent changes (e.g. from MEMORY to CALCULATION)
        # 3. It is a structure delimiter (to isolate them visually)

        change_dp = visual_dp != curr_block["dp"]
        change_type = itype != curr_block["type"] and itype != "WHITESPACE" and curr_block["type"] != "WHITESPACE"
        is_milestone = itype in ("STRUCTURE_OPEN", "STRUCTURE_CLOSE", "STRUCTURE_CONTAINS")

        if change_dp or change_type or is_milestone:
            # Save the previous block (if not the dummy initial)
            if curr_block["type"] != "START":
                blocks.append(curr_block)

            # Crear nuevo bloque
            new_type = itype if itype != "WHITESPACE" else curr_block["type"]

            # Rename for clarity in the report
            if itype == "STRUCTURE_OPEN":
                new_type = f"OPEN ({l['kind'].replace('_CONSTRUCT','').replace('_BLOCK','')})"
            if itype == "STRUCTURE_CLOSE":
                new_type = "CLOSE_STRUCTURE"

            curr_block = {"start": l["n"], "end": l["n"], "dp": visual_dp, "type": new_type, "detail": Counter()}

        # Acumular
        curr_block["end"] = l["n"]
        if itype not in ("WHITESPACE", "STRUCTURE_OPEN", "STRUCTURE_CLOSE"):
            curr_block["detail"][itype] += 1

    # Save the last block
    if curr_block["type"] != "START":
        blocks.append(curr_block)

    # --- Visual Consolidation Phase ---
    # Merge consecutive blocks that are identical in type and depth
    # (e.g. 3 lines of CALCULATION followed by 1 comment followed by 2 more CALCULATION)
    final_blocks = []
    if not blocks:
        return []

    curr = blocks[0]
    for b in blocks[1:]:
        ignoreable = b["type"] == "WHITESPACE"
        same_type = b["type"] == curr["type"] and b["dp"] == curr["dp"]

        if same_type:
            curr["end"] = b["end"]
            curr["detail"] += b["detail"]
        elif not ignoreable:
            final_blocks.append(curr)
            curr = b

    final_blocks.append(curr)

    return [b for b in final_blocks if b["type"] not in ("WHITESPACE", "START")]


def print_blocks(blocks, indent_base=""):
    print(f"{indent_base}{'LINES':>11} | DP | {'TREE':<28} {'STRUCTURE / INTENT':<22} | DETAIL")
    print(f"{indent_base}{'-'*95}")

    for b in blocks:
        # ASCII tree visualization
        # Level 0: ""
        # Level 1: "|_"
        # Level 2: "| |_"

        tree = ""
        if b["dp"] > 0:
            tree = "| " * (b["dp"] - 1) + "|_"

        # Clean detail format
        det = ", ".join([f"{k}:{v}" for k, v in b["detail"].most_common(3)])

        print(f"{indent_base}{b['start']:>5}-{b['end']:<5} | {b['dp']:>2} | {tree:<28} {b['type']:<22} | {det}")


# =============================================================================
# MAIN (Integration with Inventory)
# =============================================================================


def main(debug_file):
    if not os.path.exists(debug_file):
        return
    source_name = os.path.basename(debug_file).replace("_DEBUG.csv", "")

    # 1. Load metadata
    inv = load_inventory()
    units_map = {u["Name"]: u for u in inv if u["File"].lower() == source_name.lower()}

    # 2. Load raw lines
    lines_per_unit = defaultdict(list)
    lines_raw = []
    with open(debug_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lines_raw.append({"n": int(row["Line"]), "kind": row["Kind"], "content": row.get("Content", "")})

    # Assign lines to units
    for name, u in units_map.items():
        start, end = int(u["Start_Line"]), int(u["End_Line"])
        my_lines = [l for l in lines_raw if start <= l["n"] <= end]
        my_lines.sort(key=lambda x: x["n"])
        lines_per_unit[name] = my_lines

    # 3. Hierarchical Recursive Report
    visited = set()

    def _report(u_name, level=0):
        if u_name in visited:
            return
        visited.add(u_name)

        u = units_map.get(u_name)
        if not u:
            return

        lines = lines_per_unit[u_name]
        children = [h["Name"] for h in inv if h["Parent"] == u_name]
        children_objs = [units_map[h] for h in children if h in units_map]
        children_objs.sort(key=lambda x: int(x["Start_Line"]))

        indent = "    " * level
        print(f"\n{indent}>> UNIT: {u_name} ({u['Type']})")

        # Process segments between children (Gaps)
        cursor = 0
        total = len(lines)

        for h in children_objs:
            h_start = int(h["Start_Line"])
            h_end = int(h["End_Line"])

            # Segment before the child
            seg = []
            while cursor < total and lines[cursor]["n"] < h_start:
                seg.append(lines[cursor])
                cursor += 1

            if seg:
                blocks = analyze_topology(seg)
                print_blocks(blocks, indent + "  ")

            # Recurse into the child
            _report(h["Name"], level + 1)

            # Skip child lines in the parent
            while cursor < total and lines[cursor]["n"] <= h_end:
                cursor += 1

        # Final segment
        seg_final = []
        while cursor < total:
            seg_final.append(lines[cursor])
            cursor += 1

        if seg_final:
            blocks = analyze_topology(seg_final)
            print_blocks(blocks, indent + "  ")

    print(f"STRUCTURAL ANALYSIS: {source_name}")
    print("=" * 80)

    roots = [u for u in units_map.values() if u["Parent"] == "GLOBAL"]
    roots.sort(key=lambda x: int(x["Start_Line"]))

    for r in roots:
        _report(r["Name"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python block_analysis.py <DEBUG_file.csv>")
    else:
        main(sys.argv[1])
