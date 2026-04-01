import csv
import re
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventory import load_inventory
from forti4d.config import RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
AUDIT_PATH = RESULTS_PATH / "audit"
CSV_OUTPUT = RESULTS_PATH / "equivalences.csv"

COLS = [
    "File",
    "Unit",
    "Unit_Type",
    "Group_ID",
    "Position",
    "Var_Name",
    "N_Members",
    "Stmt_Lines",
]


# =============================================================================
# UNION-FIND
# =============================================================================


class UnionFind:
    """
    Union-Find with path compression to compute connected components.
    Nodes are strings (uppercase variable names).
    """

    def __init__(self):
        self._parent = {}

    def _ensure(self, x):
        if x not in self._parent:
            self._parent[x] = x

    def find(self, x):
        self._ensure(x)
        while self._parent[x] != x:
            # Path compression (halving)
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x, y):
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[rx] = ry

    def components(self):
        """
        Returns dict {representative: [sorted members]}.
        Each key is the canonical root of the component.
        """
        groups = defaultdict(list)
        for node in self._parent:
            groups[self.find(node)].append(node)
        return {rep: sorted(members) for rep, members in groups.items()}


# =============================================================================
# PARSING
# =============================================================================


def _extract_name(ref):
    """
    From a variable reference (which may include a subscript),
    extracts just the name: 'A(1)' → 'A', 'POINT' → 'POINT'.
    """
    ref = ref.strip()
    m = re.match(r"^(\w+)", ref)
    return m.group(1).upper() if m else ""


def _split_top(s):
    """
    Splits s by commas respecting nested parentheses.
    Same as split_list in symbols.py — duplicated to avoid a dependency.
    """
    parts, current, depth = [], [], 0
    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def parse_equivalence(content):
    """
    Extracts all groups from an EQUIVALENCE statement.
    Example: 'EQUIVALENCE (A,B(1)), (X,Y,Z)' → [['A','B'], ['X','Y','Z']]
    Each inner group has >= 2 variables (groups of 1 are ignored).
    """
    # Strip EQUIVALENCE keyword
    rest = re.sub(r"^\s*equivalence\s*", "", content.strip(), flags=re.IGNORECASE)

    groups: list[list[str]] = []
    i = 0
    while i < len(rest):
        if rest[i] == "(":
            # Find the balanced closing parenthesis
            j, depth = i + 1, 1
            while j < len(rest) and depth > 0:
                if rest[j] == "(":
                    depth += 1
                elif rest[j] == ")":
                    depth -= 1
                j += 1
            inner = rest[i + 1 : j - 1]
            refs = _split_top(inner)
            names = [_extract_name(r) for r in refs]
            names = [n for n in names if n]
            if len(names) >= 2:
                groups.append(names)
            i = j
        else:
            i += 1
    return groups


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================


def scope_resolver(n_line: int, units_on_file: list) -> tuple:
    candidates = [u for u in units_on_file if u["Start_Line"] <= n_line <= u["End_Line"]]
    if not candidates:
        return "GLOBAL", "FILE_SCOPE"
    u = max(candidates, key=lambda u: u["Start_Line"])
    return u["Name"], u.get("Type", "UNKNOWN")


# =============================================================================
# MAIN ANALYSIS
# =============================================================================


def extract_equivalences():
    print("--- Equivalences Extraction ---")

    # 1. Inventory
    try:
        inventory_list = load_inventory()
    except Exception as e:
        print(f"ERROR loading inventory: {e}")
        return

    if not inventory_list:
        print("Inventory is empty.")
        return

    units_map = defaultdict(list)
    for u in inventory_list:
        file = u.get("File", "").strip()
        if not file:
            continue
        try:
            u["Start_Line"] = int(u["Start_Line"])
            u["End_Line"] = int(u["End_Line"])
        except (ValueError, KeyError):
            u["Start_Line"] = 0
            u["End_Line"] = 0
        units_map[file].append(u)

    rows = []
    total_n_groups = 0
    sorted_files = sorted(units_map.keys(), key=str.lower)

    # 2. Per file: collect EQUIVALENCE_STMT by (scope, unit_type)
    for file_name in sorted_files:
        debug_file = AUDIT_PATH / f"{file_name}_DEBUG.csv"
        if not debug_file.exists():
            continue

        units_on_file = sorted(units_map[file_name], key=lambda u: u["Start_Line"])

        # Accumulate statements per unit
        stmts_per_unit: dict[tuple, list] = defaultdict(list)

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if row.get("Kind") != "EQUIVALENCE_STMT":
                    continue
                try:
                    n_line = int(row["Line"])
                except (ValueError, KeyError):
                    continue
                scope, unit_type = scope_resolver(n_line, units_on_file)
                stmts_per_unit[(scope, unit_type)].append((n_line, row.get("Content", "")))

        # 3. Per unit: union-find over all its EQUIVALENCE statements
        for (scope, unit_type), stmts in stmts_per_unit.items():
            uf = UnionFind()
            # var → set of lines where it appears
            var_lines: dict[str, set] = defaultdict(set)

            for n_line, content in stmts:
                stmt_groups = parse_equivalence(content)
                for group in stmt_groups:
                    # Record line for each variable in the group
                    for var in group:
                        var_lines[var].add(n_line)
                    # Unite all variables in the group
                    for i in range(1, len(group)):
                        uf.union(group[0], group[i])

            # 4. Extract connected components and emit rows
            components = uf.components()
            # Sort components by first member for deterministic ID
            ordered_groups = sorted(components.values(), key=lambda g: g[0])

            for id_group, members in enumerate(ordered_groups, 1):
                n_members = len(members)
                # Lines of all statements that define this group
                group_lines = sorted({ln for var in members for ln in var_lines.get(var, [])})
                lines_str = ";".join(str(l) for l in group_lines)

                for position, var_name in enumerate(members, 1):
                    rows.append(
                        {
                            "File": file_name,
                            "Unit": scope,
                            "Unit_Type": unit_type,
                            "Group_ID": id_group,
                            "Position": position,
                            "Var_Name": var_name,
                            "N_Members": n_members,
                            "Stmt_Lines": lines_str,
                        }
                    )

                total_n_groups += 1

    # 5. Export
    _write_csv(CSV_OUTPUT, rows, COLS)

    n_files = len({f["File"] for f in rows})
    n_units = len({(f["File"], f["Unit"]) for f in rows})
    print(f"Files with EQUIVALENCE   : {n_files}")
    print(f"Units with EQUIVALENCE   : {n_units}")
    print(f"Aliasing groups          : {total_n_groups}")
    print(f"Variables in groups      : {len(rows)}")
    print()
    print(f"Generated:")
    print(f"  {CSV_OUTPUT}")


# =============================================================================
# HELPERS
# =============================================================================


def _write_csv(filepath: Path, rows: list, columns: list):
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  → {filepath.name}  ({len(rows)} rows)")


# =============================================================================
# ENTRY POINT
# =============================================================================


def main():
    extract_equivalences()


if __name__ == "__main__":
    main()
