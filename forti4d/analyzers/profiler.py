import os
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

# --- PROJECT IMPORTS ---
import forti4d.lib.reader_logical as reader_logical
import forti4d.lib.patterns_v2 as patterns
import forti4d.lib.kinds as kinds

# Use the new master function we just defined
from forti4d.analyzers.inventory import load_inventory

# =============================================================================
# CONFIGURATION
# =============================================================================
from forti4d.config import CODE_PATH, RESULTS_PATH

CSV_OUTPUT = RESULTS_PATH / "report_density.csv"
AUDIT_PATH = RESULTS_PATH / "audit"

# =============================================================================
# DENSITY GROUPS
# =============================================================================
CALCULATION_GROUP = kinds.CALCULATION_ACTIONS | {kinds.StatementKind.ASSIGNMENT_STMT}
CONTROL_GROUP = kinds.EXECUTABLE_CONSTRUCTS | {
    kinds.StatementKind.CONTROL_STMT,
    kinds.StatementKind.ELSE_STMT,
    kinds.StatementKind.CASE_STMT,
}
IO_GROUP = kinds.IO_ACTIONS
LEGACY_GROUP = kinds.LEGACY_DATA
DECLAR_GROUP = {
    kinds.StatementKind.VAR_DECLARATION,
    kinds.StatementKind.PARAMETER_STMT,
    kinds.StatementKind.IMPLICIT_STMT,
    kinds.StatementKind.USE_STMT,
    kinds.StatementKind.IMPORT_STMT,
    kinds.StatementKind.TYPE_DEFINITION,
    kinds.StatementKind.ENUM_DEF,
    kinds.StatementKind.INTERFACE_BLOCK,
    kinds.StatementKind.CONTAINS_STMT,
    kinds.StatementKind.END_BLOCK_STMT,
}

# =============================================================================
# PATTERN MAP (Same as before, verified)
# =============================================================================
PATTERN_MAP = [
    (
        patterns.RE_END_BLOCK,
        kinds.StatementKind.END_BLOCK_STMT,
    ),  # Closings first: prevents any opener from capturing an END
    (patterns.RE_PROGRAM, kinds.StatementKind.PROGRAM_UNIT),
    (patterns.RE_MODULE, kinds.StatementKind.MODULE_UNIT),
    (patterns.RE_SUBROUTINE, kinds.StatementKind.SUBROUTINE_UNIT),
    (patterns.RE_FUNCTION, kinds.StatementKind.FUNCTION_UNIT),
    (patterns.RE_BLOCK_DATA, kinds.StatementKind.BLOCK_DATA_UNIT),
    (patterns.RE_INTERFACE, kinds.StatementKind.INTERFACE_BLOCK),
    (patterns.RE_MODULE_PROCEDURE, kinds.StatementKind.INTERFACE_BLOCK),
    (patterns.RE_TYPE_DEF, kinds.StatementKind.TYPE_DEFINITION),
    (patterns.RE_ENUM_DEF, kinds.StatementKind.ENUM_DEF),
    (patterns.RE_CONTAINS, kinds.StatementKind.CONTAINS_STMT),
    (patterns.RE_COMMON, kinds.StatementKind.COMMON_STMT),
    (patterns.RE_EQUIVALENCE, kinds.StatementKind.EQUIVALENCE_STMT),
    (patterns.RE_DATA, kinds.StatementKind.DATA_STMT),
    (patterns.RE_NAMELIST, kinds.StatementKind.NAMELIST_STMT),
    (patterns.RE_IF_BLOCK, kinds.StatementKind.IF_CONSTRUCT),
    (patterns.RE_DO_LOOP, kinds.StatementKind.DO_CONSTRUCT),
    (patterns.RE_SELECT_CASE, kinds.StatementKind.SELECT_CONSTRUCT),
    (patterns.RE_ASSOCIATE, kinds.StatementKind.ASSOCIATE_CONSTRUCT),
    (patterns.RE_BLOCK_CONST, kinds.StatementKind.BLOCK_CONSTRUCT),
    (patterns.RE_CRITICAL, kinds.StatementKind.CRITICAL_CONSTRUCT),
    (patterns.RE_WHERE_BLOCK, kinds.StatementKind.WHERE_CONSTRUCT),
    (patterns.RE_FORALL_BLOCK, kinds.StatementKind.FORALL_CONSTRUCT),
    (patterns.RE_ELSE, kinds.StatementKind.ELSE_STMT),
    (patterns.RE_CASE, kinds.StatementKind.CASE_STMT),
    (patterns.RE_USE, kinds.StatementKind.USE_STMT),
    (patterns.RE_IMPORT, kinds.StatementKind.IMPORT_STMT),
    (patterns.RE_IMPLICIT, kinds.StatementKind.IMPLICIT_STMT),
    (patterns.RE_VAR_DECL, kinds.StatementKind.VAR_DECLARATION),
    (patterns.RE_PARAMETER, kinds.StatementKind.PARAMETER_STMT),
    (patterns.RE_ATTR_SPEC, kinds.StatementKind.VAR_DECLARATION),
    (patterns.RE_ALLOCATE, kinds.StatementKind.ALLOCATION_STMT),
    (patterns.RE_DEALLOCATE, kinds.StatementKind.ALLOCATION_STMT),
    (patterns.RE_POINTER_OP, kinds.StatementKind.POINTER_ACTION),
    (patterns.RE_IO, kinds.StatementKind.IO_STMT),
    (patterns.RE_CONTROL, kinds.StatementKind.CONTROL_STMT),
    (patterns.RE_INCLUDE, kinds.StatementKind.INCLUDE_STMT),
    (patterns.RE_ARITHMETIC_IF, kinds.StatementKind.CONTROL_STMT),
    (patterns.RE_IF_SINGLE, kinds.StatementKind.IF_CONSTRUCT),
    (patterns.RE_WHERE_SINGLE, kinds.StatementKind.WHERE_CONSTRUCT),
    (patterns.RE_FORALL_SINGLE, kinds.StatementKind.FORALL_CONSTRUCT),
]


