import csv
import re
from collections import defaultdict
from pathlib import Path

from loguru import logger

from forti4d.analyzers.inventory import load_inventory
from forti4d import config

VARIABLES_COLS = [
    "File",
    "Unit",
    "Unit_Type",
    "Line",
    "Var_Name",
    "Fortran_Type",
    "Kind_Param",
    "Dimension",
    "Attributes",
    "Intent",
    "Initial_Value",
    "Is_Parameter",
    "In_Common",
    "Truncated",
]
SIGNATURES_COLS = [
    "File",
    "Unit",
    "Unit_Type",
    "Signature_Line",
    "Position",
    "Arg_Name",
    "Return_Type",
]
IMPLICIT_COLS = [
    "File",
    "Unit",
    "Unit_Type",
    "Line",
    "Rule",
    "Is_None",
]


# =============================================================================
# EXTRACTION PATTERNS (local to this script — do not belong to patterns_v2)
# =============================================================================

# -- Signatures --
# SUBROUTINE: optional PURE/ELEMENTAL/RECURSIVE, then name and arg list
RE_SIGNATURE_SUB = re.compile(
    r"^\s*(?:(?:pure|elemental|recursive)\s+)*subroutine\s+(\w+)\s*\(\s*(.*?)\s*\)",
    re.IGNORECASE,
)
# FUNCTION: any prefix (qualifiers + return type), then name and args
# The optional RESULT clause is ignored by the greedy $
RE_SIGNATURE_FUNC = re.compile(
    r"^\s*(.*?)\bfunction\s+(\w+)\s*\(\s*(.*?)\s*\)\s*(?:result\s*\(\s*\w+\s*\))?\s*$",
    re.IGNORECASE,
)

# -- F90 declarations (with ::) --
RE_DECL_F90 = re.compile(r"^(.*?)\s*::\s*(.+)$")

# -- F77 declarations (without ::): base type followed by variable list --
RE_DECL_F77 = re.compile(
    r"^\s*(integer|real|double\s+precision|complex|logical|character|byte|type|class)"
    r"(\s*\*\s*\d+|\s*\(\s*(?:(?:kind|len)\s*=\s*)?\w+\s*\))?\s+"
    r"(.+)$",
    re.IGNORECASE,
)

# -- F77 standalone PARAMETER: PARAMETER (PI=3.14, N=100) --
RE_PARAM_F77 = re.compile(r"^\s*parameter\s*\(\s*(.*)\s*\)\s*$", re.IGNORECASE)

# -- IMPLICIT --
RE_IMPL_NONE = re.compile(r"^\s*implicit\s+none\b", re.IGNORECASE)
RE_IMPL_RULE = re.compile(r"^\s*implicit\s+(.*)", re.IGNORECASE)

# -- Attributes in F90 prefix (to parse before ::) --
RE_ATTR_INTENT = re.compile(r"\bintent\s*\(\s*(in|out|inout)\s*\)", re.IGNORECASE)
RE_ATTR_DIM = re.compile(r"\bdimension\s*\(([^)]+)\)", re.IGNORECASE)
RE_ATTR_SIMPLES = re.compile(
    r"\b(allocatable|pointer|save|target|external|intrinsic|optional|"
    r"volatile|value|parameter|public|private|protected)\b",
    re.IGNORECASE,
)

# Standalone F90 attributes without :: (fix issue-2 hybrid Fortran)
# Example: DIMENSION X(100), POINTER :: P, ALLOCATABLE X
RE_ATTR_STANDALONE = re.compile(
    r"^\s*(dimension|allocatable|pointer|target|save|external|intrinsic|" r"optional|volatile|protected)\s+(.*)",
    re.IGNORECASE,
)


# =============================================================================
# PARSING FUNCTIONS
# =============================================================================


def extract_kind_type(type_str: str) -> str:
    """
    Extracts the KIND or LEN from a type specifier handling nested parentheses.
    Examples:
      'REAL(8)'                          → '8'
      'INTEGER(KIND=4)'                  → '4'
      'REAL(KIND=selected_real_kind(15,307))' → 'selected_real_kind(15,307)'
      'CHARACTER(LEN=*)'                 → '*'
      'REAL*8'                           → '*8'
    """
    # First try asterisk notation: REAL*8
    m_star = re.search(r"\*\s*(\d+)", type_str)
    if m_star and "(" not in type_str[: m_star.start()].lstrip():
        return "*" + m_star.group(1)

    # Find the first '(' after the type name
    i = type_str.find("(")
    if i == -1:
        return ""

    # Extract content up to the balanced ')'
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
    # Strip KIND= or LEN= prefix
    raw = re.sub(r"^(?:kind|len)\s*=\s*", "", raw, flags=re.IGNORECASE)
    return raw


