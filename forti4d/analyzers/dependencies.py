import sys
import csv
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Set, Tuple

from loguru import logger

# --- IMPORT OF BASE TOOLS ---
try:
    from forti4d.lib.reader_logical import read_logical_lines
    from forti4d.lib.patterns_v1 import (
        RE_PROGRAM,
        RE_MODULE,
        RE_SUBROUTINE,
        RE_FUNCTION,
        RE_INTERFACE,
    )
except ImportError as e:
    logger.error(f"ERROR: Missing base files (reader.py or patterns.py).\n{e}")
    sys.exit(1)

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================
from forti4d import config

# Nature Hierarchy (Lower index = Stronger)
NATURE_HIERARCHY = {
    "ARCHITECTURAL": 1,  # USE
    "PHYSICAL": 2,  # INCLUDE
    "OPERATIONAL": 3,  # CALL, FUNCTION
    "UNKNOWN": 99,
}

# Reference lists
INTRINSIC = {
    "ABS",
    "ACOS",
    "AIMAG",
    "AINT",
    "ALOG",
    "ALOG10",
    "AMAX0",
    "AMAX1",
    "AMIN0",
    "AMIN1",
    "AMOD",
    "ANINT",
    "ASIN",
    "ATAN",
    "ATAN2",
    "CABS",
    "CCOS",
    "CEXP",
    "CHAR",
    "CLOG",
    "CMPLX",
    "CONJG",
    "COS",
    "COSH",
    "CSIN",
    "CSQRT",
    "DABS",
    "DACOS",
    "DASIN",
    "DATAN",
    "DATAN2",
    "DBLE",
    "DCOS",
    "DCOSH",
    "DDIM",
    "DEXP",
    "DIM",
    "DINT",
    "DLOG",
    "DLOG10",
    "DMAX1",
    "DMIN1",
    "DMOD",
    "DNINT",
    "DPROD",
    "DSIGN",
    "DSIN",
    "DSINH",
    "DSQRT",
    "DTAN",
    "DTANH",
    "EXP",
    "FLOAT",
    "IABS",
    "ICHAR",
    "IDIM",
    "IDINT",
    "IDNINT",
    "IFIX",
    "INDEX",
    "INT",
    "ISIGN",
    "LEN",
    "LGE",
    "LGT",
    "LLE",
    "LLT",
    "LOG",
    "LOG10",
    "MAX",
    "MAX0",
    "MAX1",
    "MIN",
    "MIN0",
    "MIN1",
    "MOD",
    "NINT",
    "REAL",
    "SIGN",
    "SIN",
    "SINH",
    "SNGL",
    "SQRT",
    "TAN",
    "TANH",
    "TRIM",
    "ADJUSTL",
    "ADJUSTR",
    "ALLOCATED",
    "ASSOCIATED",
    "PRESENT",
    "KIND",
    "SIZE",
    "SHAPE",
    "LBOUND",
    "UBOUND",
    "SUM",
    "PRODUCT",
    "MATMUL",
    "DOT_PRODUCT",
    "TRANSPOSE",
    "COUNT",
    "ANY",
    "ALL",
    "MAXVAL",
    "MINVAL",
    "MAXLOC",
    "MINLOC",
    "LSHIFT",
    "RSHIFT",
    "AND",
    "OR",
    "XOR",
    "NOT",
    "IAND",
    "IOR",
    "IEOR",
}

KEYWORDS_IGNORE = {
    "IF",
    "WHILE",
    "READ",
    "WRITE",
    "PRINT",
    "OPEN",
    "CLOSE",
    "INQUIRE",
    "BACKSPACE",
    "REWIND",
    "FORMAT",
    "ALLOCATE",
    "DEALLOCATE",
    "NULLIFY",
    "DATA",
    "COMMON",
    "DIMENSION",
    "IMPLICIT",
    "PARAMETER",
    "INTENT",
    "PUBLIC",
    "PRIVATE",
    "OPTIONAL",
    "TARGET",
    "POINTER",
    "SAVE",
    "CASE",
    "SELECT",
    "TYPE",
    "CLASS",
    "FORALL",
    "WHERE",
    "ELSE",
    "ELSEIF",
    "THEN",
    "STOP",
    "PAUSE",
    "RETURN",
    "CYCLE",
    "EXIT",
    "CONTINUE",
    "ENTRY",
    "NAMELIST",
}