def mask_strings(line: str) -> str:
    """Avoids false positives in strings."""
    pattern = r"('([^']*)'|\"([^\"]*)\")"

    def replacer(match):
        full = match.group(0)
        return full[0] + "_" * (len(full) - 2) + full[-1]

    return re.sub(pattern, replacer, line)


def classify_line(logical_line: str):
    clean_line = mask_strings(logical_line)
    for pattern, kind in PATTERN_MAP:
        if pattern.match(clean_line):
            return kind

    if "=" in clean_line:
        temp = clean_line.replace("==", "").replace("=>", "").replace(">=", "").replace("<=", "")
        if "=" in temp:
            return kinds.StatementKind.ASSIGNMENT_STMT

    return kinds.StatementKind.UNKNOWN


def analyze_density():
    print("STARTING DENSITY PROFILING (V3 Audited)")

    files_path = CODE_PATH
    if not files_path.exists():
        print(f"ERROR: Directory {CODE_PATH} does not exist")
        return

    # 1. Load Inventory using the function in inventory.py
    # This returns a list of dicts with keys 'File', 'Start_Line', etc.
    try:
        inventory_list = load_inventory()
        print(f"Inventory loaded: {len(inventory_list)} total records.")
    except ImportError:
        print("ERROR: Function 'load_inventory' not found in inventory.py.")
        return
    except Exception as e:
        print(f"Error loading inventory: {e}")
        return

    if not inventory_list:
        print("Inventory is empty or could not be read.")
        return

    # 2. Group units by File to avoid inefficient iterations
    # Key: Filename (str) -> Value: List of unit dicts
    map_units_file = defaultdict(list)
    for u in inventory_list:
        rel = u.get("Relative_Path") or u.get("File", "")
        if rel:
            map_units_file[rel].append(u)

    output_data = []

    audit_path_ = AUDIT_PATH
    audit_path_.mkdir(parents=True, exist_ok=True)

    # Sort files alphabetically for the report
    sorted_files = sorted(map_units_file.keys(), key=lambda x: x.lower())

    for idx, rel_path in enumerate(sorted_files):
        file_name = Path(rel_path).name
        print(f"[{idx+1}/{len(sorted_files)}] Processing: {file_name}")

        # Get the units that belong to this file
        units_on_file = map_units_file[rel_path]

        # Sort by Start_Line for scope resolution
        # NOTE: We use the correct key 'Start_Line'
        units_on_file.sort(key=lambda x: x["Start_Line"])

        # Build physical path using relative path to support subdirectories
        physical_path = files_path / rel_path

        # Read logical lines
        try:
            sentences = reader_logical.read_logical_lines(physical_path)
        except Exception as e:
            print(f"  -> Read error/File not found: {e}")
            continue

        counters = defaultdict(Counter)
        debug_rows = []

        # 3. Classification and Assignment
        for sentence in sentences:
            if sentence.is_comment:
                debug_rows.append(
                    {
                        "Line": sentence.start_line,
                        "Kind": str(kinds.StatementKind.COMMENT).split(".")[1],  # Convert Enum to readable string
                        "Content": sentence.text[:120],  # First 120 chars to avoid overflow
                    }
                )
                continue

            content = sentence.text.strip()

            if sentence.label:
                # Use regex to safely remove the label at the beginning of the string
                # Match: start + label + spaces
                content = re.sub(r"^\s*" + re.escape(sentence.label) + r"\s+", "", content, count=1)

            if not content:
                debug_rows.append(
                    {
                        "Line": sentence.start_line,
                        "Kind": str(kinds.StatementKind.BLANK_LINE).split(".")[1],  # Convert Enum to readable string
                        "Content": "",
                    }
                )
                continue

            # Use start_line as defined in LogicalLine
            n_line = sentence.start_line

            # Scope Resolution: Which unit owns this line?
            unit_name = "GLOBAL"

            # Find the innermost unit that contains n_line (Start <= n <= End)
            candidates = [u for u in units_on_file if u["Start_Line"] <= n_line <= u["End_Line"]]

            if candidates:
                # The innermost is the one that started latest (highest Start_Line)
                unit_name = max(candidates, key=lambda u: u["Start_Line"])["Name"]

            kind = classify_line(content)
            counters[unit_name][kind] += 1

            if kind == kinds.StatementKind.IO_STMT:
                lower = mask_strings(content.lower())
                if re.match(r"^\s*print\b", lower):
                    counters[unit_name]["_IO_PRINT"] += 1
                elif re.match(r"^\s*write\b", lower):
                    counters[unit_name]["_IO_WRITE"] += 1
                # Note: To count READ, OPEN, etc., add them here.

            # --- AUDIT: Save data ---
            # We save: Line, Classification, Content (truncated for readability)
            debug_rows.append(
                {
                    "Line": n_line,
                    "Kind": str(kind).split(".")[1],  # Convert Enum to readable string
                    "Content": sentence.text[:120],  # First 120 chars to avoid overflow
                }
            )

        # AUDIT
        # --- AT THE END OF FILE PROCESSING ---
        # Generate debug CSV name using sanitized relative path to avoid
        # basename collisions when source files share names across subdirectories.
        debug_stem = rel_path.replace("/", "__").replace("\\", "__")
        debug_name = f"{debug_stem}_DEBUG.csv"
        debug_path = audit_path_ / debug_name

        # Write to disk
        try:
            with open(debug_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["Line", "Kind", "Content"])
                writer.writeheader()
                writer.writerows(debug_rows)
            print(f"  -> Audit saved to: {debug_path}")
        except Exception as e:
            print(f"  -> Error saving debug: {e}")

        # 4. Consolidation

        # Add GLOBAL if code was detected outside of units
        if "GLOBAL" in counters:
            if not any(u["Name"] == "GLOBAL" for u in units_on_file):
                # Create a dummy unit for the report
                units_on_file.insert(0, {"Name": "GLOBAL", "Type": "FILE_SCOPE", "Start_Line": 0})

        for u in units_on_file:
            unit_name = u["Name"]
            unit_type = u.get("Type", "UNKNOWN")

            c = counters[unit_name]
            total_sentences = sum(c.values())

            # Sumas
            n_calcula = sum(c[k] for k in CALCULATION_GROUP if k in c)
            n_control = sum(c[k] for k in CONTROL_GROUP if k in c)
            n_io = sum(c[k] for k in IO_GROUP if k in c)
            n_legacy = sum(c[k] for k in LEGACY_GROUP if k in c)
            n_declar = sum(c[k] for k in DECLAR_GROUP if k in c)

            # Percentages
            pct = lambda x: round((x / total_sentences) * 100, 1) if total_sentences > 0 else 0.0

            fila = {
                "File": file_name,
                "Unit": unit_name,
                "Type": unit_type,
                "Total_Statements": total_sentences,
                "Total_Calc": n_calcula,
                "Total_Control": n_control,
                "Total_IO": n_io,
                "Total_Legacy": n_legacy,
                "Total_Decl": n_declar,
                "Pct_Calc": pct(n_calcula),
                "Pct_Control": pct(n_control),
                "Pct_IO": pct(n_io),
                "Pct_Legacy": pct(n_legacy),
                "Pct_Decl": pct(n_declar),
                "N_Common": c[kinds.StatementKind.COMMON_STMT],
                "N_Equiv": c[kinds.StatementKind.EQUIVALENCE_STMT],
                "N_Print": c["_IO_PRINT"],
                "N_Write": c["_IO_WRITE"],
            }
            output_data.append(fila)

    # 5. Export
    headers = [
        "File",
        "Unit",
        "Type",
        "Total_Statements",
        "Total_Calc",
        "Total_Control",
        "Total_IO",
        "Total_Legacy",
        "Total_Decl",
        "Pct_Calc",
        "Pct_Control",
        "Pct_IO",
        "Pct_Legacy",
        "Pct_Decl",
        "N_Common",
        "N_Equiv",
        "N_Print",
        "N_Write",
    ]

    try:
        with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(output_data)
        print(f"\nREPORT GENERATED: {CSV_OUTPUT}")
    except Exception as e:
        print(f"Error writing CSV: {e}")


if __name__ == "__main__":
    analyze_density()
