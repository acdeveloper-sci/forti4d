import csv
from collections import defaultdict
from pathlib import Path

import forti4d.lib.reader_logical as reader_logical
from forti4d.analyzers.inventory import load_inventory
from forti4d.config import CODE_PATH, RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
CSV_OUTPUT = RESULTS_PATH / "report_sloc.csv"


# =============================================================================
# PHYSICAL LINE CLASSIFICATION
# =============================================================================

# Categories
BLANK = "BLANK"
COMMENT = "COMMENT"
CONTINUATION = "CONTINUATION"
CODE = "CODE"


def classify_physical(sentences: list) -> dict:
    """
    From the list of LogicalLines returned by reader_logical,
    builds a dict  physical_line (int) -> category (str).

    Rules:
      - LogicalLine.is_comment=True           → COMMENT
      - LogicalLine with empty/blank text      → BLANK
      - LogicalLine with code, 1 raw_line      → CODE  (single-line statement)
      - LogicalLine with code, multiple raw_lines:
          · first raw_line                    → CODE
          · the rest                          → CONTINUATION
    """
    result = {}
    for s in sentences:
        if s.is_comment:
            for lineno, _ in s.raw_lines:
                result[lineno] = COMMENT
        elif not s.text.strip():
            for lineno, _ in s.raw_lines:
                result[lineno] = BLANK
        else:
            for i, (lineno, _) in enumerate(s.raw_lines):
                result[lineno] = CODE if i == 0 else CONTINUATION
    return result


# =============================================================================
# MAIN ANALYSIS
# =============================================================================


def analize_sloc():
    print("--- Precise SLOC Counter ---")

    # 1. Load inventory
    try:
        inventory_list = load_inventory()
    except Exception as e:
        print(f"ERROR loading inventory: {e}")
        return

    if not inventory_list:
        print("Inventory is empty.")
        return

    # Convert numeric types and group by file
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

    code_path_ = CODE_PATH
    sorted_files = sorted(units_map.keys(), key=str.lower)
    output_data = []

    for idx, rel_path in enumerate(sorted_files):
        file_name = Path(rel_path).name
        physical_path = code_path_ / rel_path
        print(f"  [{idx+1}/{len(sorted_files)}] {file_name}")

        try:
            sentences = reader_logical.read_logical_lines(physical_path)
        except Exception as e:
            print(f"    -> Error reading: {e}")
            continue

        # Classify physical lines
        classif = classify_physical(sentences)

        if not classif:
            continue

        # Sort units by Start_Line for scope resolution
        units = sorted(units_map[rel_path], key=lambda u: u["Start_Line"])

        # Accumulators per unit: { unit_name -> { cat -> count } }
        counters = defaultdict(lambda: defaultdict(int))

        for lineno, cat in classif.items():
            # Scope: innermost unit containing lineno
            candidates = [u for u in units if u["Start_Line"] <= lineno <= u["End_Line"]]
            if candidates:
                scope = max(candidates, key=lambda u: u["Start_Line"])["Name"]
            else:
                scope = "GLOBAL"
            counters[scope][cat] += 1

        # Build output rows
        for u in units:
            uname = u["Name"]
            c = counters[uname]

            loc = c[BLANK] + c[COMMENT] + c[CODE] + c[CONTINUATION]
            n_blank = c[BLANK]
            n_comment = c[COMMENT]
            n_cont = c[CONTINUATION]
            sloc_physical = loc - n_blank - n_comment  # includes continuations
            sloc_net = sloc_physical - n_cont  # = logical code statements
            pct_comment = round(n_comment / loc * 100, 1) if loc > 0 else 0.0

            output_data.append(
                {
                    "File": file_name,
                    "Unit": uname,
                    "Type": u.get("Type", "UNKNOWN"),
                    "LOC": loc,
                    "N_Blank": n_blank,
                    "N_Comments": n_comment,
                    "N_Continuation": n_cont,
                    "SLOC_physical": sloc_physical,
                    "SLOC_net": sloc_net,
                    "Pct_Comment": pct_comment,
                }
            )

    if not output_data:
        print("No data to export.")
        return

    # Sort by descending SLOC_net
    output_data.sort(key=lambda x: -x["SLOC_net"])

    # Export
    columns = [
        "File",
        "Unit",
        "Type",
        "LOC",
        "N_Blank",
        "N_Comments",
        "N_Continuation",
        "SLOC_physical",
        "SLOC_net",
        "Pct_Comment",
    ]
    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(output_data)

    # Console summary
    total_loc = sum(r["LOC"] for r in output_data)
    total_blank = sum(r["N_Blank"] for r in output_data)
    total_comment = sum(r["N_Comments"] for r in output_data)
    total_cont = sum(r["N_Continuation"] for r in output_data)
    total_sloc_physycal = sum(r["SLOC_physical"] for r in output_data)
    total_sloc_net = sum(r["SLOC_net"] for r in output_data)

    # Totals by file (root units only to avoid double-counting)
    # Note: we sum all because most are non-overlapping (different ranges)
    # For a real per-file total we use the max LOC per file
    files_loc = defaultdict(int)
    for r in output_data:
        # Accumulate root LOC (Parent==GLOBAL) per file
        files_loc[r["File"]] = max(files_loc[r["File"]], r["LOC"])

    print(f"\nGlobal summary:")
    print(f"  Total LOC (physical, corpus) : {sum(files_loc.values()):>8,}")
    print(f"  Blank lines                  : {total_blank:>8,}")
    print(f"  Comment lines                : {total_comment:>8,}")
    print(f"  Continuation lines           : {total_cont:>8,}")
    print(f"  Physical SLOC                : {total_sloc_physycal:>8,}  (code without blanks/comments)")
    print(f"  Net SLOC                     : {total_sloc_net:>8,}  (logical statements)")

    loc_corpus = sum(files_loc.values())
    if loc_corpus > 0:
        print(f"  Comment density (corpus)     : {total_comment/loc_corpus*100:>7.1f}%")

    print(f"\nTop 10 largest units (net SLOC):")
    for r in output_data[:10]:
        pct = f"{r['Pct_Comment']:4.1f}%"
        print(f"  {r['SLOC_net']:5}  sloc  {r['Pct_Comment']:4.1f}% comment  " f"{r['File']:25} {r['Unit']}")

    # Units with no comments at all
    no_comments = [r for r in output_data if r["N_Comments"] == 0 and r["SLOC_net"] > 10]
    if no_comments:
        print(f"\nUnits with >10 statements and 0 comments ({len(no_comments)}):")
        for r in sorted(no_comments, key=lambda x: -x["SLOC_net"])[:15]:
            print(f"  {r['SLOC_net']:5}  sloc  {r['File']:25} {r['Unit']}")

    print(f"\nGenerated: {CSV_OUTPUT}")


if __name__ == "__main__":
    analize_sloc()