# Hardened Regexes
RE_USE = re.compile(r"^\s*use\b\s+(\w+)", re.IGNORECASE)
RE_CALL = re.compile(r"^\s*call\b\s+(\w+)", re.IGNORECASE)
# INCLUDE looks for quotes. Ignores C-style <...>.
RE_INCLUDE = re.compile(r"^\s*include\b\s+['\"]([^'\"]+)['\"]", re.IGNORECASE)
RE_FUNC_CALL = re.compile(r"\b([a-zA-Z]\w*)\s*\(", re.IGNORECASE)

RE_END_MODULE = re.compile(r"^\s*end\s*module\b", re.IGNORECASE)

RE_END_INTERFACE = re.compile(r"^\s*END\s*INTERFACE\b", re.IGNORECASE)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def mask_strings(text: str) -> str:
    """Replaces string contents with '' to avoid false positives."""
    text = re.sub(r"'[^']*'", "''", text)
    text = re.sub(r'"[^"]*"', '""', text)
    return text


def get_strongest_nature(nature_set: Set[str]) -> str:
    """Returns the strongest nature from a set."""
    if not nature_set:
        return ""
    # Sort by ranking
    sorted_natures = sorted(nature_set, key=lambda x: NATURE_HIERARCHY.get(x, 99))
    return sorted_natures[0]


# =============================================================================
# MAIN LOGIC
# =============================================================================


