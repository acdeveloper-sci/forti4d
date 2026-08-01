import os
import csv
import re
from collections import defaultdict
from pathlib import Path

from loguru import logger

from forti4d.analyzers.inventory import load_inventory
from forti4d import config

BLANK_NAME = "(BLANK)"  # Label for unnamed COMMON


# =============================================================================
# PARSING OF COMMON STATEMENTS
# =============================================================================


def extract_blocks(content: str) -> list:
    """
    Extracts block names from a COMMON statement.

    Returns a list of unique block names referenced on that line.
    The blank COMMON (unnamed or with //) is represented as NOMBRE_BLANK.

    Ejemplos:
      "COMMON /A/ x, y"          → ["A"]
      "COMMON x, y"              → ["(BLANK)"]
      "COMMON //x"               → ["(BLANK)"]
      "COMMON /A/ x /B/ y"       → ["A", "B"]
      "COMMON x /A/ y"           → ["(BLANK)", "A"]
    """
    # Strip the COMMON keyword from the start
    rest = re.sub(r"^\s*common\s*", "", content.strip(), flags=re.IGNORECASE)

    if not rest:
        return []

    blocks = []

    if rest.lstrip().startswith("/"):
        # Starts with a named block (or // for blank)
        for m in re.finditer(r"/(\w*)/", rest):
            name = m.group(1).strip()
            blocks.append(name if name else BLANK_NAME)
    else:
        # Starts with blank COMMON (variables before any /)
        blocks.append(BLANK_NAME)
        # There may be named blocks after: COMMON x /A/ y
        for m in re.finditer(r"/(\w*)/", rest):
            name = m.group(1).strip()
            blocks.append(name if name else BLANK_NAME)

    # Deduplicate while preserving order (a line should not repeat the same block,
    # but if it does, count it only once per line)
    seen_list = []
    seen = set()
    for b in blocks:
        if b not in seen:
            seen_list.append(b)
            seen.add(b)
    return seen_list


# =============================================================================
# MAIN ANALYSIS
# =============================================================================


