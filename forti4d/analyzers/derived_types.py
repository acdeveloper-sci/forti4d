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
DEFS_OUTPUTS = RESULTS_PATH / "type_definitions.csv"
COMPS_OUTPUTS = RESULTS_PATH / "type_components.csv"

TYPES_COLS = [
    "File",
    "Unit",
    "Unit_Type",
    "Start_Line",
    "End_Line",
    "Type_Name",
    "N_Components",
]
COMPS_COLS = [
    "File",
    "Type_Name",
    "Line",
    "Position",
    "Comp_Name",
    "Fortran_Type",
    "Kind_Param",
    "Dimension",
    "Attributes",
]


# =============================================================================
# EXTRACTION PATTERNS (local)
# =============================================================================

# Definition name: TYPE name  or  TYPE :: name  (F90)
RE_NAME_TYPE = re.compile(r"^\s*type\b\s*(?:::\s*)?(\w+)", re.IGNORECASE)

# Close TYPE block: END TYPE [optional_name]
RE_END_TYPE = re.compile(r"^\s*end\s*type\b", re.IGNORECASE)

# F90 declaration with ::
RE_DECL_F90 = re.compile(r"^(.*?)\s*::\s*(.+)$")

# F77 declaration without ::: base type + list
RE_DECL_F77 = re.compile(
    r"^\s*(integer|real|double\s+precision|complex|logical|character|byte)"
    r"(\s*\*\s*\d+|\s*\(\s*(?:(?:kind|len)\s*=\s*)?\w+\s*\))?\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# Simple attributes in F90 prefix
RE_ATTR_DIM = re.compile(r"\bdimension\s*\(([^)]+)\)", re.IGNORECASE)
RE_ATTR_SIMPLES = re.compile(
    r"\b(allocatable|pointer|save|target|volatile|private|public|protected)\b",
    re.IGNORECASE,
)


# =============================================================================
# PARSING FUNCTIONS
# =============================================================================


def extract_kind(type_str: str) -> str:
    """Extracts KIND/LEN from a type specifier, handling nested parentheses."""
    m_star = re.search(r"\*\s*(\d+)", type_str)
    if m_star and "(" not in type_str[: m_star.start()].lstrip():
        return "*" + m_star.group(1)

    i = type_str.find("(")
    if i == -1:
        return ""

    depth, content = 0, []
    for ch in type_str[i + 1 :]:
        if ch == "(":
            depth += 1
            content.append(ch)
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
            content.append(ch)
        else:
            content.append(ch)

    raw = "".join(content).strip()
    raw = re.sub(r"^(?:kind|len)\s*=\s*", "", raw, flags=re.IGNORECASE)
    return raw


def split_list(s: str) -> list:
    """Splits by commas respecting nested parentheses."""
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


def parse_component(content: str, n_line: int, init_pos: int) -> list:
    """
    Parses a VAR_DECLARATION line inside a TYPE body.
    Returns a list of dicts with component fields.
    """
    rows = []

    if "::" in content:
        # F90 with ::
        m = RE_DECL_F90.match(content.strip())
        if not m:
            return []
        prefix = m.group(1).strip()
        list_str = m.group(2).strip()

        # Extract base type from prefix
        parts_pref = split_list(prefix)
        base_type = ""
        base_kind = ""
        base_dim = ""
        attrs = []

        if parts_pref:
            type_str = parts_pref[0].strip()
            m_base = re.match(r"(\w+(?:\s+\w+)*)", type_str, re.IGNORECASE)
            base_type = m_base.group(1).upper() if m_base else ""
            base_kind = extract_kind(type_str)

        for attr in parts_pref[1:]:
            m_dim = RE_ATTR_DIM.search(attr)
            if m_dim:
                base_dim = m_dim.group(1)
                attrs.append(f"DIMENSION({m_dim.group(1)})")
                continue
            m_s = RE_ATTR_SIMPLES.match(attr.strip())
            if m_s:
                attrs.append(attr.strip().upper())

        for entry in split_list(list_str):
            row = _parse_entry(entry, base_type, base_kind, base_dim, attrs, n_line, init_pos + len(rows))
            if row:
                rows.append(row)
    else:
        # F77 without ::
        m = RE_DECL_F77.match(content.strip())
        if not m:
            return []
        base_type = re.sub(r"\s+", " ", m.group(1).upper())
        base_kind = extract_kind(m.group(1) + (m.group(2) or ""))
        list_str = m.group(3).strip()

        for entry in split_list(list_str):
            row = _parse_entry(entry, base_type, base_kind, "", [], n_line, init_pos + len(rows))
            if row:
                rows.append(row)

    return rows


def _parse_entry(entry: str, etype: str, kind: str, dim: str, attrs: list, n_line: int, position: int) -> dict:
    """Extracts name, dimension, and info from an individual list entry."""
    entry = entry.strip()
    # Strip initial value (components with initializers: comp = value)
    if "=" in entry:
        entry = entry[: entry.index("=")].strip()

    name = ""
    dim_local = dim

    m_star = re.match(r"^(\w+)\s*\*\s*(\d+)$", entry)
    if m_star:
        name = m_star.group(1)
        kind = "*" + m_star.group(2)
    elif "(" in entry:
        m_dim = re.match(r"^(\w+)\s*\((.+)\)\s*$", entry)
        if m_dim:
            name = m_dim.group(1)
            dim_local = m_dim.group(2).strip()
        else:
            name = re.sub(r"\(.*", "", entry).strip()
    else:
        name = entry

    if not re.match(r"^\w+$", name):
        return {}

    return {
        "Line": n_line,
        "Position": position,
        "Comp_Name": name.upper(),
        "Fortran_Type": etype,
        "Kind_Param": kind,
        "Dimension": dim_local,
        "Attributes": "|".join(attrs) if attrs else "",
    }


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================


def scope_resolver(n_line: int, units_on_file: list) -> tuple:
    """Returns (unit_name, unit_type) for n_line."""
    candidates = [u for u in units_on_file if u["Start_Line"] <= n_line <= u["End_Line"]]
    if not candidates:
        return "GLOBAL", "FILE_SCOPE"
    u = max(candidates, key=lambda u: u["Start_Line"])
    return u["Name"], u.get("Type", "UNKNOWN")


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

_KINDS_TYPE = {"TYPE_DEFINITION", "VAR_DECLARATION", "END_BLOCK_STMT"}


def extract_types():
    print("--- Derived Types Extraction ---")

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
        rel = u.get("Relative_Path") or u.get("File", "").strip()
        if not rel:
            continue
        try:
            u["Start_Line"] = int(u["Start_Line"])
            u["End_Line"] = int(u["End_Line"])
        except (ValueError, KeyError):
            u["Start_Line"] = 0
            u["End_Line"] = 0
        units_map[rel].append(u)

    rows_types = []
    rows_comps = []
    sorted_files = sorted(units_map.keys(), key=str.lower)

    # 2. Process each file with a state machine
    for rel_path in sorted_files:
        file_name = Path(rel_path).name
        debug_stem = rel_path.replace("/", "__").replace("\\", "__")
        debug_file = AUDIT_PATH / f"{debug_stem}_DEBUG.csv"
        if not debug_file.exists():
            continue

        units_on_file = sorted(units_map[rel_path], key=lambda u: u["Start_Line"])

        active_type = None  # dict while inside a TYPE body

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kind = row.get("Kind", "")
                if kind not in _KINDS_TYPE:
                    continue

                try:
                    n_line = int(row["Line"])
                except (ValueError, KeyError):
                    continue

                content = row.get("Content", "")

                if kind == "TYPE_DEFINITION":
                    m = RE_NAME_TYPE.match(content)
                    if not m:
                        continue
                    host_unit, host_tipo = scope_resolver(n_line, units_on_file)
                    active_type = {
                        "File": file_name,
                        "Unit": host_unit,
                        "Unit_Type": host_tipo,
                        "Start_Line": n_line,
                        "End_Line": n_line,  # updated when closing
                        "Type_Name": m.group(1).upper(),
                        "Components": [],
                    }

                elif active_type is not None:
                    if kind == "END_BLOCK_STMT" and RE_END_TYPE.match(content):
                        active_type["End_Line"] = n_line
                        # Emit definition
                        comps = active_type["Components"]
                        rows_types.append(
                            {
                                "File": active_type["File"],
                                "Unit": active_type["Unit"],
                                "Unit_Type": active_type["Unit_Type"],
                                "Start_Line": active_type["Start_Line"],
                                "End_Line": active_type["End_Line"],
                                "Type_Name": active_type["Type_Name"],
                                "N_Components": len(comps),
                            }
                        )
                        for comp in comps:
                            rows_comps.append(
                                {
                                    "File": file_name,
                                    "Type_Name": active_type["Type_Name"],
                                    **comp,
                                }
                            )
                        active_type = None

                    elif kind == "VAR_DECLARATION":
                        pos_ini = len(active_type["Components"]) + 1
                        nuevos = parse_component(content, n_line, pos_ini)
                        active_type["Components"].extend(nuevos)

    # 3. Export CSVs
    _write_csv(DEFS_OUTPUTS, rows_types, TYPES_COLS)
    _write_csv(COMPS_OUTPUTS, rows_comps, COMPS_COLS)

    n_types = len(rows_types)
    n_comps = len(rows_comps)
    print(f"Derived types           : {n_types}")
    print(f"Total components        : {n_comps}")
    print()
    print("Generated:")
    print(f"  {DEFS_OUTPUTS}")
    print(f"  {COMPS_OUTPUTS}")


# =============================================================================
# HELPERS
# =============================================================================


def _write_csv(path: Path, rows: list, columns: list):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"  → {path.name}  ({len(rows)} rows)")


# =============================================================================
# ENTRY POINT
# =============================================================================


def main():
    extract_types()


if __name__ == "__main__":
    main()
