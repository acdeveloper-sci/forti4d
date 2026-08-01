"""
clones.py
Compares same-named units across files to detect whether they are identical,
similar, or diverged copies.

Reads the duplicate-unit list from dep_00_ambiguities.csv, extracts and
normalizes the source of each unit, and performs pairwise comparison.

Output: report_clones.csv  — one row per (unit, file_A, file_B) pair.
"""

import csv
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from loguru import logger

from forti4d.analyzers.inventory import load_inventory
from forti4d.lib.reader_logical import read_logical_lines
from forti4d import config

# Umbral de similitud: >= este valor → SIMILAR; == 1.0 → IDENTICO
SIMILAR_THRESHOLD = 0.80


# =============================================================================
# EXTRACTION AND NORMALIZATION
# =============================================================================


def build_file_index(path: Path) -> dict:
    """Returns dict: relative_path_string → full Path for all Fortran source files."""
    index = {}
    for f in path.rglob("*"):
        if f.suffix.lower() in (".f90", ".f", ".for", ".f77", ".f95", ".f03"):
            index[str(f.relative_to(path))] = f
    return index


def _extract_from_cache(path: Path, start: int, end: int, cache: dict) -> list:
    """
    Returns normalized logical lines for the unit at [start, end], using
    cache to avoid re-parsing the same file multiple times within a run.
    """
    if path not in cache:
        try:
            cache[path] = read_logical_lines(str(path))
        except Exception:
            cache[path] = []
    result = []
    for ll in cache[path]:
        if ll.start_line < start:
            continue
        if ll.start_line > end:
            break
        if ll.is_comment or not ll.text.strip():
            continue
        result.append(" ".join(ll.text.upper().split()))
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


def analyze_clones(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes. Returns an empty list when there are
    no results (inventory empty, no ambiguities, or no groups with >= 2 files),
    which causes write_clones to write a headers-only CSV."""
    inputs = inputs or {}
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # Load inventory
    inventory_list = load_inventory(
        rows=inputs.get("inventory_report"), csv_path=Path(results_dir) / "inventory_report.csv"
    )
    if not inventory_list:
        logger.warning("ERROR: inventory is empty. Run inventory.py first.")
        return {"report_clones": []}

    # Index: (relative_path, name_upper) → {type, start, end}
    inv_idx = {}
    for row in inventory_list:
        key = (row.get("Relative_Path", row["File"]), row["Name"].upper())
        inv_idx[key] = {
            "type": row["Type"],
            "start": int(row["Start_Line"]),
            "end": int(row["End_Line"]),
        }

    # Load ambiguities — absence means no duplicate names in the corpus (not an error)
    ambiguities_rows = inputs.get("dep_00_ambiguities")
    if ambiguities_rows is None:
        ambiguities_path = Path(results_dir) / "dep_00_ambiguities.csv"
        if not ambiguities_path.exists():
            logger.info("No ambiguous unit names found — skipping clone comparison.")
            return {"report_clones": []}
        with open(ambiguities_path, encoding="utf-8-sig") as f:
            ambiguities_rows = list(csv.DictReader(f))

    groups = []  # [(name, utype, [rel_path1, rel_path2, ...])]
    for row in ambiguities_rows:
        name = row["Unit_Name"].strip().upper()
        utype = row["Type"].strip()
        files = [a.strip() for a in row["File_List"].split(";") if a.strip()]
        if len(files) >= 2:
            groups.append((name, utype, files))

    if not groups:
        logger.info("No duplicate units found.")
        return {"report_clones": []}

    # Build file path index: relative_path_string → full Path
    file_idx = build_file_index(source_dir)

    # Pairwise comparisons with per-run file parse cache
    _parse_cache = {}
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

                lines_a = _extract_from_cache(path_a, info_a["start"], info_a["end"], _parse_cache)
                lines_b = _extract_from_cache(path_b, info_b["start"], info_b["end"], _parse_cache)

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

    return {"report_clones": rows, "n_groups": len(groups)}


def write_clones(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    rows = data["report_clones"]
    columns = ["Unit", "Type", "File_A", "File_B", "SLOC_A", "SLOC_B", "Similarity_Pct", "Status"]

    output_file = Path(results_dir) / "report_clones.csv"

    if not rows:
        _write_empty_csv(output_file, columns)
        return

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)

    n_id = sum(1 for r in rows if r["Status"] == "IDENTICAL")
    n_sim = sum(1 for r in rows if r["Status"] == "SIMILAR")
    n_div = sum(1 for r in rows if r["Status"] == "DIVERGED")

    logger.info(f"{len(rows)} pairs compared  ({data['n_groups']} units with duplicates)")
    logger.info(f"  IDENTICAL : {n_id}")
    logger.info(f"  SIMILAR   : {n_sim}")
    logger.info(f"  DIVERGED  : {n_div}")
    logger.success(f"Generated: {output_file}")


def _write_empty_csv(path, columns):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=columns).writeheader()


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_clones(source_dir, results_dir, inputs=inputs)
    write_clones(results_dir, data)
    return data


if __name__ == "__main__":
    main()
