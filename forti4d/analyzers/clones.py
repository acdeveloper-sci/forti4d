"""
clones.py
Compares same-named units across files to detect whether they are identical,
similar, or diverged copies.

Reads the duplicate-unit list from dep_00_ambiguities.csv, extracts and
normalizes the source of each unit, and performs pairwise comparison.

Output: report_clones.csv  — one row per (unit, file_A, file_B) pair.
"""

import csv
import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from forti4d.analyzers.inventory import load_inventory
from forti4d.lib.reader_logical import read_logical_lines
from forti4d.config import CODE_PATH, RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
AMBIGUITIES_PATH = RESULTS_PATH / "dep_00_ambiguities.csv"
CSV_OUTPUT = RESULTS_PATH / "report_clones.csv"

# Umbral de similitud: >= este valor → SIMILAR; == 1.0 → IDENTICO
SIMILAR_THRESHOLD = 0.80


# =============================================================================
# EXTRACTION AND NORMALIZATION
# =============================================================================


def build_file_index(path: Path) -> dict:
    """Returns dict: basename → full Path for all Fortran source files."""
    index = {}
    for f in path.rglob("*"):
        if f.suffix.lower() in (".f90", ".f", ".for", ".f77", ".f95", ".f03"):
            index[f.name] = f
    return index


def extract_lines_unit(path: Path, start: int, end: int) -> list:
    """
    Reads a Fortran source file and returns the normalized logical lines
    belonging to the unit at [start, end].

    Normalization: comments and blank lines removed, whitespace collapsed,
    text uppercased.
    """
    try:
        logical_lines = read_logical_lines(str(path))
    except Exception:
        return []

    result = []
    for ll in logical_lines:
        if ll.start_line < start:
            continue
        if ll.start_line > end:
            break
        if ll.is_comment or not ll.text.strip():
            continue
        standardized = " ".join(ll.text.upper().split())
        result.append(standardized)
    return result


def similarity(lines_a: list, lines_b: list) -> float:
    if not lines_a and not lines_b:
        return 1.0
    if not lines_a or not lines_b:
        return 0.0
    return SequenceMatcher(None, lines_a, lines_b).ratio()


def classify(ratio: float) -> str:
    if ratio >= 1.0:
        return "IDENTICAL"
    if ratio >= SIMILAR_THRESHOLD:
        return "SIMILAR"
    return "DIVERGED"


# =============================================================================
# MAIN
# =============================================================================


def main():
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)

    # Load inventory
    inventory_list = load_inventory()
    if not inventory_list:
        print("ERROR: inventory is empty. Run inventory.py first.")
        return

    # Index: (file_basename, name_upper) → {type, start, end}
    inv_idx = {}
    for row in inventory_list:
        key = (row["File"], row["Name"].upper())
        inv_idx[key] = {
            "type": row["Type"],
            "start": int(row["Start_Line"]),
            "end": int(row["End_Line"]),
        }

    # Load ambiguedades
    if not AMBIGUITIES_PATH.exists():
        print(f"ERROR: {AMBIGUITIES_PATH} not found. Run dependencies.py first.")
        return

    groups = []  # [(name, utype, [file1, file2, ...])]
    with open(AMBIGUITIES_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row["Unit_Name"].strip().upper()
            utype = row["Type"].strip()
            files = [a.strip() for a in row["File_List"].split(";") if a.strip()]
            if len(files) >= 2:
                groups.append((name, utype, files))

    if not groups:
        print("No duplicate units found.")
        _wrtite_empty_csv()
        return

    # Build file path index
    file_idx = build_file_index(CODE_PATH)

    # Pairwise comparisons
    rows = []
    for name, utype, files in groups:
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                file_a = files[i]
                file_b = files[j]

                info_a = inv_idx.get((file_a, name))
                info_b = inv_idx.get((file_b, name))
                if not info_a or not info_b:
                    continue

                path_a = file_idx.get(file_a)
                path_b = file_idx.get(file_b)
                if not path_a or not path_b:
                    continue

                lines_a = extract_lines_unit(path_a, info_a["start"], info_a["end"])
                lines_b = extract_lines_unit(path_b, info_b["start"], info_b["end"])

                ratio = similarity(lines_a, lines_b)
                status = classify(ratio)

                rows.append(
                    {
                        "Unit": name,
                        "Type": utype,
                        "File_A": file_a,
                        "File_B": file_b,
                        "SLOC_A": len(lines_a),
                        "SLOC_B": len(lines_b),
                        "Similarity_Pct": round(ratio * 100, 1),
                        "Status": status,
                    }
                )

    # Sort: diverged first, then similar, then identical; then by name
    _order = {"DIVERGED": 0, "SIMILAR": 1, "IDENTICAL": 2}
    rows.sort(key=lambda r: (_order[r["Status"]], r["Unit"]))

    columns = ["Unit", "Type", "File_A", "File_B", "SLOC_A", "SLOC_B", "Similarity_Pct", "Status"]
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    n_id = sum(1 for r in rows if r["Status"] == "IDENTICAL")
    n_sim = sum(1 for r in rows if r["Status"] == "SIMILAR")
    n_div = sum(1 for r in rows if r["Status"] == "DIVERGED")

    print(f"\n{len(rows)} pairs compared  ({len(groups)} units with duplicates)")
    print(f"  IDENTICAL : {n_id}")
    print(f"  SIMILAR   : {n_sim}")
    print(f"  DIVERGED  : {n_div}")
    print(f"\nGenerated: {CSV_OUTPUT}")


def _wrtite_empty_csv():
    columns = ["Unit", "Type", "File_A", "File_B", "SLOC_A", "SLOC_B", "Similarity_Pct", "Status"]
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=columns).writeheader()


if __name__ == "__main__":
    main()