def load_inventory_enhanced(rows=None, results_dir=None) -> Tuple[Dict, Dict, List[Dict]]:
    """
    Builds a name-indexed inventory lookup + per-file unit map, and computes
    the ambiguity report rows. Pure — does not touch disk.

    If `rows` is given (in-memory inventory from a prior step in the same
    pipeline run), uses it directly. Otherwise reads inventory_report.csv
    from results_dir — the standalone path, used when this step runs on
    its own with only its inputs on disk.

    Returns:
      - inventory: {NOMBRE_UPPER: [ {file, type, parent, ...}, ... ]}
      - file_map: {FILE: set(DEFINED_UNIT_NAMES)}
      - ambiguous_rows: list[dict], global ambiguity report rows
    """
    inventory = defaultdict(list)
    file_map = defaultdict(set)  # Quick lookup of what each file defines

    if rows is None:
        inventory_file = Path(results_dir) / "inventory_report.csv"
        if not inventory_file.exists():
            logger.error(f"ERROR: '{inventory_file}' does not exist. Run inventory.py first.")
            sys.exit(1)

        logger.info("Loading inventory...")
        with open(inventory_file, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    for row in rows:
        name = row.get("Name", "").strip().upper()
        file = row.get("Relative_Path", row.get("File", "")).strip()
        utype = row.get("Type", "").strip().upper()
        # READ THE PARENT (if column does not exist, assume GLOBAL for compatibility)
        parent = row.get("Parent", "GLOBAL").strip().upper()

        # Name adjustment for Implicit Main in the Inventory (if applicable)
        # Normally the inventory already carries "IMPLICIT-MAIN".
        # We will handle it at resolution time, or we can pre-process it.

        if name:
            # We save ALL the info needed to decide later
            inventory[name].append(
                {
                    "file": file,
                    "type": utype,
                    "parent": parent,
                }
            )
            file_map[file].add(name)

    # Ambiguity Detection (Global Informational Only)
    ambiguous_rows = []

    for name, occurrences in inventory.items():
        if len(occurrences) > 1:
            # Collect all distinct types involved in the collision
            detected_types = sorted(list(set(d["type"] for d in occurrences)))
            report_type = "/".join(detected_types)  # e.g. "SUBROUTINE/FUNCTION" or just "SUBROUTINE"

            # Save to ambiguity report with detail
            file_list = [d["file"] for d in occurrences]
            ambiguous_rows.append(
                {
                    "Unit_Name": name,
                    "Type": report_type,
                    "Count": len(occurrences),
                    "File_List": "; ".join(sorted(set(file_list))),
                }
            )

    # Return 'inventory' as-is (list of candidates) so resolution can decide
    return inventory, file_map, ambiguous_rows


def scan_file(file_path: Path, source_path: Path = None) -> List[Dict]:
    """
    Scans a file and returns a list of raw dependencies.
    Scans dependencies while tracking the Scope (Parent) of the caller.
    """
    raw_deps = []
    rel_path = str(file_path.relative_to(source_path)) if source_path else file_path.name

    try:
        logical_lines = read_logical_lines(str(file_path))
    except Exception as e:
        logger.warning(f"Error reading {file_path.name}: {e}")
        return []

    # Base name for implicit units
    # RULE: IMPLICIT-MAIN becomes "MAIN__filename.f"
    file_main_name = f"MAIN__{file_path.name}"

    # Initial state
    current_unit_name = file_main_name
    current_unit_type = "IMPLICIT-MAIN"

    # SCOPE TRACKING (PARENT)
    # When we enter a MODULE, current_scope becomes the module name.
    # Subroutines inside will inherit that scope.
    current_scope = "GLOBAL"

    # Control States
    inside_interface = False
    current_is_recursive = False

    for lline in logical_lines:
        if lline.is_comment:
            continue

        text_raw = lline.text.strip()
        line_num = lline.start_line
        text_safe = mask_strings(text_raw)

        # --- INTERFACE LOGIC (CRITICAL TO AVOID FALSE POSITIVES) ---

        # Does an interface start?
        if RE_INTERFACE.match(text_safe):
            inside_interface = True
            continue  # Skip — we do not want to analyze the interior

        # Does an interface end?
        if RE_END_INTERFACE.match(text_safe):
            inside_interface = False
            continue

        # If we are inside, IGNORE EVERYTHING (to avoid falsely changing current_unit_name)
        if inside_interface:
            continue

        # ------------------------------------------------------------------

        # 0. DETECT MODULE CLOSE (to reset scope)
        if RE_END_MODULE.match(text_safe):
            current_scope = "GLOBAL"
            # (Optional: we could reset current_unit_name, but the next header will do it)
            continue

        # 1. DETECT UNIT CHANGE
        m_prog = RE_PROGRAM.match(text_safe)
        m_mod = RE_MODULE.match(text_safe)
        m_sub = RE_SUBROUTINE.match(text_safe)
        m_func = RE_FUNCTION.match(text_safe)

        is_header = False
        if m_prog:
            current_unit_name = m_prog.group(1).upper()
            current_unit_type = "PROGRAM"
            current_scope = "GLOBAL"  # Program siempre es global
            is_header = True
        elif m_mod:
            current_unit_name = m_mod.group(1).upper()
            current_unit_type = "MODULE"
            current_scope = current_unit_name  # The module becomes the Scope!
            is_header = True
        elif m_sub:
            current_unit_name = m_sub.group(1).upper()
            current_unit_type = "SUBROUTINE"
            # If we are inside a module (current_scope != GLOBAL), this subroutine belongs to it.
            # If current_scope is GLOBAL, it is a normal external subroutine.
            # Check if the word RECURSIVE is in the definition
            current_is_recursive = "RECURSIVE" in text_safe.upper()
            is_header = True
        elif m_func:
            current_unit_name = m_func.group(1).upper()
            current_unit_type = "FUNCTION"
            # Check if the word RECURSIVE is in the definition
            current_is_recursive = "RECURSIVE" in text_safe.upper()
            is_header = True

        if is_header:
            continue

        # 2. CAPTURE DEPENDENCIES (we pass source_parent = current_scope)

        # INCLUDE (Physical) - Uses text_raw
        m_inc = RE_INCLUDE.match(text_raw)
        if m_inc:
            target = m_inc.group(1)
            raw_deps.append(
                {
                    "source_file": rel_path,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "INCLUDE",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "PHYSICAL",
                }
            )
            continue

        # USE (Architectural) - Uses text_safe
        m_use = RE_USE.match(text_safe)
        if m_use:
            target = m_use.group(1).upper()
            raw_deps.append(
                {
                    "source_file": rel_path,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "USE",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "ARCHITECTURAL",
                }
            )
            continue

        # CALL (Operative) - Uses text_safe
        m_call = RE_CALL.match(text_safe)
        if m_call:
            target = m_call.group(1).upper()

            # Recursion filter for CALL (rare in subroutines but possible)
            if target == current_unit_name and not current_is_recursive:
                continue

            raw_deps.append(
                {
                    "source_file": rel_path,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "CALL",
                    "target_raw": target,
                    "line": line_num,
                    "nature": "OPERATIONAL",
                }
            )
            # No continue

        # FUNCTION CALL (Operative) - Uses text_safe
        candidates = RE_FUNC_CALL.findall(text_safe)
        for cand in candidates:
            cand_upper = cand.upper()
            if cand_upper in KEYWORDS_IGNORE:
                continue
            if cand_upper in INTRINSIC:
                continue
            if m_call and m_call.group(1).upper() == cand_upper:  # check if it is a CALL <name>
                continue

            # RECURSION
            if cand_upper == current_unit_name:
                if not current_is_recursive:
                    # Access to return array, not a recursive call
                    continue

            # We add it as a candidate. Resolution will determine if it is an array or function.
            raw_deps.append(
                {
                    "source_file": rel_path,
                    "source_unit": current_unit_name,
                    "source_type": current_unit_type,
                    "source_parent": current_scope,
                    "dep_type": "FUNC_CALL",
                    "target_raw": cand_upper,
                    "line": line_num,
                    "nature": "OPERATIONAL",
                }
            )

    return raw_deps


def analyze_dependencies(source_dir: Path, results_dir: Path, *, inputs=None) -> dict:
    """Pure computation. Returns a dict with all 7 logical datasets. No disk writes."""
    inputs = inputs or {}

    # 1. Load base data
    inventory, _, ambiguous_rows = load_inventory_enhanced(
        rows=inputs.get("inventory_report"), results_dir=results_dir
    )
    source_path = source_dir

    # 2. Scan Files
    files = sorted([f for f in source_path.rglob("*") if f.suffix.lower() in (".f90", ".f", ".for", ".f95")])
    logger.info(f"Analyzing {len(files)} files...")

    all_raw_deps = []
    for f in files:
        # print(f"  Scanning: {f.name}")
        all_raw_deps.extend(scan_file(f, source_path))

    # 3. Resolution and Cross-matching
    master_rows = []
    orphans_set = set()

    # Structures for aggregated reports
    dest_file_map = defaultdict(list)
    graph_edges = set()  # (UnitA, TypeA, UnitB, TypeB, DepType)
    edges_counter = Counter()
    impact_fan_out = Counter()
    impact_fan_in = Counter()

    # Structure for file-level report
    # {(FileSrc, FileDest): set(Nature)}
    file_deps_map = defaultdict(set)
    file_deps_details = defaultdict(set)  # To list dep types (USE, CALL...)

    logger.info("Resolving dependencies with Scope...")

    for item in all_raw_deps:
        target = item["target_raw"]
        dtype = item["dep_type"]

        # Caller Context
        source_parent = item.get("source_parent", "GLOBAL")

        # Destination Resolution
        dest_file = None
        dest_type = "UNKNOWN"
        dest_unit = target  # Default to the raw name

        if dtype == "INCLUDE":
            # Include is special, the target is a file
            dest_file = target
            dest_type = "FILE"
            # Verificar existencia
            if not (source_path / target).exists():
                dest_file = "MISSING_FILE"

        else:
            # Look for candidates in inventory
            candidates = inventory.get(target)

            if not candidates:
                # NOT FOUND
                dest_file = None
                if dtype == "FUNC_CALL":
                    continue  # Ignore non-inventoried arrays/functions
            else:
                # SCOPE RESOLUTION STRATEGY
                match = None

                # 1. Priority: Sibling/Internal Scope (Same Parent)
                # e.g., area_square calls area, and both are children of mod_calc.
                internal_matches = [c for c in candidates if c["parent"] == source_parent and source_parent != "GLOBAL"]

                if internal_matches:
                    match = internal_matches[0]  # Found internally!
                else:
                    # 2. Global Scope
                    global_matches = [c for c in candidates if c["parent"] == "GLOBAL"]
                    if global_matches:
                        match = global_matches[0]
                    else:
                        # 3. External Scope (Another Module)
                        # Ambiguity arises if there are several modules with the same name (rare in valid code)
                        # If there is only one, we assume it was imported via USE (even if we do not validate USE explicitly yet)
                        if len(candidates) == 1:
                            match = candidates[0]
                        else:
                            # Real Conflict: Exists in mod_A and mod_B, and it is unclear which one is used.
                            dest_file = "MULTIPLE_CANDIDATES"

                            # Recover types to report something useful (e.g. SUBROUTINE)
                            types = sorted(list(set(c["type"] for c in candidates)))
                            if len(types) == 1:
                                dest_type = types[0]
                            else:
                                dest_type = "AMBIGUOUS_TYPE"

                if match:
                    dest_file = match["file"]
                    dest_type = match["type"]

        # If we reach here, it is a relevant dependency (or a confirmed USE/CALL orphan)

        # Register real Orphan
        if dest_file is None:
            dest_file = "EXTERNAL_OR_MISSING"
            dest_type = "EXTERNAL"
            orphans_set.add((target, dtype))

        # --- Add to Master ---
        master_rows.append(
            {
                "Source_File": item["source_file"],
                "Source_Unit": item["source_unit"],
                "Source_Type": item["source_type"],
                "Dep_Type": dtype,
                "Target_Unit": dest_unit,
                "Target_Type": dest_type,
                "Target_File": dest_file,
                "Source_Line": item["line"],
            }
        )

        # --- Add to Graph and Impact Matrix (Only resolved internal ones) ---
        if dest_file and dest_file not in ("MULTIPLE_CANDIDATES", "EXTERNAL_OR_MISSING", "MISSING_FILE"):
            # Grafo
            dest_files = "; ".join(sorted(set(inv["file"] for inv in inventory.get(dest_unit, []))))
            graph_edges.add((item["source_unit"], item["source_type"], dest_unit, dest_type, dtype, dest_files))
            key = (item["source_unit"], dest_unit, item["source_type"], dest_type)
            edges_counter[key] += 1

            # Impacto
            impact_fan_out[item["source_unit"]] += 1
            impact_fan_in[dest_unit] += 1

            # File Dependency (Only if they are different)
            if item["source_file"] != dest_file:
                pair = (item["source_file"], dest_file)
                file_deps_map[pair].add(item["nature"])
                file_deps_details[pair].add(dtype)

    # 4. Build the 7 logical datasets (no disk writes here)

    # B. Units Graph
    graph_rows = []
    for row in sorted(list(graph_edges)):
        key = (row[0], row[2], row[1], row[3])
        weight = edges_counter[key]
        graph_rows.append(
            {
                "Source_Unit": row[0],
                "Source_Type": row[1],
                "Target_Unit": row[2],
                "Target_Type": row[3],
                "Dep_Type": row[4],
                "Target_File": row[5],
                "Weight": weight,
            }
        )

    # C. Impact Matrix
    all_units = set(impact_fan_out.keys()) | set(impact_fan_in.keys())
    rows_impact = []
    for u in sorted(all_units):
        if u.startswith("MAIN__"):
            report_type = "IMPLICIT-MAIN"
            files_report = u.replace("MAIN__", "")
        else:
            candidates = inventory.get(u)
            if candidates:
                detected_types = sorted(list(set(d["type"] for d in candidates)))
                report_type = "/".join(detected_types)
                files_report = "; ".join(sorted(set(d["file"] for d in candidates)))
        rows_impact.append(
            {
                "Unit": u,
                "Type": report_type,
                "File": files_report,
                "Fan_Out": impact_fan_out.get(u, 0),
                "Fan_In": impact_fan_in.get(u, 0),
            }
        )

    # D. Orphans
    orphan_rows = [{"Target_Unit": u, "Dep_Type": t, "Status": "EXTERNAL_OR_LIBRARY"} for u, t in sorted(list(orphans_set))]

    # E. File Dependencies
    file_rows = []
    for (src, dst), natures in file_deps_map.items():
        strongest = get_strongest_nature(natures)
        details = "; ".join(sorted(file_deps_details[(src, dst)]))
        all_nats = "; ".join(sorted(natures))
        file_rows.append(
            {
                "Source_File": src,
                "Target_File": dst,
                "Strong_Nature": strongest,
                "Nature_List": all_nats,
                "Detail_Types": details,
            }
        )

    # F. INCLUDE file references — one row per INCLUDE statement
    include_rows = []
    seen_includes = set()
    for item in all_raw_deps:
        if item.get("dep_type") != "INCLUDE":
            continue
        target = item["target_raw"]
        key = (item["source_file"], item["source_unit"], target)
        if key in seen_includes:
            continue
        seen_includes.add(key)
        estado = "PRESENT" if (source_path / target).exists() else "MISSING"
        include_rows.append(
            {
                "Source_File": item["source_file"],
                "Source_Unit": item["source_unit"],
                "Included_File": target,
                "Status": estado,
            }
        )
    include_rows.sort(key=lambda r: (r["Source_File"], r["Source_Unit"]))

    return {
        "dep_00_ambiguities": ambiguous_rows,
        "dep_01_master_data": master_rows,
        "dep_02_unit_graph": graph_rows,
        "dep_03_impact_matrix": rows_impact,
        "dep_04_external_orphans": orphan_rows,
        "dep_05_file_dependencies": file_rows,
        "dep_06_include_files": include_rows,
    }


def write_dependencies(results_dir: Path, data: dict) -> None:
    """Only place that touches disk for this step. Same 7 files, same behavior as before —
    each is always written (even if empty), only the console message is conditional."""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    ambiguities_out = results_dir / "dep_00_ambiguities.csv"
    master_out = results_dir / "dep_01_master_data.csv"
    graph_out = results_dir / "dep_02_unit_graph.csv"
    impact_out = results_dir / "dep_03_impact_matrix.csv"
    orphans_out = results_dir / "dep_04_external_orphans.csv"
    depends_out = results_dir / "dep_05_file_dependencies.csv"
    includes_out = results_dir / "dep_06_include_files.csv"

    ambiguous_rows = data["dep_00_ambiguities"]
    with open(ambiguities_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Unit_Name", "Type", "Count", "File_List"])
        w.writeheader()
        w.writerows(ambiguous_rows)
    if ambiguous_rows:
        logger.success(f"  -> Detected {len(ambiguous_rows)} ambiguous units (see {ambiguities_out})")
    else:
        logger.success(f"  -> No ambiguous unit names found (see {ambiguities_out})")

    # A. Master
    keys_master = [
        "Source_File",
        "Source_Unit",
        "Source_Type",
        "Dep_Type",
        "Target_Unit",
        "Target_Type",
        "Target_File",
        "Source_Line",
    ]
    master_rows = data["dep_01_master_data"]
    with open(master_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys_master)
        w.writeheader()
        w.writerows(master_rows)
    if master_rows:
        logger.success(f"Generated:{master_out}")

    # B. Units Graph
    graph_rows = data["dep_02_unit_graph"]
    with open(graph_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["Source_Unit", "Source_Type", "Target_Unit", "Target_Type", "Dep_Type", "Target_File", "Weight"],
        )
        w.writeheader()
        w.writerows(graph_rows)
    if graph_rows:
        logger.success(f"Generated:{graph_out}")

    # C. Impact Matrix
    rows_impact = data["dep_03_impact_matrix"]
    with open(impact_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Unit", "Type", "File", "Fan_Out", "Fan_In"])
        w.writeheader()
        w.writerows(rows_impact)
    if rows_impact:
        logger.success(f"Generated:{impact_out}")

    # D. Orphans
    orphan_rows = data["dep_04_external_orphans"]
    with open(orphans_out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Target_Unit", "Dep_Type", "Status"])
        w.writeheader()
        w.writerows(orphan_rows)
    if orphan_rows:
        logger.success(f"Generated:{orphans_out}")

    # E. File Dependencies
    file_rows = data["dep_05_file_dependencies"]
    with open(depends_out, "w", newline="", encoding="utf-8") as f:
        keys = ["Source_File", "Target_File", "Strong_Nature", "Nature_List", "Detail_Types"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(file_rows)
    if file_rows:
        logger.success(f"Generated:{depends_out}")

    # F. INCLUDE file references
    include_rows = data["dep_06_include_files"]
    with open(includes_out, "w", newline="", encoding="utf-8") as f:
        keys = ["Source_File", "Source_Unit", "Included_File", "Status"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(include_rows)
    if include_rows:
        logger.success(f"Generated: {includes_out} ({len(include_rows)} INCLUDE references)")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    data = analyze_dependencies(source_dir, results_dir, inputs=inputs)
    write_dependencies(results_dir, data)
    return data


if __name__ == "__main__":
    main()
