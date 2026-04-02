import sys
import os
import csv
from collections import defaultdict
from forti4d.config import RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
IMPACT_FILE = RESULTS_PATH / "dep_03_impact_matrix.csv"
INVENTORY_FILE = RESULTS_PATH / "inventory_report.csv"
OUTPUT_FILE = RESULTS_PATH / "report_structure_analysis.csv"

# How many incoming calls make a unit "CRITICAL"?
CRITICAL_THRESHOLD = 10


def load_matrix():
    if not IMPACT_FILE.exists():
        print(f"ERROR: '{IMPACT_FILE}' does not exist. Run dependencies.py first.")
        sys.exit(1)

    data_per_file = defaultdict(list)

    print(f"Reading {IMPACT_FILE}...")
    with open(IMPACT_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            file = row.get("File", "N/A").strip()

            # Filter out invalid or multi-file entries
            if file in ("N/A", "EXTERNAL/LOCAL", "MULTIPLE_CANDIDATES") or ";" in file:
                continue

            try:
                fan_in = int(row.get("Fan_In", 0))
                fan_out = int(row.get("Fan_Out", 0))
            except ValueError:
                continue

            data_per_file[file].append(
                {
                    "Unit": row.get("Unit", "UNKNOWN"),
                    "Type": row.get("Type", "UNKNOWN").upper(),
                    "Fan_In": fan_in,
                    "Fan_Out": fan_out,
                }
            )

    return data_per_file


def load_inventory_files():
    """
    Returns the set of all known files and whether they contain
    any IMPLICIT-MAIN unit (for later categorization).
    """
    known_files = set()
    files_with_implicit_main = set()

    if not INVENTORY_FILE.exists():
        print(f"Warning: '{INVENTORY_FILE}' does not exist. ISLANDs will not be detected.")
        return known_files, files_with_implicit_main

    with open(INVENTORY_FILE, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            file = row.get("File", "").strip()
            if file:
                known_files.add(file)
                if row.get("Type", "").upper() == "IMPLICIT-MAIN":
                    files_with_implicit_main.add(file)

    return known_files, files_with_implicit_main


def classify_file(file_name, units, has_implicit_main):
    """
    Determines the architectural role of the file.
    """
    total_units = len(units)

    if total_units > 0:
        fan_in_max = units[0]["Fan_In"]
        unit_max_in = units[0]["Unit"]
        fan_out_max = units[0]["Fan_Out"]
        unit_max_out = units[0]["Unit"]
    else:
        fan_in_max = 0
        unit_max_in = "N/A"
        fan_out_max = 0
        unit_max_out = "N/A"

    sum_fan_in = 0
    sum_fan_out = 0
    has_main = False

    for u in units:
        fi = u["Fan_In"]
        fo = u["Fan_Out"]

        sum_fan_in += fi
        sum_fan_out += fo

        if fi > fan_in_max:
            fan_in_max = fi
            unit_max_in = u["Unit"]

        if fo > fan_out_max:
            fan_out_max = fo
            unit_max_out = u["Unit"]

        type_str = u["Type"]
        if "PROGRAM" in type_str or "IMPLICIT-MAIN" in type_str:
            has_main = True

    # Categorization — explicit priority order
    category = "MIXED"
    detail = "Standard functionality"

    # Files with an implicit main program: they are entry-point executables,
    # not library routines — categorized separately
    if has_implicit_main:
        category = "ENTRY_POINT"
        detail = f"Implicit main program (Fan-Out: {fan_out_max})"

    elif sum_fan_in == 0 and sum_fan_out == 0:
        # We will never reach here from dep_03 (ISLANDs have no entries in the matrix),
        # but we can from files injected as ISLAND in main().
        category = "ISLAND"
        detail = "Isolated file (possible dead code)"

    elif fan_in_max >= CRITICAL_THRESHOLD:
        category = "CRITICAL_NODE"
        detail = f"High centrality (Max Fan-In: {fan_in_max})"

    elif fan_out_max >= CRITICAL_THRESHOLD:
        category = "ORCHESTRATOR"
        detail = f"Flow controller (Max Fan-Out: {fan_out_max})"

    elif (sum_fan_in > 0 or sum_fan_out > 0) and fan_out_max < 5:
        # WORKER: connected but low outgoing impact.
        # Fan_In=0 is acceptable if it at least calls something (low-order pure caller).
        category = "WORKER"
        detail = "Service or calculation routine"

    return {
        "File": file_name,
        "Category": category,
        "Fan_In_Max": fan_in_max,
        "Unit_Max_In": unit_max_in,
        "Fan_Out_Max": fan_out_max,
        "Unit_Max_Out": unit_max_out,
        "Total_Units": total_units,
        "Has_Main": "YES" if has_main else "NO",
        "Detail": detail,
    }


def main():
    print(f"--- Architecture Analysis (Threshold: {CRITICAL_THRESHOLD}) ---")

    data = load_matrix()
    known_files, files_with_implicit_main = load_inventory_files()

    if not data and not known_files:
        print("No data found to process.")
        return

    results = []
    counts = defaultdict(int)

    processed_files = set()

    for file, units in data.items():
        has_implicit_main = file in files_with_implicit_main
        res = classify_file(file, units, has_implicit_main)
        results.append(res)
        counts[res["Category"]] += 1
        processed_files.add(file)

    # Inventory files that have no entry in dep_03 → ISLANDs
    for file in sorted(known_files - processed_files):
        res = {
            "File": file,
            "Category": "ISLAND",
            "Fan_In_Max": 0,
            "Unit_Max_In": "N/A",
            "Fan_Out_Max": 0,
            "Unit_Max_Out": "N/A",
            "Total_Units": 0,
            "Has_Main": "NO",
            "Detail": "File with no connections in the impact matrix",
        }
        results.append(res)
        counts["ISLAND"] += 1

    # Hierarchical order for the report
    priority = {"CRITICAL_NODE": 1, "ORCHESTRATOR": 2, "ENTRY_POINT": 3, "MIXED": 4, "WORKER": 5, "ISLAND": 6}
    results.sort(key=lambda x: priority.get(x["Category"], 99))

    columns = [
        "File",
        "Category",
        "Fan_In_Max",
        "Unit_Max_In",
        "Fan_Out_Max",
        "Unit_Max_Out",
        "Total_Units",
        "Has_Main",
        "Detail",
    ]

    try:
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(results)

        print(f"Report generated successfully: {OUTPUT_FILE}")
        print("\nCategory Statistics:")
        for cat in priority:
            count = counts.get(cat, 0)
            if count:
                print(f"  - {cat:15}: {count}")

    except IOError as e:
        print(f"Error writing the report: {e}")


if __name__ == "__main__":
    main()
