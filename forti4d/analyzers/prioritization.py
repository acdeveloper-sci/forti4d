"""
priorizacion.py
Computes a composite risk/effort score for each unit and ranks them
for migration planning.

Score (0-100) weighted across five signals:
  CC           30%  — cyclomatic complexity (normalized by corpus max)
  Fan_In       30%  — call-graph criticality (normalized by corpus max)
  Pct_Legacy   20%  — legacy construct density
  Clone        15%  — penalty for being part of a diverged/similar duplicate group
  E4_Risk      5%   — E4 scope risk: no IMPLICIT NONE and/or EQUIVALENCE aliasing

Units with Estado = NO_REACHABLE (dead code) are separated into a
DEAD_CODE priority tier and placed at the bottom of the list.

Output: report_prioritization.csv
"""

import csv
from collections import defaultdict
from pathlib import Path

from forti4d.config import RESULTS_PATH

# =============================================================================
# CONFIGURATION
# =============================================================================
CONSOL_PATH = RESULTS_PATH / "report_consolidated.csv"
CLONES_PATH = RESULTS_PATH / "report_clones.csv"
STRATEGY_PATH = RESULTS_PATH / "report_migration_strategy.csv"
CSV_OUTPUT = RESULTS_PATH / "report_prioritization.csv"

# Score weights (must sum to 1.0)
W_CC = 0.30
W_FAN_IN = 0.30
W_LEGACY = 0.20
W_CLONE = 0.15
W_E4 = 0.05

# E4_Risk sub-weights (must sum to 1.0)
# No IMPLICIT NONE: harder to infer types, higher migration risk.
# EQUIVALENCE: memory aliasing, incompatible with safe refactoring.
W_E4_IMPL = 0.70  # no IMPLICIT NONE
W_E4_EQUIV = 0.30  # has EQUIVALENCE aliasing

# Clone penalty per worst state
CLONE_PENALTY = {
    "DIVERGED": 1.0,
    "SIMILAR": 0.5,
    "IDENTICAL": 0.25,
}

# Priority thresholds (applied to score 0-100).
# In practice the maximum achievable score is ~50-60 since no unit
# simultaneously maxes out all four signals.
THRESH_CRITICAL = 40
THRESH_HIGH = 25
THRESH_MEDIUM = 12


# =============================================================================
# HELPERS
# =============================================================================


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def percentile(values: list, pct: float) -> float:
    """Returns the pct-th percentile of values (0-100 scale)."""
    s = sorted(v for v in values if v > 0)
    if not s:
        return 1.0
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def classify_priority(score: float) -> str:
    if score >= THRESH_CRITICAL:
        return "CRITICAL"
    if score >= THRESH_HIGH:
        return "HIGH"
    if score >= THRESH_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _order_priority(p: str) -> int:
    return {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "DEAD_CODE": 4}[p]


# =============================================================================
# LOAD FROM SOURCE
# =============================================================================


