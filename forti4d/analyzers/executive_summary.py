import sys
import os
import io
import csv
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean, median
from loguru import logger
from forti4d import config


def load_data(rows=None, dep_rows=None, results_dir=None):
    """Uses in-memory `rows`/`dep_rows` if given, otherwise reads
    inventory_report.csv / dep_03_impact_matrix.csv from results_dir."""
    if rows is None:
        inventory_file = Path(results_dir) / "inventory_report.csv"
        if not inventory_file.exists():
            logger.error(f"ERROR: {inventory_file} not found")
            sys.exit(1)
        # utf-8-sig to correctly read accented characters if coming from Excel
        with open(inventory_file, "r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

    inv_rows = []
    for row in rows:
        # Safely convert numbers (Total_Lines may already be int if `rows`
        # came in-memory from inventory.py, or str if read from CSV)
        try:
            val = str(row.get("Total_Lines", "0")).strip()
            if not val.isdigit():
                val = "0"
            row["Total_Lines"] = int(val)
        except ValueError:
            row["Total_Lines"] = 0
        inv_rows.append(row)

    if dep_rows is None:
        dependencies_file = Path(results_dir) / "dep_03_impact_matrix.csv"
        dep_rows = []
        if dependencies_file.exists():
            # utf-8-sig to read dependencies
            with open(dependencies_file, "r", encoding="utf-8-sig") as f:
                dep_rows = list(csv.DictReader(f))

    out_dep_rows = []
    for row in dep_rows:
        try:
            row["Fan_In"] = int(row["Fan_In"])
        except (ValueError, KeyError):
            row["Fan_In"] = 0
        try:
            row["Fan_Out"] = int(row["Fan_Out"])
        except (ValueError, KeyError):
            row["Fan_Out"] = 0
        out_dep_rows.append(row)

    return inv_rows, out_dep_rows


def load_scope_health(impl_rows=None, equiv_rows=None, common_rows=None, vars_rows=None, results_dir=None):
    """
    Loads the optional E4 sources and returns four structures:
      impl_none_set  — set (File, Unit) with IMPLICIT NONE
      equiv_set      — set (File, Unit) with at least one EQUIVALENCE group
      common_set     — set (File, Unit) with at least one COMMON block
      vars_count     — Counter (File, Unit) -> number of local variables (excl. PARAMETERs)
    Uses in-memory rows if given; any of these can be empty if the
    corresponding CSV doesn't exist (optional sources).
    """
    if impl_rows is None:
        symbols_impl_csv = Path(results_dir) / "symbol_implicit.csv"
        impl_rows = []
        if symbols_impl_csv.exists():
            with open(symbols_impl_csv, encoding="utf-8-sig") as f:
                impl_rows = list(csv.DictReader(f))
    impl_none_set = set()
    for row in impl_rows:
        if row.get("Is_None", "").strip() == "YES":
            impl_none_set.add((row.get("File", "").strip(), row.get("Unit", "").strip()))

    if equiv_rows is None:
        equivalences_csv = Path(results_dir) / "equivalences.csv"
        equiv_rows = []
        if equivalences_csv.exists():
            with open(equivalences_csv, encoding="utf-8-sig") as f:
                equiv_rows = list(csv.DictReader(f))
    equiv_set = set()
    for row in equiv_rows:
        equiv_set.add((row.get("File", "").strip(), row.get("Unit", "").strip()))

    if common_rows is None:
        common_usage_csv = Path(results_dir) / "common_usage.csv"
        common_rows = []
        if common_usage_csv.exists():
            with open(common_usage_csv, encoding="utf-8-sig") as f:
                common_rows = list(csv.DictReader(f))
    common_set = set()
    for row in common_rows:
        common_set.add((row.get("File", "").strip(), row.get("Unit", "").strip()))

    if vars_rows is None:
        symbols_vars_csv = Path(results_dir) / "symbol_variables.csv"
        vars_rows = []
        if symbols_vars_csv.exists():
            with open(symbols_vars_csv, encoding="utf-8-sig") as f:
                vars_rows = list(csv.DictReader(f))
    vars_count = Counter()
    for row in vars_rows:
        if row.get("Is_Parameter", "").strip() != "YES":
            key = (row.get("File", "").strip(), row.get("Unit", "").strip())
            vars_count[key] += 1

    return impl_none_set, equiv_set, common_set, vars_count


def calculate_scope_stats(inv_rows, impl_none_set, equiv_set, common_set, vars_count):
    """
    Calculates scope health metrics from E4 data.
    Returns None if no E4 data is available.
    """
    if not (impl_none_set or equiv_set or common_set or vars_count):
        return None

    total = len(inv_rows)
    units = [(r["File"], r["Name"] if "Name" in r else r.get("Unit", "")) for r in inv_rows]

    n_impl_none = sum(1 for u in units if u in impl_none_set)
    n_equiv = sum(1 for u in units if u in equiv_set)
    n_common = sum(1 for u in units if u in common_set)
    n_clean = sum(1 for u in units if u in impl_none_set and u not in equiv_set and u not in common_set)

    top5_vars = vars_count.most_common(5)

    return {
        "total": total,
        "n_impl_none": n_impl_none,
        "n_equiv": n_equiv,
        "n_common": n_common,
        "n_clean": n_clean,
        "top5_vars": top5_vars,
        "has_data": True,
    }


def calculate_summary(inv_rows, dep_rows):
    stats = {
        "total_files": 0,
        "total_lines": sum(r["Total_Lines"] for r in inv_rows if r.get("Parent", "GLOBAL") == "GLOBAL"),
        "total_units": len(inv_rows),
        "units_per_type": Counter(),
        "files_map": defaultdict(lambda: {"lines": 0, "units": 0, "types": set(), "legacy_flags": 0, "io_flags": 0}),
        "top_usage": [],
        "legacy_count": 0,
        "units_with_legacy": 0,
        "top_legacy": Counter(),
        "io_count": 0,
        "units_with_io": 0,
        "top_io": Counter(),
        "implicit_main_count": 0,
    }

    unique_files = set()

    for r in inv_rows:
        file = r.get("Relative_Path") or r["File"]
        utype = r["Type"]
        lines = r["Total_Lines"]

        unique_files.add(file)
        stats["units_per_type"][r["Type"]] += 1

        # Stats per file - LOC only in root units to avoid double counting
        # (nested units share the line range of their parent)
        stats["files_map"][file]["lines_p"] = lines
        if r.get("Parent", "GLOBAL") == "GLOBAL":
            stats["files_map"][file]["lines"] += lines
        stats["files_map"][file]["units"] += 1
        stats["files_map"][file]["types"].add(utype)

        # Audit Flags
        has_legacy = bool(r.get("Legacy") and r["Legacy"].strip())
        has_io = bool(r.get("IO") and r["IO"].strip())

        # Legacy
        if has_legacy:
            stats["units_with_legacy"] += 1
            items = [x.strip() for x in r["Legacy"].split(",")]
            for it in items:
                if it:
                    stats["legacy_count"] += 1
                    stats["top_legacy"][it] += 1
                    stats["files_map"][file]["legacy_flags"] += 1

        # IO
        if has_io:
            stats["units_with_io"] += 1
            items = [x.strip() for x in r["IO"].split(",")]
            for it in items:
                if it:
                    stats["io_count"] += 1
                    stats["top_io"][it] += 1
                    stats["files_map"][file]["io_flags"] += 1

        if utype == "IMPLICIT-MAIN":
            stats["implicit_main_count"] += 1

    stats["total_files"] = len(unique_files)
    # stats["total_lines"] = sum(d["lines"] for d in stats["files_map"].values())

    # Top Dependencies - utilization (high Fan-In)
    # Sort by Fan-In descending
    dep_rows_sorted = sorted(dep_rows, key=lambda x: x["Fan_In"], reverse=True)
    stats["top_usage"] = dep_rows_sorted[:15]  # Top 15

    # Top Dependencies - complexity (high Fan-Out)
    # Sort by Fan-Out descending
    dep_rows_sorted = sorted(dep_rows, key=lambda x: x["Fan_Out"], reverse=True)
    stats["top_complexity"] = dep_rows_sorted[:15]  # Top 15

    return stats


def generate_markdown_report(stats, scope_stats=None) -> str:
    """Pure: builds and returns the markdown report text. No disk writes."""
    f = io.StringIO()
    f.write("# EXECUTIVE SUMMARY OF FORTRAN PROJECT SOURCE CODE\n\n")

    # 1. GLOBAL OVERVIEW
    f.write("## 1. Global Metrics\n")
    f.write(f"- **Total Files**: {stats['total_files']}\n")
    f.write(f"- **Total Lines of Code (LOC)**: {stats['total_lines']:,}\n")
    f.write(f"- **Total Program Units**: {stats['total_units']}\n")
    if stats["total_files"] > 0:
        avg_loc = stats["total_lines"] / stats["total_files"]
        f.write(f"- **Average LOC per file**: {avg_loc:.1f}\n\n")

    # 2. DISTRIBUTION BY TYPE
    f.write("## 2. Distribution by Unit Type\n")
    f.write("| Type | Count | % of Total |\n")
    f.write("| :--- | :---: | :---: |\n")
    for tipo, count in stats["units_per_type"].most_common():
        pct = (count / stats["total_units"]) * 100
        f.write(f"| {tipo} | {count} | {pct:.1f}% |\n")
    f.write("\n")

    # 3. TOP MONOLITHS
    f.write("## 3. Top 10 Largest Files (Monoliths)\n")
    # Sort files by lines
    top_files = sorted(stats["files_map"].items(), key=lambda x: x[1]["lines"], reverse=True)[:10]
    f.write("| File | Lines | Units | Contained Types |\n")
    f.write("| :--- | :---: | :---: | :--- |\n")
    for name, data in top_files:
        tipos_str = ", ".join(sorted(data["types"]))
        f.write(f"| {name} | {data['lines']} | {data['units']} | {tipos_str} |\n")
    f.write("\n")

    # 4. CODE HEALTH
    f.write("## 4. Health Indicators (Legacy)\n")
    pct_legacy = (stats["units_with_legacy"] / stats["total_units"]) * 100 if stats["total_units"] else 0
    f.write(f"- **Units with Legacy code (COMMON/GOTO/etc.):** {stats['units_with_legacy']} ({pct_legacy:.1f}%)\n")
    if not stats["top_legacy"]:
        f.write("_No configured Legacy statements detected (COMMON, GOTO, etc)._\n\n")
    else:
        f.write("The following legacy constructs were detected:\n\n")
        f.write("  | Statement | Occurrences |\n")
        f.write("  | :--- | :---: |\n")
        for item, count in stats["top_legacy"].most_common():
            f.write(f"  | {item} | {count} |\n")

    pct_io = (stats["units_with_io"] / stats["total_units"]) * 100 if stats["total_units"] else 0
    f.write(f"- **Units with Intensive I/O (OPEN/READ/CLOSE/etc.):** {stats['units_with_io']} ({pct_io:.1f}%)\n")
    if not stats["top_io"]:
        f.write("_No configured I/O statements detected (OPEN, READ, CLOSE, etc)._\n\n")
    else:
        f.write("The following I/O constructs were detected:\n\n")
        f.write("  | Statement | Occurrences |\n")
        f.write("  | :--- | :---: |\n")
        for item, count in stats["top_io"].most_common():
            f.write(f"  | {item} | {count} |\n")
    f.write(f"- **Implicit Main Programs:** {stats['implicit_main_count']} (Candidates for refactoring)\n")
    f.write("\n")

    # 5. SCOPE HEALTH (E4)
    if scope_stats and scope_stats.get("has_data"):
        ss = scope_stats
        total = ss["total"]
        pct = lambda n: f"{(n/total*100):.1f}%" if total else "—"
        f.write("## 5. Scope Health (E4)\n\n")
        f.write("| Indicator | Units | % of total |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| With IMPLICIT NONE | {ss['n_impl_none']} | {pct(ss['n_impl_none'])} |\n")
        f.write(
            f"| Without IMPLICIT NONE (type risk) | {total - ss['n_impl_none']} | {pct(total - ss['n_impl_none'])} |\n"
        )
        f.write(f"| With EQUIVALENCE (aliasing) | {ss['n_equiv']} | {pct(ss['n_equiv'])} |\n")
        f.write(f"| With COMMON blocks | {ss['n_common']} | {pct(ss['n_common'])} |\n")
        f.write(f"| Clean scope (IMPLICIT NONE, no EQUIV, no COMMON) | {ss['n_clean']} | {pct(ss['n_clean'])} |\n")
        f.write("\n")
        if ss["top5_vars"]:
            f.write("### Top 5 units by local variable density\n\n")
            f.write("| Unit | File | Local Vars |\n")
            f.write("| :--- | :--- | :---: |\n")
            for (file, unit), n in ss["top5_vars"]:
                f.write(f"| {unit} | {file} | {n} |\n")
            f.write("\n")

    # 6. STRUCTURE (Dependencies)
    top_usage = stats["top_usage"]
    # Filter UNKNOWN for the executive report if desired,
    # but sometimes it is useful to see which unknown is heavily used.

    if top_usage:
        f.write("## 6. Critical Units (most reused, highest Fan-In)\n")
        f.write("Units that are the 'heart' of the system.\n\n")
        f.write("| Unit | Type | File | Called by (times) |\n")
        f.write("| :--- | :--- | :--- | :---: |\n")
        for d in top_usage:
            f.write(f"| {d['Unit']} | {d.get('Type','?')} | {d.get('File','?')} | {d.get('Fan_In',0)} |\n")
        f.write("\n")

    top_complejos = stats["top_complexity"]
    # Filter UNKNOWN for the executive report if desired,
    # but sometimes it is useful to see which unknown is heavily used.

    if top_complejos:
        f.write("## 7. Orchestrator Units (highest complexity, highest Fan-Out)\n")
        f.write("Units that coordinate flow and depend on many parts of the system.\n\n")
        f.write("| Unit | Type | File | Calls (no. dependencies) |\n")
        f.write("| :--- | :--- | :--- | :---: |\n")
        for d in top_complejos:
            f.write(f"| {d['Unit']} | {d.get('Type','?')} | {d.get('File','?')} | {d.get('Fan_Out',0)} |\n")
        f.write("\n")

    return f.getvalue()


def generate_csv_rows(stats) -> list:
    """Pure: returns the data rows for file_statistics.csv (header excluded)."""
    rows = []
    for fname, data in sorted(stats["files_map"].items()):
        rows.append(
            [
                fname,
                data["lines"],
                data["units"],
                "YES" if data["legacy_flags"] > 0 else "NO",
                "YES" if data["io_flags"] > 0 else "NO",
                ";".join(sorted(data["types"])),
            ]
        )
    return rows


def analyze_executive_summary(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes."""
    inputs = inputs or {}
    logger.info("Generating Executive Summary...")
    inv, dep = load_data(
        rows=inputs.get("inventory_report"), dep_rows=inputs.get("dep_03_impact_matrix"), results_dir=results_dir
    )
    stats = calculate_summary(inv, dep)

    # Optional E4 sources — in current pipeline order these steps haven't
    # run yet, so `inputs` won't have them; falls back to disk, same as before.
    impl_none_set, equiv_set, common_set, vars_count = load_scope_health(
        impl_rows=inputs.get("symbol_implicit"),
        equiv_rows=inputs.get("equivalences"),
        common_rows=inputs.get("common_usage"),
        vars_rows=inputs.get("symbol_variables"),
        results_dir=results_dir,
    )
    scope_stats = calculate_scope_stats(inv, impl_none_set, equiv_set, common_set, vars_count)
    if scope_stats:
        logger.info(
            f"  E4: {scope_stats['n_impl_none']}/{scope_stats['total']} IMPLICIT NONE, "
            f"{scope_stats['n_equiv']} EQUIV, {scope_stats['n_common']} COMMON, "
            f"{scope_stats['n_clean']} clean-scope"
        )

    md_text = generate_markdown_report(stats, scope_stats)
    csv_rows = generate_csv_rows(stats)

    return {"project_summary_md": md_text, "file_statistics": csv_rows}


def write_executive_summary(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    out_md = Path(results_dir) / "PROJECT_SUMMARY.md"
    # utf-8-sig to generate MD report compatible with Windows
    with open(out_md, "w", encoding="utf-8-sig") as f:
        f.write(data["project_summary_md"])
    logger.success(f"Executive report generated: {out_md}")

    out_csv = Path(results_dir) / "file_statistics.csv"
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Total_Lines", "Total_Units", "Has_Legacy", "Has_IO", "Types_Present"])
        writer.writerows(data["file_statistics"])
    logger.success(f"Detailed CSV generated: {out_csv}")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_executive_summary(source_dir, results_dir, inputs=inputs)
    write_executive_summary(results_dir, data)
    return data


if __name__ == "__main__":
    main()
