import csv
import sys
import os
from pathlib import Path
from loguru import logger
from forti4d import config

# E4 penalty on ICM (additive points, scale 0-100)
E4_PENALTY_MAX = 7.0  # maximum added to ICM for E4 risk
W_E4_IMPL = 0.70  # without IMPLICIT NONE
W_E4_EQUIV = 0.30  # has EQUIVALENCE

# Priority Map (Lower number = Higher urgency)
PRIORITY_MAP = {
    "DIRECT_MIGRATION": 1,
    "STANDARD_MIGRATION": 2,
    "REPLACE_LIB": 3,
    "REFACTOR_CORE": 4,
    "REWRITE_ISOLATED": 5,
    "ANALYZE_UTILITY": 6,
    "ELIMINATE": 7,
}


# HELPERS
def to_float(val, default=0.0):
    """Safely converts a value (string, from CSV, or already-numeric, from
    an in-memory upstream step) to float."""
    if not val or (isinstance(val, str) and val.strip() == ""):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def clip(val, max_val):
    """Simulates numpy/pandas .clip()."""
    return min(val, max_val)


def load_reachability(rows=None, results_dir=None):
    """Returns dict (File, Unit) → Status. Empty if no data is available.
    Uses in-memory `rows` if given, otherwise reads report_reachability.csv
    from results_dir (optional source — empty if it doesn't exist)."""
    result = {}
    if rows is None:
        reachability_csv = Path(results_dir) / "report_reachability.csv"
        if not reachability_csv.exists():
            return result
        with open(reachability_csv, encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))
    for row in rows:
        key = (row.get("File", "").strip(), row.get("Unit", "").strip())
        result[key] = row.get("Status", "").strip()
    return result


def load_e4(impl_rows=None, equiv_rows=None, results_dir=None):
    """
    Returns (impl_none_set, equiv_set):
      impl_none_set — (File, Unit) that have IMPLICIT NONE (Is_None == YES)
      equiv_set     — (File, Unit) that have at least one EQUIVALENCE group
    Uses in-memory rows if given; otherwise reads the optional CSVs from
    results_dir (both empty if they don't exist).
    """
    impl_none_set = set()
    if impl_rows is None:
        symbols_impl_csv = Path(results_dir) / "symbol_implicit.csv"
        impl_rows = []
        if symbols_impl_csv.exists():
            with open(symbols_impl_csv, encoding="utf-8-sig", errors="replace") as f:
                impl_rows = list(csv.DictReader(f))
    for row in impl_rows:
        if row.get("Is_None", "").strip() == "YES":
            key = (row.get("File", "").strip(), row.get("Unit", "").strip())
            impl_none_set.add(key)

    equiv_set = set()
    if equiv_rows is None:
        equivalences_csv = Path(results_dir) / "equivalences.csv"
        equiv_rows = []
        if equivalences_csv.exists():
            with open(equivalences_csv, encoding="utf-8-sig", errors="replace") as f:
                equiv_rows = list(csv.DictReader(f))
    for row in equiv_rows:
        key = (row.get("File", "").strip(), row.get("Unit", "").strip())
        equiv_set.add(key)

    return impl_none_set, equiv_set


def load_impact(rows=None, results_dir=None):
    """Loads the impact matrix into a dictionary for fast lookup. Uses
    in-memory rows if given, otherwise reads dep_03_impact_matrix.csv."""
    impact_map = {}

    if rows is None:
        impact_file = Path(results_dir) / "dep_03_impact_matrix.csv"
        if not impact_file.exists():
            logger.error(f"ERROR: {impact_file} not found")
            sys.exit(1)
        with open(impact_file, "r", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))

    for row in rows:
        # Use a tuple (File, Unit) as a unique key (Composite Key)
        key = (row["File"], row["Unit"])
        impact_map[key] = {"Fan_In": to_float(row.get("Fan_In", 0)), "Fan_Out": to_float(row.get("Fan_Out", 0))}
    return impact_map