def load_consolidated() -> list:
    if not CONSOL_PATH.exists():
        print(f"ERROR: {CONSOL_PATH} not found. Run consolidate.py first.")
        return []
    with open(CONSOL_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_strategy() -> dict:
    """Returns dict: (file, unit_upper) → Strategy string."""
    result = {}
    if not STRATEGY_PATH.exists():
        return result
    with open(STRATEGY_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = row.get("File", "").strip()
            u = row.get("Unit", "").strip().upper()
            if a and u:
                result[(a, u)] = row.get("Strategy", "").strip()
    return result


def load_worst_state_clone() -> dict:
    """
    Returns dict: (file, unit_upper) → worst clone Estado for that unit.
    A unit appears in clones as File_A or File_B.
    """
    _rank = {"DIVERGED": 3, "SIMILAR": 2, "IDENTICAL": 1}
    worst = {}

    if not CLONES_PATH.exists():
        return worst

    with open(CLONES_PATH, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("Unit", "").strip().upper()
            status = row.get("Status", "").strip()
            file_a = row.get("File_A", "").strip()
            file_b = row.get("File_B", "").strip()

            for file in (file_a, file_b):
                key = (file, name)
                rank_curr = _rank.get(worst.get(key, ""), 0)
                rank_new = _rank.get(status, 0)
                if rank_new > rank_curr:
                    worst[key] = status

    return worst


# =============================================================================
# SCORING
# =============================================================================


def calculate_scores(rows: list, clones: dict, strategy: dict) -> list:
    # Normalization reference: 95th percentile among reachable units.
    # Using percentile instead of max prevents a single outlier (e.g. an
    # IMPLICIT-MAIN with CC in the thousands) from compressing the entire scale.
    # Values above the reference are capped at 1.0.
    alive = [r for r in rows if r.get("Status", "") != "UNREACHABLE"]

    ref_cc = percentile([safe_float(r.get("CC")) for r in alive], 95) or 1.0
    ref_fanin = percentile([safe_float(r.get("Fan_In")) for r in alive], 95) or 1.0

    result = []
    for row in rows:
        file = row.get("File", "").strip()
        unit = row.get("Unit", "").strip()
        status = row.get("Status", "").strip()

        cc = safe_float(row.get("CC"))
        fan_in = safe_float(row.get("Fan_In"))
        legacy = safe_float(row.get("Pct_Legacy"))

        # Normalized components (0-1), capped at 1.0
        s_cc = min(cc / ref_cc, 1.0)
        s_fanin = min(fan_in / ref_fanin, 1.0)
        s_legacy = legacy / 100.0

        # Clone component
        status_clone = clones.get((file, unit.upper()), "")
        s_clone = CLONE_PENALTY.get(status_clone, 0.0)

        # E4 Risk component
        no_impl_none = row.get("Implicit_None", "") != "YES"
        has_equiv = row.get("Has_Equiv", "") == "YES"
        s_e4 = min(W_E4_IMPL * (1.0 if no_impl_none else 0.0) + W_E4_EQUIV * (1.0 if has_equiv else 0.0), 1.0)

        # Weighted score (0-100)
        score = (W_CC * s_cc + W_FAN_IN * s_fanin + W_LEGACY * s_legacy + W_CLONE * s_clone + W_E4 * s_e4) * 100

        if status == "UNREACHABLE":
            priority = "DEAD_CODE"
        else:
            priority = classify_priority(score)

        strategy_unit = strategy.get((file, unit.upper()), "")

        result.append(
            {
                "Priority": priority,
                "Score": round(score, 1),
                "File": file,
                "Unit": unit,
                "Type": row.get("Type", ""),
                "CC": row.get("CC", ""),
                "Fan_In": row.get("Fan_In", ""),
                "Pct_Legacy": row.get("Pct_Legacy", ""),
                "Reachability_Status": status,
                "Clone_Status": status_clone,
                "Strategy": strategy_unit,
                "Implicit_None": row.get("Implicit_None", ""),
                "Has_Equiv": row.get("Has_Equiv", ""),
                "Score_CC": round(s_cc * W_CC * 100, 1),
                "Score_FanIn": round(s_fanin * W_FAN_IN * 100, 1),
                "Score_Legacy": round(s_legacy * W_LEGACY * 100, 1),
                "Score_Clon": round(s_clone * W_CLONE * 100, 1),
                "Score_E4": round(s_e4 * W_E4 * 100, 1),
            }
        )

    # Sort: by priority tier first, then by score descending
    result.sort(key=lambda r: (_order_priority(r["Priority"]), -r["Score"]))
    return result


# =============================================================================
# MAIN
# =============================================================================


def main():
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)

    rows = load_consolidated()
    if not rows:
        return

    clones = load_worst_state_clone()
    strategy = load_strategy()

    result = calculate_scores(rows, clones, strategy)

    columns = [
        "Priority",
        "Score",
        "File",
        "Unit",
        "Type",
        "CC",
        "Fan_In",
        "Pct_Legacy",
        "Reachability_Status",
        "Clone_Status",
        "Strategy",
        "Implicit_None",
        "Has_Equiv",
        "Score_CC",
        "Score_FanIn",
        "Score_Legacy",
        "Score_Clon",
        "Score_E4",
    ]

    with open(CSV_OUTPUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(result)

    # Summary
    count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "DEAD_CODE": 0}
    for r in result:
        count[r["Priority"]] += 1

    print(f"\n{len(result)} units prioritized")
    print(f"  CRITICAL  : {count['CRITICAL']}")
    print(f"  HIGH      : {count['HIGH']}")
    print(f"  MEDIUM    : {count['MEDIUM']}")
    print(f"  LOW       : {count['LOW']}")
    print(f"  DEAD_CODE : {count['DEAD_CODE']}")
    print(f"\nTop 10:")
    for r in result[:10]:
        print(f"  [{r['Priority']:<9}] {r['Score']:>5}  {r['Unit']:<25} CC={r['CC']}  FanIn={r['Fan_In']}")
    print(f"\nGenerated: {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