def split_list(s: str) -> list:
    """
    Splits s by commas respecting nested parentheses.
    Example: 'A, B(10,5), C*4' → ['A', 'B(10,5)', 'C*4']
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


def parse_prefix_type(prefix: str) -> dict:
    """
    Extracts from the prefix of an F90 declaration (text before ::):
      base_type, kind, dimension, intent, attributes, is_parameter.
    Example: 'INTEGER(KIND=4), INTENT(IN), DIMENSION(N)'
    → {type: 'INTEGER', kind: '4', intent: 'IN', dim: 'N', ...}
    """
    result = {
        "type": "",
        "kind": "",
        "dim": "",
        "intent": "",
        "attrs": [],
        "is_param": False,
    }
    parts = split_list(prefix.strip())
    if not parts:
        return result

    # First part = base type (with possible inline KIND or LEN)
    type_str = parts[0].strip()
    m_base = re.match(r"(\w+(?:\s+\w+)*)", type_str, re.IGNORECASE)
    if m_base:
        result["type"] = m_base.group(1).strip().upper()

    # Inline kind: REAL(8), INTEGER(KIND=4), REAL(KIND=selected_real_kind(15,307))
    result["kind"] = extract_kind_type(type_str)

    # Attributes (partes[1:])
    for attr in parts[1:]:
        attr = attr.strip()

        m_intent = RE_ATTR_INTENT.search(attr)
        if m_intent:
            result["intent"] = m_intent.group(1).upper()
            result["attrs"].append(f"INTENT({result['intent']})")
            continue

        m_dim = RE_ATTR_DIM.search(attr)
        if m_dim:
            result["dim"] = m_dim.group(1)
            result["attrs"].append(f"DIMENSION({m_dim.group(1)})")
            continue

        if re.match(r"^\s*parameter\s*$", attr, re.IGNORECASE):
            result["is_param"] = True
            result["attrs"].append("PARAMETER")
            continue

        m_simple = RE_ATTR_SIMPLES.match(attr)
        if m_simple:
            result["attrs"].append(attr.upper())

    return result


def parse_var_entry(
    entry: str, base_type: str, base_kind: str, base_dim: str, intent: str, attrs: list, is_param: bool
) -> dict:
    """
    Parses an individual entry from the variable list.
    Examples: 'X', 'X(10)', 'X(N,M)', 'X*4', 'PI = 3.14159'
    """
    entry = entry.strip()
    name = ""
    dim = base_dim
    kind = base_kind
    value = ""

    # Initial value (for inline PARAMETER: name = value)
    if "=" in entry:
        idx = entry.index("=")
        value = entry[idx + 1 :].strip()
        entry = entry[:idx].strip()

    # F77 asterisk-style kind: X*4
    m_star = re.match(r"^(\w+)\s*\*\s*(\d+)$", entry)
    if m_star:
        name = m_star.group(1)
        kind = "*" + m_star.group(2)
    # Explicit dimension: X(10) or X(N,M)
    elif "(" in entry:
        m_dim = re.match(r"^(\w+)\s*\((.+)\)\s*$", entry)
        if m_dim:
            name = m_dim.group(1)
            dim = m_dim.group(2).strip()
        else:
            name = re.sub(r"\(.*", "", entry).strip()
    else:
        name = entry

    if not re.match(r"^\w+$", name):
        return {}

    return {
        "Var_Name": name.upper(),
        "Fortran_Type": base_type,
        "Kind_Param": kind,
        "Dimension": dim,
        "Attributes": "|".join(attrs) if attrs else "",
        "Intent": intent,
        "Initial_Value": value,
        "Is_Parameter": "YES" if (is_param or bool(value)) else "NO",
        "In_Common": "",  # filled in post-processing
        "Truncated": "NO",
    }


def parse_declaration(content: str, scope: str, unit_type: str, file: str, n_line: int) -> list:
    """
    Parses a VAR_DECLARATION statement.
    Distinguishes F90 (with ::) vs F77 (without ::) by presence of '::'.
    """
    base = {
        "File": file,
        "Unit": scope,
        "Unit_Type": unit_type,
        "Line": n_line,
    }
    truncated = len(content) >= 118

    rows = []

    if "::" in content:
        # F90 with ::
        m = RE_DECL_F90.match(content.strip())
        if not m:
            return []
        info = parse_prefix_type(m.group(1))
        list_str = m.group(2).strip()

        # If the type is not recognized, we still extract with an empty type
        # (could be ALLOCATABLE :: x, y or another attribute-only form)
        for entry in split_list(list_str):
            row = parse_var_entry(
                entry,
                info["type"],
                info["kind"],
                info["dim"],
                info["intent"],
                info["attrs"],
                info["is_param"],
            )
            if row:
                row["Truncated"] = "YES" if truncated else "NO"
                rows.append({**base, **row})
    else:
        # F77 without :: — try base type first
        m = RE_DECL_F77.match(content.strip())
        if not m:
            # Standalone attribute without type: DIMENSION X(100), SAVE X, EXTERNAL PROC
            m_attr = RE_ATTR_STANDALONE.match(content.strip())
            if not m_attr:
                return []
            attr_name = m_attr.group(1).upper()
            list_str = m_attr.group(2).strip()
            # Strip residual :: if present (POINTER :: P without type)
            list_str = re.sub(r"^::\s*", "", list_str)
            for entry in split_list(list_str):
                row = parse_var_entry(entry, "", "", "", "", [attr_name], False)
                if row:
                    row["Truncated"] = "YES" if truncated else "NO"
                    rows.append({**base, **row})
            return rows

        base_type = re.sub(r"\s+", " ", m.group(1).upper())  # DOUBLE PRECISION
        # Use extraer_kind_tipo to normalize: removes outer parentheses and KIND=/LEN=
        kind_suffix = extract_kind_type(m.group(1) + (m.group(2) or ""))
        list_str = m.group(3).strip()

        for entry in split_list(list_str):
            row = parse_var_entry(entry, base_type, kind_suffix, "", "", [], False)
            if row:
                row["Truncated"] = "YES" if truncated else "NO"
                rows.append({**base, **row})

    return rows


def parse_parameter(content: str, scope: str, unit_type: str, file: str, n_line: int) -> list:
    """
    Parses a standalone F77 PARAMETER statement: PARAMETER (PI=3.14, N=100)
    """
    m = RE_PARAM_F77.match(content.strip())
    if not m:
        return []

    base = {
        "File": file,
        "Unit": scope,
        "Unit_Type": unit_type,
        "Line": n_line,
    }
    rows = []
    for entry in split_list(m.group(1)):
        if "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        name = name.strip().upper()
        if not re.match(r"^\w+$", name):
            continue
        rows.append(
            {
                **base,
                "Var_Name": name,
                "Fortran_Type": "",  # implicit type; not known here
                "Kind_Param": "",
                "Dimension": "",
                "Attributes": "PARAMETER",
                "Intent": "",
                "Initial_Value": value.strip(),
                "Is_Parameter": "YES",
                "In_Common": "",
                "Truncated": "NO",
            }
        )
    return rows


def parse_implicit(content: str, scope: str, unit_type: str, file: str, n_line: int) -> dict:
    """
    Parses an IMPLICIT statement (NONE or type rule).
    """
    is_none = bool(RE_IMPL_NONE.match(content.strip()))
    if is_none:
        rule = "NONE"
    else:
        m = RE_IMPL_RULE.match(content.strip())
        rule = m.group(1).strip() if m else content.strip()

    return {
        "File": file,
        "Unit": scope,
        "Unit_Type": unit_type,
        "Line": n_line,
        "Rule": rule,
        "Is_None": "YES" if is_none else "NO",
    }


def parse_signature(content: str, kind: str, scope: str, unit_type: str, file: str, n_line: int) -> list:
    """
    Extracts formal arguments from the SUBROUTINE or FUNCTION header.
    kind: 'SUBROUTINE_UNIT' or 'FUNCTION_UNIT'
    Returns one row per argument (1-based position).
    Returns an empty list if there are no arguments.
    """
    return_type = ""

    if kind == "SUBROUTINE_UNIT":
        m = RE_SIGNATURE_SUB.match(content.strip())
        if not m:
            return []
        args_str = m.group(2).strip()
    else:
        m = RE_SIGNATURE_FUNC.match(content.strip())
        if not m:
            return []
        # Prefix = qualifiers + return type (if any)
        prefix = re.sub(r"\b(pure|elemental|recursive)\b", "", m.group(1), flags=re.IGNORECASE).strip()
        return_type = prefix.upper() if prefix else ""
        args_str = m.group(3).strip()

    if not args_str:
        return []

    rows = []
    for i, arg in enumerate(split_list(args_str), 1):
        arg_name = arg.strip().upper()
        if not arg_name or arg_name == "*":  # * = alternate return F77
            continue
        rows.append(
            {
                "File": file,
                "Unit": scope,
                "Unit_Type": unit_type,
                "Signature_Line": n_line,
                "Position": i,
                "Arg_Name": arg_name,
                "Return_Type": return_type,
            }
        )

    return rows


def extract_common_vars(content: str) -> dict:
    """
    Extracts the var_name → block_name mapping from a COMMON statement.
    Example: 'COMMON /A/ X, Y /B/ Z' → {'X': 'A', 'Y': 'A', 'Z': 'B'}
    """
    result = {}
    # Strip leading COMMON keyword
    rest = re.sub(r"^\s*common\s*", "", content.strip(), flags=re.IGNORECASE)
    if not rest:
        return result

    current_block = "(BLANK)"
    vars_buffer = []
    i = 0

    while i < len(rest):
        if rest[i] == "/":
            # Flush buffer to current block
            for v in split_list("".join(vars_buffer)):
                m = re.match(r"\s*(\w+)", v)
                if m:
                    result[m.group(1).upper()] = current_block
            vars_buffer = []
            # Read block name
            j = rest.find("/", i + 1)
            if j == -1:
                break
            name = rest[i + 1 : j].strip()
            current_block = name if name else "(BLANK)"
            i = j + 1
        else:
            vars_buffer.append(rest[i])
            i += 1

    # Flush remaining items
    for v in split_list("".join(vars_buffer)):
        m = re.match(r"\s*(\w+)", v)
        if m:
            result[m.group(1).upper()] = current_block

    return result


# =============================================================================
# SCOPE RESOLUTION
# =============================================================================


def scope_resolver(n_line: int, units_on_file: list) -> tuple:
    """
    Returns (unit_name, unit_type) for line n_line.
    When nested, chooses the unit with the latest start (innermost).
    """
    candidates = [u for u in units_on_file if u["Start_Line"] <= n_line <= u["End_Line"]]
    if not candidates:
        return "GLOBAL", "FILE_SCOPE"
    u = max(candidates, key=lambda u: u["Start_Line"])
    return u["Name"], u.get("Type", "UNKNOWN")


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

# Kinds of interest (values as written by profiler.py: .name of the enum)
_KINDS_INTEREST = {
    "SUBROUTINE_UNIT",
    "FUNCTION_UNIT",
    "VAR_DECLARATION",
    "PARAMETER_STMT",
    "IMPLICIT_STMT",
    "COMMON_STMT",
}


def extract_symbols(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes. Returns None for all 3 outputs when
    there's nothing to process (same as the original — no file is written)."""
    inputs = inputs or {}
    logger.debug("--- Symbol Extraction ---")

    # 1. Inventory
    try:
        inventory_list = load_inventory(
            rows=inputs.get("inventory_report"), csv_path=Path(results_dir) / "inventory_report.csv"
        )
    except Exception as e:
        logger.warning(f"ERROR loading inventory: {e}")
        return {"symbol_variables": None, "symbol_signatures": None, "symbol_implicit": None}

    if not inventory_list:
        logger.warning("Inventory is empty.")
        return {"symbol_variables": None, "symbol_signatures": None, "symbol_implicit": None}

    # Group units by file, ensuring int types
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

    rows_vars = []
    rows_signatures = []
    rows_implicit = []

    # common_map[(file, unit_upper)] = {VAR_NAME_UPPER: block_name}
    # used in post-processing to fill In_Common in filas_vars
    common_map = defaultdict(dict)

    audit_data = inputs.get("audit")  # {rel_path: debug_rows}, from profiler.py — avoids re-reading from disk
    audit_path_ = Path(results_dir) / "audit"
    sorted_files = sorted(units_map.keys(), key=str.lower)

    # 2. Process each file
    for rel_path in sorted_files:
        file_name = Path(rel_path).name

        debug_rows = audit_data.get(rel_path) if audit_data is not None else None
        if debug_rows is None:
            debug_stem = rel_path.replace("/", "__").replace("\\", "__")
            debug_file = audit_path_ / f"{debug_stem}_DEBUG.csv"
            if not debug_file.exists():
                continue
            with open(debug_file, encoding="utf-8-sig") as f:
                debug_rows = list(csv.DictReader(f))

        units_on_file = sorted(units_map[rel_path], key=lambda u: u["Start_Line"])

        for row in debug_rows:
            kind = row.get("Kind", "")
            if kind not in _KINDS_INTEREST:
                continue

            try:
                n_line = int(row["Line"])
            except (ValueError, KeyError):
                continue

            content = row.get("Content", "")
            scope, unit_type = scope_resolver(n_line, units_on_file)

            if kind in ("SUBROUTINE_UNIT", "FUNCTION_UNIT"):
                news = parse_signature(content, kind, scope, unit_type, file_name, n_line)
                rows_signatures.extend(news)

            elif kind == "VAR_DECLARATION":
                news = parse_declaration(content, scope, unit_type, file_name, n_line)
                rows_vars.extend(news)

            elif kind == "PARAMETER_STMT":
                news = parse_parameter(content, scope, unit_type, file_name, n_line)
                rows_vars.extend(news)

            elif kind == "IMPLICIT_STMT":
                rows_implicit.append(parse_implicit(content, scope, unit_type, file_name, n_line))

            elif kind == "COMMON_STMT":
                mapping = extract_common_vars(content)
                common_map[(file_name, scope.upper())].update(mapping)

    # 3. Post-processing: enrich filas_vars with In_Common
    for row in rows_vars:
        key = (row["File"], row["Unit"].upper())
        row["In_Common"] = common_map.get(key, {}).get(row["Var_Name"], "")

    return {
        "symbol_variables": rows_vars,
        "symbol_signatures": rows_signatures,
        "symbol_implicit": rows_implicit,
        "common_units_count": len(common_map),
    }