def analyze_common(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes."""
    inputs = inputs or {}
    logger.debug("--- COMMON Block Analysis ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory(
            rows=inputs.get("inventory_report"), csv_path=Path(results_dir) / "inventory_report.csv"
        )
    except Exception as e:
        logger.warning(f"ERROR loading inventory: {e}")
        return {"common_usage": None, "common_coupling": None}

    if not inventory_list:
        logger.warning("Inventory is empty.")
        return {"common_usage": None, "common_coupling": None}

    # Type conversion and grouping by file
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

    # Result structure:
    # usage[(file, drive)] = Counter(block -> n occurrences)
    usage = defaultdict(lambda: defaultdict(int))
    # unit metadata for the report
    meta = {}  # (file, drive) -> dict with Type

    for u in inventory_list:
        k = (u["File"], u["Name"])
        meta[k] = {"Type": u.get("Type", "UNKNOWN")}

    audit_data = inputs.get("audit")  # {rel_path: debug_rows}, from profiler.py — avoids re-reading from disk
    audit_path_ = Path(results_dir) / "audit"
    sorted_files = sorted(units_map.keys(), key=str.lower)

    total_common = 0

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
            if row.get("Kind") != "COMMON_STMT":
                continue

            try:
                n_line = int(row["Line"])
            except ValueError:
                continue

            content = row.get("Content", "")
            blocks = extract_blocks(content)

            if not blocks:
                continue

            # Scope resolution
            candidates = [u for u in units_on_file if u["Start_Line"] <= n_line <= u["End_Line"]]
            if not candidates:
                scope = "GLOBAL"
                stype = "FILE_SCOPE"
            else:
                u_scope = max(candidates, key=lambda u: u["Start_Line"])
                scope = u_scope["Name"]
                stype = u_scope.get("Type", "UNKNOWN")
                meta[(file_name, scope)] = {"Type": stype}

            for block in blocks:
                usage[(file_name, scope)][block] += 1
                total_common += 1

    if total_common == 0:
        logger.info("No COMMON statements found in the corpus.")
        logger.info("(The code uses F90 modules instead of COMMON blocks)")
        return {"common_usage": [], "common_coupling": [], "empty": True}

    # 2. Build usage report (one row per (unit, block))
    row_usage = []
    for (file, unit), blocks_cnt in sorted(usage.items()):
        stype = meta.get((file, unit), {}).get("Type", "UNKNOWN")
        for block, occurrences in sorted(blocks_cnt.items()):
            row_usage.append(
                {
                    "File": file,
                    "Unit": unit,
                    "Type": stype,
                    "Block": block,
                    "Occurrences": occurrences,
                }
            )

    # 3. Build coupling report (one row per block)
    # block -> set de (file, unit)
    units_block = defaultdict(set)
    for (file, unit), blocks_cnt in usage.items():
        for block in blocks_cnt:
            units_block[block].add((file, unit))

    docking_rows = []
    for block, pairs in sorted(units_block.items()):
        n_units = len(pairs)
        unique_files = sorted(set(a for a, _ in pairs))
        sorted_units = sorted(u for _, u in pairs)

        if n_units >= 5:
            risk = "HIGH"
        elif n_units >= 2:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        docking_rows.append(
            {
                "Block": block,
                "N_Units": n_units,
                "N_Files": len(unique_files),
                "Risk": risk,
                "Units": "; ".join(sorted_units),
                "Files": "; ".join(unique_files),
            }
        )

    docking_rows.sort(key=lambda x: -x["N_Units"])

    return {"common_usage": row_usage, "common_coupling": docking_rows, "empty": False}


def write_common(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    results_dir = Path(results_dir)
    usage_output = results_dir / "common_usage.csv"
    coupling_output = results_dir / "common_coupling.csv"

    row_usage = data["common_usage"]
    docking_rows = data["common_coupling"]

    if row_usage is None:
        return  # inventory empty / load error — nothing written at all, same as before

    if data.get("empty"):
        # Generate empty CSVs with headers to maintain pipeline consistency
        _write_empty_csv(usage_output, ["File", "Unit", "Type", "Block", "Occurrences"])
        _write_empty_csv(coupling_output, ["Block", "N_Units", "N_Files", "Risk", "Units", "Files"])
        return

    # 4. Export
    _write_csv(usage_output, row_usage, ["File", "Unit", "Type", "Block", "Occurrences"])
    _write_csv(coupling_output, docking_rows, ["Block", "N_Units", "N_Files", "Risk", "Units", "Files"])

    # 5. Console summary
    total_common = sum(r["Occurrences"] for r in row_usage)
    n_blocks = len(docking_rows)
    n_units_affected = len(set((r["File"], r["Unit"]) for r in row_usage))

    logger.info(f"COMMON statements found       : {total_common}")
    logger.info(f"Unique blocks                 : {n_blocks}")
    logger.info(f"Units with COMMON             : {n_units_affected}")

    from collections import Counter

    risks = Counter(r["Risk"] for r in docking_rows)
    logger.info("Coupling distribution by block:")
    for level in ("HIGH", "MEDIUM", "LOW"):
        n = risks.get(level, 0)
        if n:
            logger.info(f"  {level:6}: {n} block(s)")

    logger.info("Most coupled blocks (shared by most units):")
    for r in docking_rows[:10]:
        logger.info(f"  {r['Block']:20}  {r['N_Units']:3} units  " f"[{r['Risk']}]  → {r['Units'][:60]}")

    logger.success(f"Generated: {usage_output}, {coupling_output}")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_common(source_dir, results_dir, inputs=inputs)
    write_common(results_dir, data)
    return data


# =============================================================================
# WRITING HELPERS
# =============================================================================


def _write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_empty_csv(path, columns):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=columns).writeheader()
    logger.success(f"  {path} generated (empty — no COMMON in corpus)")


if __name__ == "__main__":
    main()
