import os
import csv
from collections import defaultdict
from pathlib import Path

from loguru import logger

from forti4d.analyzers.inventory import load_inventory
from forti4d import config


# =============================================================================
# CYCLOMATIC COMPLEXITY LOGIC
# =============================================================================


def count_decision_point(kind: str, content: str) -> int:
    """
    Returns 1 if the statement is a decision point, 0 otherwise.

    Rules (simplified McCabe):
      IF_CONSTRUCT     → +1  (block IF and single-line IF)
      ELSE_STMT        → +1  only if ELSE IF / ELSEIF (plain ELSE = 0)
      DO_CONSTRUCT     → +1  (DO, DO WHILE, labeled DO)
      SELECT_CONSTRUCT → +0  (CASE branches already account for paths)
      CASE_STMT        → +1  except CASE DEFAULT / CLASS DEFAULT
      WHERE_CONSTRUCT  → +1
      FORALL_CONSTRUCT → +1
    """
    lower = content.strip().lower()

    if kind == "IF_CONSTRUCT":
        return 1

    if kind == "ELSE_STMT":
        # "else if ..." and "elseif..." are decision points; "else" and
        # "elsewhere" are not.
        return 1 if (lower.startswith("else if") or lower.startswith("elseif")) else 0

    if kind == "DO_CONSTRUCT":
        return 1

    if kind == "SELECT_CONSTRUCT":
        return 0

    if kind == "CASE_STMT":
        # CASE DEFAULT and CLASS DEFAULT are the implicit path (equiv. to ELSE).
        if lower.startswith("case default") or lower.startswith("class default"):
            return 0
        return 1

    if kind == "WHERE_CONSTRUCT":
        return 1

    if kind == "FORALL_CONSTRUCT":
        return 1

    return 0


def interpret_cc(cc: int) -> str:
    if cc <= 10:
        return "LOW"
    if cc <= 20:
        return "MEDIUM"
    if cc <= 50:
        return "HIGH"
    return "CRITICAL"


# =============================================================================
# MAIN ANALYSIS
# =============================================================================


def analyze_complexity(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes. Returns None for report_complexity
    when there's nothing to process (same as the original — no file is
    written in that case either)."""
    inputs = inputs or {}
    logger.debug("--- McCabe Cyclomatic Complexity ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory(
            rows=inputs.get("inventory_report"), csv_path=Path(results_dir) / "inventory_report.csv"
        )
    except Exception as e:
        logger.warning(f"ERROR loading inventory: {e}")
        return {"report_complexity": None}

    if not inventory_list:
        logger.warning("Inventory is empty.")
        return {"report_complexity": None}

    logger.info(f"Inventory loaded: {len(inventory_list)} units.")

    # Convert numeric types and group by file
    units_file_map = defaultdict(list)
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
        units_file_map[rel].append(u)

    output_data = []
    audit_data = inputs.get("audit")  # {rel_path: debug_rows}, from profiler.py — avoids re-reading from disk
    audit_path_ = Path(results_dir) / "audit"

    sorted_files = sorted(units_file_map.keys(), key=str.lower)

    for idx, rel_path in enumerate(sorted_files):
        file_name = Path(rel_path).name

        debug_rows = audit_data.get(rel_path) if audit_data is not None else None
        if debug_rows is None:
            debug_stem = rel_path.replace("/", "__").replace("\\", "__")
            debug_file = audit_path_ / f"{debug_stem}_DEBUG.csv"
            if not debug_file.exists():
                logger.warning(f"  [{idx+1}] No DEBUG file: {file_name} — skipped")
                continue
            with open(debug_file, encoding="utf-8-sig") as f:
                debug_rows = list(csv.DictReader(f))

        units_per_file = units_file_map[rel_path]
        units_per_file.sort(key=lambda u: u["Start_Line"])

        # Accumulators: each unit starts with base CC = 1
        score = defaultdict(int)

        for row in debug_rows:
            try:
                n_line = int(row["Line"])
            except ValueError:
                continue

            kind = row.get("Kind", "")
            content = row.get("Content", "")

            delta = count_decision_point(kind, content)
            if not delta:
                continue

            # Scope resolution: innermost unit containing n_line
            candidates = [u for u in units_per_file if u["Start_Line"] <= n_line <= u["End_Line"]]
            if not candidates:
                continue
            scope = max(candidates, key=lambda u: u["Start_Line"])["Name"]

            score[scope] += delta

        # Build output rows for each unit in the file
        for u in units_per_file:
            uname = u["Name"]
            cc = 1 + score[uname]
            output_data.append(
                {
                    "File": file_name,
                    "Unit": uname,
                    "Type": u.get("Type", "UNKNOWN"),
                    "CC": cc,
                    "Level": interpret_cc(cc),
                    "Start_Line": u["Start_Line"],
                    "End_Line": u["End_Line"],
                    "Total_Lines": u.get("Total_Lines", 0),
                }
            )

    # 3. Sort by CC descending
    output_data.sort(key=lambda x: -x["CC"])

    return {"report_complexity": output_data}


def write_complexity(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    output_data = data["report_complexity"]
    if output_data is None:
        return

    columns = [
        "File",
        "Unit",
        "Type",
        "CC",
        "Level",
        "Start_Line",
        "End_Line",
        "Total_Lines",
    ]
    output_file = Path(results_dir) / "report_complexity.csv"
    try:
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(output_data)
        logger.success(f"Report generated: {output_file}")
    except IOError as e:
        logger.warning(f"Error writing CSV: {e}")
        return

    # 5. Console summary
    from collections import Counter

    count = Counter(r["Level"] for r in output_data)

    logger.info(f"Distribution ({len(output_data)} units):")
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        n = count.get(level, 0)
        if n:
            logger.info(f"  {level:8}: {n:4}")

    logger.info("Top 10 most complex units:")
    for r in output_data[:10]:
        logger.info(f"  CC={r['CC']:5}  {r['Level']:8}  " f"{r['File']:25} {r['Unit']}")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_complexity(source_dir, results_dir, inputs=inputs)
    write_complexity(results_dir, data)
    return data


if __name__ == "__main__":
    main()