def define_strategy(row, ivc, icm, state_reached=""):
    """Rules Engine."""
    fan_in = row["Fan_In"]
    tipo = row["Type"]
    pct_io = row["Pct_IO"]
    pct_declar = row["Pct_Decl"]

    # Rule -1: Dead code confirmed by reachability analysis
    if state_reached == "UNREACHABLE":
        return "ELIMINATE", "Dead code confirmed by reachability analysis"

    # Rule 0: Dead Code / Undetected Entry Point
    # MODULE and BLOCK DATA are excluded: they are USEd, not CALLed → Fan_In always 0 in call analysis
    if fan_in == 0 and tipo not in ["PROGRAM", "IMPLICIT-MAIN", "MODULE", "BLOCK DATA"]:
        fan_out = row["Fan_Out"]
        if fan_out > 0:
            # Calls other units but nobody calls it internally → possible external entry point
            return "ANALYZE_UTILITY", "No internal callers but active (possible entry point)"
        # fan_out == 0: complete island with no internal connections
        if ivc > 25:
            return "ANALYZE_UTILITY", "No internal connections but with substantial computation"
        return "ELIMINATE", "Isolated with trivial logic (possible dead code)"

    # Rule 1: Calculation Gems
    if ivc > 50 and icm < 30:
        return "DIRECT_MIGRATION", "Gem: Pure and isolated algorithm"

    # Rule 2: Infrastructure
    if (pct_io > 30 or pct_declar > 40) and ivc < 20:
        return "REPLACE_LIB", "Boilerplate: Replace with Modern Libraries"

    # Rule 3: Critical Knots
    if icm > 25 and fan_in > 5:
        return "REFACTOR_CORE", "Gordian Knot: High risk and high dependency"

    # Rule 4: Isolated Knots
    if icm > 20:
        return "REWRITE_ISOLATED", "Complex but low systemic impact"

    return "STANDARD_MIGRATION", "Regular business logic"


