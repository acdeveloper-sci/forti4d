import os
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
USAGE_OUTPUT = RESULTS_PATH / "common_usage.csv"
COUPLING_OUTPUT = RESULTS_PATH / "common_coupling.csv"

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


def analyze_common():
    print("--- COMMON Block Analysis ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory()
    except Exception as e:
        print(f"ERROR loading inventory: {e}")
        return

    if not inventory_list:
        print("Inventory is empty.")
        return

    # Type conversion and grouping by file
    units_map = defaultdict(list)
    for u in inventory_list:
        file = u.get("File", "").strip()
        if not file:
            continue
        try:
            u["Start_Line"] = int(u["Start_Line"])
            u["End_Line"] = int(u["End_Line"])
        except (ValueError, KeyError):
            u["Start_Line"] = 0
            u["End_Line"] = 0
        units_map[file].append(u)

    # Result structure:
    # usage[(file, drive)] = Counter(block -> n occurrences)
    usage = defaultdict(lambda: defaultdict(int))
    # unit metadata for the report
    meta = {}  # (file, drive) -> dict with Type

    for u in inventory_list:
        k = (u["File"], u["Name"])
        meta[k] = {"Type": u.get("Type", "UNKNOWN")}

    audit_path_ = AUDIT_PATH
    sorted_files = sorted(units_map.keys(), key=str.lower)

    total_common = 0

    for file_name in sorted_files:
        debug_file = audit_path_ / f"{file_name}_DEBUG.csv"
        if not debug_file.exists():
            continue

        units_on_file = sorted(units_map[file_name], key=lambda u: u["Start_Line"])

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
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
        print("No COMMON statements found in the corpus.")
        print("(The code uses F90 modules instead of COMMON blocks)")
        # Generate empty CSVs with headers to maintain pipeline consistency
        _write_empty_csv(USAGE_OUTPUT, ["File", "Unit", "Type", "Block", "Occurrences"])
        _write_empty_csv(COUPLING_OUTPUT, ["Block", "N_Units", "N_Files", "Risk", "Units", "Files"])
        return

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

    # 4. Export
    _write_csv(USAGE_OUTPUT, row_usage, ["File", "Unit", "Type", "Block", "Occurrences"])

    _write_csv(
        COUPLING_OUTPUT,
        docking_rows,
        ["Block", "N_Units", "N_Files", "Risk", "Units", "Files"],
    )

    # 5. Console summary
    n_blocks = len(units_block)
    n_units_affected = len(usage)

    print(f"COMMON statements found       : {total_common}")
    print(f"Unique blocks                 : {n_blocks}")
    print(f"Units with COMMON             : {n_units_affected}")
    print()

    from collections import Counter

    risks = Counter(r["Risk"] for r in docking_rows)
    print("Coupling distribution by block:")
    for level in ("HIGH", "MEDIUM", "LOW"):
        n = risks.get(level, 0)
        if n:
            print(f"  {level:6}: {n} block(s)")

    print()
    print("Most coupled blocks (shared by most units):")
    for r in docking_rows[:10]:
        print(f"  {r['Block']:20}  {r['N_Units']:3} units  " f"[{r['Risk']}]  → {r['Units'][:60]}")

    print(f"\nGenerated: {USAGE_OUTPUT}, {COUPLING_OUTPUT}")


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
    print(f"  {path} generated (empty — no COMMON in corpus)")


if __name__ == "__main__":
    analyze_common()
