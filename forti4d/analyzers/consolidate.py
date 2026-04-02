"""
consolidate.py
Merges all per-unit reports into a single CSV with one row per unit.

Sources (all optional except inventory_report.csv):
  inventory_report.csv      → base + Legacy/IO flags
  report_sloc.csv           → LOC, SLOC, comment density
  report_complexity.csv     → CC, complexity level
  dep_03_impact_matrix.csv  → Fan_In, Fan_Out
  report_density.csv        → statement profiles (% calc/control/IO…)
  report_reachability.csv   → status REACHABLE / UNREACHABLE / ENTRY_POINT
  common_usage.csv          → COMMON blocks used (aggregated per unit)
  symbol_variables.csv      → N_Local_Vars, N_Params
  symbol_signatures.csv     → N_Formal_Args
  symbol_implicit.csv       → Implicit_None
  type_definitions.csv      → N_Derived_Types
  equivalences.csv          → Has_Equiv, N_Equiv_Groups
  audit/*_DEBUG.csv         → N_Data_Stmts, N_Entry_Stmts (scope resolution)

Output: report_consolidated.csv — 34 columns, one row per unit.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path
from forti4d.config import RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
INVENTORY_PATH = RESULTS_PATH / "inventory_report.csv"
SLOC_PATH = RESULTS_PATH / "report_sloc.csv"
COMPLEXITY_PATH = RESULTS_PATH / "report_complexity.csv"
IMPACT_PATH = RESULTS_PATH / "dep_03_impact_matrix.csv"
DENSITY_PATH = RESULTS_PATH / "report_density.csv"
REACH_PATH = RESULTS_PATH / "report_reachability.csv"
COMMONU_PATH = RESULTS_PATH / "common_usage.csv"
SYMVALS_PATH = RESULTS_PATH / "symbol_variables.csv"
SYMSIGN_PATH = RESULTS_PATH / "symbol_signatures.csv"
SYMBIMP_PATH = RESULTS_PATH / "symbol_implicit.csv"
TYPEDEF_PATH = RESULTS_PATH / "type_definitions.csv"
EQUIVAL_PATH = RESULTS_PATH / "equivalences.csv"
AUDIT_PATH = RESULTS_PATH / "audit"

CSV_OUTPUT = RESULTS_PATH / "report_consolidated.csv"


# =============================================================================
# READ HELPERS
# =============================================================================


def read_csv(path: str, key_fn) -> dict:
    """
    Reads a CSV and returns a dict keyed by key_fn(row).
    If the key repeats, the last row wins (merge behavior).
    Returns {} if the file does not exist (optional source).
    """
    p = Path(path)
    if not p.exists():
        return {}
    result = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = key_fn(row)
            if k:
                result[k] = row
    return result


def read_csv_multi(path: str, key_fn) -> dict:
    """
    Like read_csv but accumulates multiple rows per key into a list.
    """
    p = Path(path)
    if not p.exists():
        return {}
    result = defaultdict(list)
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            k = key_fn(row)
            if k:
                result[k].append(row)
    return dict(result)


def key_au(row: dict) -> tuple:
    """Key (File, Unit) — used by most sources."""
    a = row.get("File", "").strip()
    u = row.get("Unit", "").strip()
    return (a, u) if a and u else None


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# =============================================================================
# STATEMENT COUNT FROM AUDIT CSVs
# =============================================================================

_AUDIT_KINDS = {"DATA_STMT", "ENTRY_STMT"}


def count_stmts_audit(inv_raw: dict) -> dict:
    """
    Iterates over audit/*_DEBUG.csv and counts DATA_STMT and ENTRY_STMT per unit.
    Uses scope resolution identical to complexity.py: innermost unit
    whose range [Start_Line, End_Line] contains the line.

    Returns dict (File, Unit) → {"N_Data_Stmts": int, "N_Entry_Stmts": int}.
    Returns {} if the audit/ directory does not exist.
    """
    if not AUDIT_PATH.exists():
        return {}

    # Group units by file with their line ranges
    map_by_file = defaultdict(list)
    for (file, name), row in inv_raw.items():
        try:
            ls = int(row.get("Start_Line", 0))
            le = int(row.get("End_Line", 0))
        except (ValueError, TypeError):
            ls = le = 0
        map_by_file[file].append((ls, le, name))

    counts = {}  # (File, Unit) → {"N_Data_Stmts": n, "N_Entry_Stmts": n}

    for file, units in map_by_file.items():
        debug_file = AUDIT_PATH / f"{file}_DEBUG.csv"
        if not debug_file.exists():
            continue

        with open(debug_file, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                kind = row.get("Kind", "")
                if kind not in _AUDIT_KINDS:
                    continue
                try:
                    n_line = int(row["Line"])
                except (ValueError, KeyError):
                    continue

                # Innermost unit containing n_line
                candidates = [(li, lf, nom) for li, lf, nom in units if li <= n_line <= lf]
                if not candidates:
                    continue
                _, _, name = max(candidates, key=lambda t: t[0])

                k = (file, name)
                if k not in counts:
                    counts[k] = {"N_Data_Stmts": 0, "N_Entry_Stmts": 0}
                if kind == "DATA_STMT":
                    counts[k]["N_Data_Stmts"] += 1
                else:
                    counts[k]["N_Entry_Stmts"] += 1

    return counts


# =============================================================================
# SOURCE LOADING
# =============================================================================


def load_sources():
    print("Loading sources...")

    # Inventory: key = (File, Name)  ← the inventory uses "Name"
    inv_raw = {}
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)

    if not INVENTORY_PATH.exists():
        print(f"ERROR: {INVENTORY_PATH} not found.")
        sys.exit(1)
    with open(INVENTORY_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = row.get("File", "").strip()
            n = row.get("Name", "").strip()
            if a and n:
                inv_raw[(a, n)] = row

    sloc_data = read_csv(SLOC_PATH, key_au)
    cc_data = read_csv(COMPLEXITY_PATH, key_au)
    dens_data = read_csv(DENSITY_PATH, key_au)
    reach_data = read_csv(REACH_PATH, key_au)

    # dep_03: key = (File, Unit) — columns in different order
    imp_data = {}
    if IMPACT_PATH.exists():
        with open(IMPACT_PATH, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                a = row.get("File", "").strip()
                u = row.get("Unit", "").strip()
                if a and u:
                    imp_data[(a, u)] = row

    # common_usage: multiple rows per unit (one per block)
    common_multi = read_csv_multi(COMMONU_PATH, key_au)

    # E4 symbols: multiple rows per unit
    vars_multi = read_csv_multi(SYMVALS_PATH, key_au)
    signat_multi = read_csv_multi(SYMSIGN_PATH, key_au)
    implic_multi = read_csv_multi(SYMBIMP_PATH, key_au)

    # derived types: key = (File, host_unit)
    def key_type(row):
        a = row.get("File", "").strip()
        u = row.get("Unit", "").strip()
        return (a, u) if a and u else None

    type_multi = read_csv_multi(TYPEDEF_PATH, key_type)
    equiv_multi = read_csv_multi(EQUIVAL_PATH, key_au)

    print(f"  inventory    : {len(inv_raw)} units")
    print(f"  sloc         : {len(sloc_data)} entries")
    print(f"  complexity   : {len(cc_data)} entries")
    print(f"  density      : {len(dens_data)} entries")
    print(f"  reachability : {len(reach_data)} entries")
    print(f"  impact       : {len(imp_data)} entries")
    print(f"  common_usage : {len(common_multi)} units with COMMON")
    print(f"  symbol_vars  : {sum(len(v) for v in vars_multi.values())} vars in {len(vars_multi)} units")
    print(f"  symbol_signatures: {sum(len(v) for v in signat_multi.values())} args in {len(signat_multi)} units")
    print(f"  tipos_def    : {sum(len(v) for v in type_multi.values())} types in {len(type_multi)} units")
    print(f"  equivalences : {sum(len(v) for v in equiv_multi.values())} vars in {len(equiv_multi)} units")

    audit_stmts = count_stmts_audit(inv_raw)
    n_data = sum(v["N_Data_Stmts"] for v in audit_stmts.values())
    n_entry = sum(v["N_Entry_Stmts"] for v in audit_stmts.values())
    if audit_stmts:
        print(f"  audit stmts  : {n_data} DATA_STMT, {n_entry} ENTRY_STMT in {len(audit_stmts)} units")

    return (
        inv_raw,
        sloc_data,
        cc_data,
        dens_data,
        reach_data,
        imp_data,
        common_multi,
        vars_multi,
        signat_multi,
        implic_multi,
        type_multi,
        equiv_multi,
        audit_stmts,
    )


# =============================================================================
# CONSOLIDATED REPORT CONSTRUCTION
# =============================================================================


def build_rows(
    inv_raw,
    sloc_data,
    cc_data,
    dens_data,
    reach_data,
    implic_data,
    common_multi,
    vars_multi,
    sygnat_multi,
    impl_multi,
    types_multi,
    equiv_multi,
    audit_stmts,
):
    rows = []

    for (file, name), inv in inv_raw.items():
        k = (file, name)

        # ---- IDENTITY ----
        utype = inv.get("Type", "UNKNOWN")
        parent = inv.get("Parent", "GLOBAL")

        # ---- SLOC (SOURCE LINES OF CODE) ----
        slc = sloc_data.get(k, {})
        loc = safe_int(slc.get("LOC", inv.get("Total_Lines", 0)))
        sloc_physical = safe_int(slc.get("SLOC_physical"))
        sloc_net = safe_int(slc.get("SLOC_net"))
        n_comments = safe_int(slc.get("N_Comments"))
        n_continuation = safe_int(slc.get("N_Continuation"))
        pct_comment = safe_float(slc.get("Pct_Comment"))

        # ---- COMPLEXITY ----
        cc_row = cc_data.get(k, {})
        cc = safe_int(cc_row.get("CC", 1))
        cc_level = cc_row.get("Level", "")
        # CC/SLOC: complexity density per statement
        cc_sloc = round(cc / sloc_net, 3) if sloc_net > 0 else 0.0

        # ---- IMPACT (Fan-In / Fan-Out) ----
        implic = implic_data.get(k, {})
        fan_in = safe_int(implic.get("Fan_In"))
        fan_out = safe_int(implic.get("Fan_Out"))

        # ---- DENSITY ----
        dn = dens_data.get(k, {})
        pct_calculat = safe_float(dn.get("Pct_Calc"))
        pct_control = safe_float(dn.get("Pct_Control"))
        pct_io = safe_float(dn.get("Pct_IO"))
        pct_legacy = safe_float(dn.get("Pct_Legacy"))

        # ---- REACHABILITY ----
        reach = reach_data.get(k, {})
        status = reach.get("Status", "")
        via_entries = reach.get("Via_Entry_Points", "")

        # ---- COMMON BLOCKS ----
        common_rows = common_multi.get(k, [])
        n_common_block = len(common_rows)
        common_block = "; ".join(sorted(r.get("Block", "") for r in common_rows))

        # ---- E4 SYMBOLS ----
        var_rows = vars_multi.get(k, [])
        n_vars_loc = sum(1 for r in var_rows if r.get("Is_Parameter") == "NO")
        n_params = sum(1 for r in var_rows if r.get("Is_Parameter") == "YES")
        n_args = len(sygnat_multi.get(k, []))
        impl_rows = impl_multi.get(k, [])
        impl_none = "YES" if any(r.get("Is_None") == "YES" for r in impl_rows) else ("NO" if impl_rows else "")
        n_types = len(types_multi.get(k, []))
        equiv_rows = equiv_multi.get(k, [])
        has_equiv = "YES" if equiv_rows else "NO"
        n_groups_equiv = len({r.get("Group_ID", "") for r in equiv_rows} - {""}) if equiv_rows else 0

        # ---- AUDIT STATEMENT COUNTS ----
        ast = audit_stmts.get(k, {})
        n_data_stmts = ast.get("N_Data_Stmts", 0)
        n_entry_stmts = ast.get("N_Entry_Stmts", 0)

        # ---- FLAGS from inventory ----
        legacy_flags = inv.get("Legacy", "").strip()
        io_flags = inv.get("IO", "").strip()

        rows.append(
            {
                # Identity
                "File": file,
                "Unit": name,
                "Type": utype,
                "Parent": parent,
                # Size
                "LOC": loc,
                "SLOC_physical": sloc_physical,
                "SLOC_net": sloc_net,
                "N_Comments": n_comments,
                "N_Continuation": n_continuation,
                "Pct_Comment": pct_comment,
                # Complexity
                "CC": cc,
                "CC_Level": cc_level,
                "CC_SLOC": cc_sloc,
                # Structural coupling
                "Fan_In": fan_in,
                "Fan_Out": fan_out,
                # Statement profile
                "Pct_Calc": pct_calculat,
                "Pct_Control": pct_control,
                "Pct_IO": pct_io,
                "Pct_Legacy": pct_legacy,
                # COMMON blocks
                "N_Common_Blocks": n_common_block,
                "Common_Blocks": common_block,
                # Reachability
                "Status": status,
                "Via_Entry_Points": via_entries,
                # E4 Symbols
                "N_Local_Vars": n_vars_loc,
                "N_Params": n_params,
                "N_Formal_Args": n_args,
                "Implicit_None": impl_none,
                "N_Derived_Types": n_types,
                "Has_Equiv": has_equiv,
                "N_Equiv_Groups": n_groups_equiv,
                "N_Data_Stmts": n_data_stmts,
                "N_Entry_Stmts": n_entry_stmts,
                # Audit flags
                "Legacy_Flags": legacy_flags,
                "IO_Flags": io_flags,
            }
        )

    return rows


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

COLUMNS = [
    "File",
    "Unit",
    "Type",
    "Parent",
    "LOC",
    "SLOC_physical",
    "SLOC_net",
    "N_Comments",
    "N_Continuation",
    "Pct_Comment",
    "CC",
    "CC_Level",
    "CC_SLOC",
    "Fan_In",
    "Fan_Out",
    "Pct_Calc",
    "Pct_Control",
    "Pct_IO",
    "Pct_Legacy",
    "N_Common_Blocks",
    "Common_Blocks",
    "Status",
    "Via_Entry_Points",
    "N_Local_Vars",
    "N_Params",
    "N_Formal_Args",
    "Implicit_None",
    "N_Derived_Types",
    "Has_Equiv",
    "N_Equiv_Groups",
    "N_Data_Stmts",
    "N_Entry_Stmts",
    "Legacy_Flags",
    "IO_Flags",
]


def main():
    print("=== Report Consolidation ===\n")

    sources = load_sources()
    rows = build_rows(*sources)

    if not rows:
        print("No rows to export.")
        return

    # Sort: first by file, then by implicit Start_Line order from
    # the inventory (preserved as a dict in Python 3.7+)
    # For the final CSV: alphabetical order by file + unit
    rows.sort(key=lambda r: (r["File"].lower(), r["Unit"].lower()))

    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Summary
    total = len(rows)
    con_cc = sum(1 for r in rows if r["CC_Level"])
    no_sloc = sum(1 for r in rows if r["SLOC_net"] == 0)
    deads = sum(1 for r in rows if r["Status"] == "UNREACHABLE")
    criticals = sum(1 for r in rows if r["CC_Level"] == "CRITICAL")
    no_coment = sum(1 for r in rows if r["Pct_Comment"] == 0 and r["SLOC_net"] > 10)

    print(f"\nConsolidated report generated: {CSV_OUTPUT}")
    print(f"  Total rows              : {total}")
    print(f"  With CC metrics         : {con_cc}")
    print(f"  UNREACHABLE units       : {deads}")
    print(f"  CRITICAL CC level       : {criticals}")
    print(f"  Without comments (>10 sl): {no_coment}")
    print(f"  Without SLOC (empty/err): {no_sloc}")

    # Top risk: high CC + high Fan_In + few comments
    print("\nTop 10 refactoring candidates (CC × Fan_In):")
    top = sorted(rows, key=lambda r: -(r["CC"] * max(r["Fan_In"], 1)))
    for r in top[:10]:
        print(
            f"  CC={r['CC']:5}  Fan_In={r['Fan_In']:3}  {r['Pct_Comment']:4.1f}%comment  " f"{r['File']:25} {r['Unit']}"
        )


if __name__ == "__main__":
    main()
