import sys
import os
import csv
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Set, Tuple

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
    print(f"ERROR: Missing base files (reader.py or patterns.py).\n{e}")
    sys.exit(1)

# =============================================================================
# CONFIGURATION AND CONSTANTS
# =============================================================================
from forti4d.config import CODE_PATH, RESULTS_PATH

INVENTORY_FILE = RESULTS_PATH / "inventory_report.csv"

# Output Files
AMBIGUITIES_OUT = RESULTS_PATH / "dep_00_ambiguities.csv"
MASTER_OUT = RESULTS_PATH / "dep_01_master_data.csv"
GRAPH_OUT = RESULTS_PATH / "dep_02_unit_graph.csv"
IMPACT_OUT = RESULTS_PATH / "dep_03_impact_matrix.csv"
ORPHANS_OUT = RESULTS_PATH / "dep_04_external_orphans.csv"
DEPENDS_OUT = RESULTS_PATH / "dep_05_file_dependencies.csv"
INCLUDES_OUT = RESULTS_PATH / "dep_06_include_files.csv"

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


def load_inventory_enhanced(report_ambiguities=False) -> Tuple[Dict, Dict]:
    """
    Loads inventory and detects duplicates.
    Returns:
      - inventory: {NOMBRE_UPPER: [ {file, type, parent, ...}, ... ]}
      - file_map: {FILE: set(DEFINED_UNIT_NAMES)}
    Generates a GLOBAL ambiguities report.
    """
    inventory = defaultdict(list)
    file_map = defaultdict(set)  # Quick lookup of what each file defines

    if not os.path.exists(INVENTORY_FILE):
        print(f"ERROR: '{INVENTORY_FILE}' does not exist. Run inventory.py first.")
        sys.exit(1)

    print("Loading inventory...")
    with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
        reader_csv = csv.DictReader(f)
        for row in reader_csv:
            name = row.get("Name", "").strip().upper()
            file = row.get("File", "").strip()
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

    # Save ambiguity report
    if ambiguous_rows and report_ambiguities:
        with open(AMBIGUITIES_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Unit_Name", "Type", "Count", "File_List"])
            w.writeheader()
            w.writerows(ambiguous_rows)
        print(f"  -> Detected {len(ambiguous_rows)} ambiguous units (see {AMBIGUITIES_OUT})")

    # Return 'inventory' as-is (list of candidates) so resolution can decide
    return inventory, file_map


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
        print(f"Error reading {file_path.name}: {e}")
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


def main():
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)

    # 1. Load base data
    inventory, _ = load_inventory_enhanced(report_ambiguities=True)
    source_path = CODE_PATH

    # 2. Scan Files
    files = sorted([f for f in source_path.rglob("*") if f.suffix.lower() in (".f90", ".f", ".for", ".f95")])
    print(f"Analyzing {len(files)} files...")

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

    print("Resolving dependencies with Scope...")

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
            if not (CODE_PATH / target).exists():
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

    # 4. CSV File Generation

    # A. Master
    if master_rows:
        keys = [
            "Source_File",
            "Source_Unit",
            "Source_Type",
            "Dep_Type",
            "Target_Unit",
            "Target_Type",
            "Target_File",
            "Source_Line",
        ]
        with open(MASTER_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(master_rows)
        print(f"Generated:{MASTER_OUT}")

    # B. Units Graph
    if graph_edges:
        with open(GRAPH_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "Source_Unit",
                    "Source_Type",
                    "Target_Unit",
                    "Target_Type",
                    "Dep_Type",
                    "Target_File",
                    "Weight",
                ]
            )
            for row in sorted(list(graph_edges)):
                # (source_unit, dest_unit, source_type, dest_type)
                key = (row[0], row[2], row[1], row[3])
                weight = edges_counter[key]
                rowt = row + (weight,)
                w.writerow(rowt)
        print(f"Generated:{GRAPH_OUT}")

    # C. Impact Matrix
    all_units = set(impact_fan_out.keys()) | set(impact_fan_in.keys())
    if all_units:
        # Recover types for the matrix (looking up in inventory or inferred)
        rows_impact = []
        for u in sorted(all_units):
            # Type? Look up in inventory. If not found, it may be an Implicit Main
            utype = "UNKNOWN"
            file = "N/A"

            if u.startswith("MAIN__"):
                report_type = "IMPLICIT-MAIN"
                # Optional: try to recover the filename from the MAIN__ string
                files_report = u.replace("MAIN__", "")
            else:
                candidates = inventory.get(u)  # Esto devuelve una LISTA o None
                if candidates:
                    detected_types = sorted(list(set(d["type"] for d in candidates)))
                    report_type = "/".join(detected_types)

                    files_list = [d["file"] for d in candidates]
                    files_report = "; ".join(sorted(set(files_list)))

            rows_impact.append(
                {
                    "Unit": u,
                    "Type": report_type,
                    "File": files_report,
                    "Fan_Out": impact_fan_out.get(u, 0),
                    "Fan_In": impact_fan_in.get(u, 0),
                }
            )

        with open(IMPACT_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["Unit", "Type", "File", "Fan_Out", "Fan_In"])
            w.writeheader()
            w.writerows(rows_impact)
        print(f"Generated:{IMPACT_OUT}")

    # D. Orphans
    if orphans_set:
        with open(ORPHANS_OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Target_Unit", "Dep_Type", "Status"])
            for u, t in sorted(list(orphans_set)):
                w.writerow([u, t, "EXTERNAL_OR_LIBRARY"])
        print(f"Generated:{ORPHANS_OUT}")

    # E. File Dependencies
    if file_deps_map:
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

        with open(DEPENDS_OUT, "w", newline="", encoding="utf-8") as f:
            keys = ["Source_File", "Target_File", "Strong_Nature", "Nature_List", "Detail_Types"]
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(file_rows)
        print(f"Generated:{DEPENDS_OUT}")

        # dep_06: INCLUDE file references — one row per INCLUDE statement
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
            estado = "PRESENT" if (CODE_PATH / target).exists() else "MISSING"
            include_rows.append(
                {
                    "Source_File": item["source_file"],
                    "Source_Unit": item["source_unit"],
                    "Included_File": target,
                    "Status": estado,
                }
            )
        include_rows.sort(key=lambda r: (r["Source_File"], r["Source_Unit"]))

        with open(INCLUDES_OUT, "w", newline="", encoding="utf-8") as f:
            keys = ["Source_File", "Source_Unit", "Included_File", "Status"]
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(include_rows)
        print(f"Generated: {INCLUDES_OUT} ({len(include_rows)} INCLUDE references)")


if __name__ == "__main__":
    main()