def write_symbols(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    rows_vars = data["symbol_variables"]
    if rows_vars is None:
        return  # inventory empty / load error — nothing written at all, same as before

    results_dir = Path(results_dir)
    rows_signatures = data["symbol_signatures"]
    rows_implicit = data["symbol_implicit"]

    # 4. Export CSVs
    _write_csv(results_dir / "symbol_variables.csv", rows_vars, VARIABLES_COLS)
    _write_csv(results_dir / "symbol_signatures.csv", rows_signatures, SIGNATURES_COLS)
    _write_csv(results_dir / "symbol_implicit.csv", rows_implicit, IMPLICIT_COLS)

    # 5. Console summary
    n_impl_none = sum(1 for f in rows_implicit if f["Is_None"] == "YES")

    logger.info(f"Variables / constants   : {len(rows_vars)}")
    logger.info(f"Formal arguments        : {len(rows_signatures)}")
    logger.info(f"IMPLICIT statements     : {len(rows_implicit)}  ({n_impl_none} IMPLICIT NONE)")
    logger.info(f"Units with COMMON map   : {data['common_units_count']}")
    logger.success("Generated:")
    logger.success(f"  {results_dir / 'symbol_variables.csv'}")
    logger.success(f"  {results_dir / 'symbol_signatures.csv'}")
    logger.success(f"  {results_dir / 'symbol_implicit.csv'}")


# =============================================================================
# WRITE HELPERS
# =============================================================================


def _write_csv(path: Path, rows: list, columns: list):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    logger.debug(f"  → {path.name}  ({len(rows)} rows)")


# =============================================================================
# ENTRY POINT
# =============================================================================


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = extract_symbols(source_dir, results_dir, inputs=inputs)
    write_symbols(results_dir, data)
    return data


if __name__ == "__main__":
    main()