def analyze_cross(source_dir, results_dir, *, inputs=None) -> dict:
    """Pure computation. No disk writes."""
    inputs = inputs or {}
    logger.debug("--- Cross Migration Analysis (Standard Lib) ---")

    # 1. Load Dependency data into memory (Hash Map)
    logger.info("Loading impact matrix...")
    impact_map = load_impact(rows=inputs.get("dep_03_impact_matrix"), results_dir=results_dir)

    # 1b. Optional sources — in current pipeline order these steps haven't
    # run yet, so `inputs` won't have them; falls back to whatever is on
    # disk from a prior run, same as before.
    reach_map = load_reachability(rows=inputs.get("report_reachability"), results_dir=results_dir)
    impl_none_set, equiv_set = load_e4(
        impl_rows=inputs.get("symbol_implicit"), equiv_rows=inputs.get("equivalences"), results_dir=results_dir
    )
    if reach_map:
        logger.info(f"  Reachability loaded: {len(reach_map)} units")
    if impl_none_set or equiv_set:
        logger.info(f"  E4: {len(impl_none_set)} with IMPLICIT NONE, {len(equiv_set)} with EQUIVALENCE")

    # 2. Process Density and Cross-reference
    density_rows = inputs.get("report_density")
    if density_rows is None:
        density_file = Path(results_dir) / "report_density.csv"
        if not density_file.exists():
            logger.error(f"ERROR: {density_file} not found")
            sys.exit(1)
        with open(density_file, "r", encoding="utf-8-sig", errors="replace") as f:
            density_rows = list(csv.DictReader(f))

    results = []

    logger.info("Processing and classifying units...")
    for row in density_rows:
        # Retrieve data from the density CSV and convert types
        file = row["File"]
        unit_name = row["Unit"]
        pct_control = to_float(row.get("Pct_Control", 0))
        pct_legacy = to_float(row.get("Pct_Legacy", 0))
        pct_calculo = to_float(row.get("Pct_Calc", 0))
        pct_io = to_float(row.get("Pct_IO", 0))
        pct_declar = to_float(row.get("Pct_Decl", 0))

        # Look up impact data (manual JOIN)
        key = (file, unit_name)
        impact_data = impact_map.get(key, {"Fan_In": 0.0, "Fan_Out": 0.0})

        fan_in = impact_data["Fan_In"]
        fan_out = impact_data["Fan_Out"]

        # Calculate Indices
        # A. Outgoing Coupling Score (Cap at 20 deps -> 100 pts)
        score_fanout = clip(fan_out * 5, 100.0)

        # B. Incoming Coupling Score (Cap at 20 callers -> 100 pts)
        score_fanin = clip(fan_in * 5, 100.0)

        # C. Legacy Score (Cap at 25% lines -> 100 pts)
        score_legacy = clip(pct_legacy * 4, 100.0)

        # D. ICM base (15% Control + 45% Legacy + 20% Fan-Out + 20% Fan-In)
        icm = (0.15 * pct_control) + (0.45 * score_legacy) + (0.20 * score_fanout) + (0.20 * score_fanin)

        # D2. E4 Penalty (additive, max E4_PENALTY_MAX points)
        key = (file, unit_name)
        no_impl_none = key not in impl_none_set
        has_equiv = key in equiv_set
        e4_penalty = E4_PENALTY_MAX * (
            W_E4_IMPL * (1.0 if no_impl_none else 0.0) + W_E4_EQUIV * (1.0 if has_equiv else 0.0)
        )
        icm = round(icm + e4_penalty, 1)

        # E. IVC
        ivc = pct_calculo

        # Reachability status (empty if CSV not available)
        state_reached = reach_map.get(key, "")

        # Create enriched row object
        processed_row = {
            "File": file,
            "Unit": unit_name,
            "Type": row["Type"],
            "ICM": icm,
            "IVC": ivc,
            "Pct_Calc": pct_calculo,
            "Pct_Control": pct_control,
            "Pct_Legacy": pct_legacy,
            "Pct_IO": pct_io,
            "Pct_Decl": pct_declar,
            "Fan_In": fan_in,
            "Fan_Out": fan_out,
            "Reachability_Status": state_reached,
        }

        # Apply Rules
        strategy, explanation = define_strategy(processed_row, ivc, icm, state_reached)

        processed_row["Strategy"] = strategy
        processed_row["Explanation"] = explanation
        processed_row["Priority_Num"] = PRIORITY_MAP.get(strategy, 99)

        results.append(processed_row)

    # 3. Sorting
    # Equivalent to df.sort_values(['Priority_Num', 'IVC'], ascending=[True, False])
    # Python sort is stable; we sort by secondary criterion first, then primary (or use tuple with negation)
    logger.info("Sorting results by priority...")
    results.sort(key=lambda x: (x["Priority_Num"], -x["IVC"]))

    return {"report_migration_strategy": results}


def write_cross(results_dir, data: dict) -> None:
    """Only place that touches disk for this step."""
    results = data["report_migration_strategy"]
    output_columns = [
        "Priority_Num",
        "Strategy",
        "File",
        "Unit",
        "Type",
        "ICM",
        "IVC",
        "Pct_Calc",
        "Pct_Control",
        "Pct_Legacy",
        "Fan_In",
        "Fan_Out",
        "Reachability_Status",
        "Explanation",
    ]
    output_file = Path(results_dir) / "report_migration_strategy.csv"

    try:
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

        logger.success(f"SUCCESS: Report generated at '{output_file}'")

        # Generate brief summary to console
        count = {}
        for r in results:
            est = r["Strategy"]
            count[est] = count.get(est, 0) + 1

        logger.info("--- STRATEGY SUMMARY ---")
        for k, v in sorted(count.items()):
            logger.info(f"{k}: {v}")

    except Exception as e:
        logger.warning(f"Error writing file: {e}")


def main(source_dir=None, results_dir=None, *, inputs=None):
    """Entry point for both CLI standalone use and the in-process orchestrator."""
    source_dir, results_dir = config.resolve_paths(source_dir, results_dir)
    data = analyze_cross(source_dir, results_dir, inputs=inputs)
    write_cross(results_dir, data)
    return data


if __name__ == "__main__":
    main()
