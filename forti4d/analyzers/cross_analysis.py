import csv
import sys
import os
from forti4d.config import RESULTS_PATH

# CONFIGURATION
DENSITY_FILE = RESULTS_PATH / "report_density.csv"
IMPACT_FILE = RESULTS_PATH / "dep_03_impact_matrix.csv"
STRATEGY_OUTPUT = RESULTS_PATH / "report_migration_strategy.csv"

# Optional E4 / reachability sources (used if they exist)
REACHABILITY_CSV = RESULTS_PATH / "report_reachability.csv"
SIMBOLS_IMPL_CSV = RESULTS_PATH / "symbol_implicit.csv"
EQUIVALENCES_CSV = RESULTS_PATH / "equivalences.csv"

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
    """Safely converts a string to float."""
    if not val or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def clip(val, max_val):
    """Simulates numpy/pandas .clip()."""
    return min(val, max_val)


def load_reachability():
    """Returns dict (File, Unit) → Status. Empty if the CSV does not exist."""
    result = {}
    if not REACHABILITY_CSV.exists():
        return result
    with open(REACHABILITY_CSV, encoding="utf-8-sig", errors="replace") as f:
        for row in csv.DictReader(f):
            key = (row.get("File", "").strip(), row.get("Unit", "").strip())
            result[key] = row.get("Status", "").strip()
    return result


def load_e4():
    """
    Returns (impl_none_set, equiv_set):
      impl_none_set — (File, Unit) that have IMPLICIT NONE (Is_None == YES)
      equiv_set     — (File, Unit) that have at least one EQUIVALENCE group
    Both empty if the CSVs do not exist.
    """
    impl_none_set = set()
    if SIMBOLS_IMPL_CSV.exists():
        with open(SIMBOLS_IMPL_CSV, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                if row.get("Is_None", "").strip() == "YES":
                    key = (row.get("File", "").strip(), row.get("Unit", "").strip())
                    impl_none_set.add(key)

    equiv_set = set()
    if EQUIVALENCES_CSV.exists():
        with open(EQUIVALENCES_CSV, encoding="utf-8-sig", errors="replace") as f:
            for row in csv.DictReader(f):
                key = (row.get("File", "").strip(), row.get("Unit", "").strip())
                equiv_set.add(key)

    return impl_none_set, equiv_set


def load_impact():
    """Loads the impact matrix into a dictionary for fast lookup."""
    impact_map = {}

    if not IMPACT_FILE.exists():
        print(f"ERROR: {IMPACT_FILE} not found")
        sys.exit(1)

    with open(IMPACT_FILE, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
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


def main():
    print("--- Cross Migration Analysis (Standard Lib) ---")

    # 1. Load Dependency data into memory (Hash Map)
    print("Loading impact matrix...")
    impact_map = load_impact()

    # 1b. Optional sources
    reach_map = load_reachability()
    impl_none_set, equiv_set = load_e4()
    if reach_map:
        print(f"  Reachability loaded: {len(reach_map)} units")
    if impl_none_set or equiv_set:
        print(f"  E4: {len(impl_none_set)} with IMPLICIT NONE, {len(equiv_set)} with EQUIVALENCE")

    # 2. Process Density and Cross-reference
    if not DENSITY_FILE.exists():
        print(f"ERROR: {DENSITY_FILE} not found")
        sys.exit(1)

    results = []

    print("Processing and classifying units...")
    with open(DENSITY_FILE, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)

        for row in reader:
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
    print("Sorting results by priority...")
    results.sort(key=lambda x: (x["Priority_Num"], -x["IVC"]))

    # 4. Export to CSV
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

    try:
        with open(STRATEGY_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=output_columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

        print(f"SUCCESS: Report generated at '{STRATEGY_OUTPUT}'")

        # Generate brief summary to console
        count = {}
        for r in results:
            est = r["Strategy"]
            count[est] = count.get(est, 0) + 1

        print("\n--- STRATEGY SUMMARY ---")
        for k, v in sorted(count.items()):
            print(f"{k}: {v}")

    except Exception as e:
        print(f"Error writing file: {e}")


if __name__ == "__main__":
    main()
