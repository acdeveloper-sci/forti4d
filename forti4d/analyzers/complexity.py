import os
import csv
from collections import defaultdict
from pathlib import Path

from forti4d.analyzers.inventory import load_inventory
from forti4d.config import RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
AUDIT_PATH = RESULTS_PATH / "audit"
CSV_OUTPUT = RESULTS_PATH / "report_complexity.csv"


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


def analyze_complexity():
    print("--- McCabe Cyclomatic Complexity ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory()
    except Exception as e:
        print(f"ERROR loading inventory: {e}")
        return

    if not inventory_list:
        print("Inventory is empty.")
        return

    print(f"Inventory loaded: {len(inventory_list)} units.")

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
    audit_path_ = AUDIT_PATH

    sorted_files = sorted(units_file_map.keys(), key=str.lower)

    for idx, rel_path in enumerate(sorted_files):
        file_name = Path(rel_path).name
        debug_stem = rel_path.replace("/", "__").replace("\\", "__")
        debug_file = audit_path_ / f"{debug_stem}_DEBUG.csv"

        if not debug_file.exists():
            print(f"  [{idx+1}] No DEBUG file: {file_name} — skipped")
            continue

        units_per_file = units_file_map[rel_path]
        units_per_file.sort(key=lambda u: u["Start_Line"])

        # Accumulators: each unit starts with base CC = 1
        score = defaultdict(int)

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
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

    # 4. Export
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
    try:
        with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(output_data)
        print(f"\nReport generated: {CSV_OUTPUT}")
    except IOError as e:
        print(f"Error writing CSV: {e}")
        return

    # 5. Console summary
    from collections import Counter

    count = Counter(r["Level"] for r in output_data)
    cc_vals = [r["CC"] for r in output_data]

    print(f"\nDistribution ({len(output_data)} units):")
    for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        n = count.get(level, 0)
        if n:
            print(f"  {level:8}: {n:4}")

    print(f"\nTop 10 most complex units:")
    for r in output_data[:10]:
        print(f"  CC={r['CC']:5}  {r['Level']:8}  " f"{r['File']:25} {r['Unit']}")


if __name__ == "__main__":
    analyze_complexity()
