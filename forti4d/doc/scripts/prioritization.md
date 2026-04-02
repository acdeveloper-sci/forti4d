# prioritization.py

## Purpose

Computes a composite risk/effort score for each program unit and ranks them
for migration planning. Combines five signals — complexity, criticality,
legacy density, clone status, and E4 scope risk — into a single ordered list.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CONSOL_PATH` | `RESULTS_PATH / "report_consolidated.csv"` | Input: per-unit metrics |
| `CLONES_PATH` | `RESULTS_PATH / "report_clones.csv"` | Input: clone state per pair |
| `STRATEGY_PATH` | `RESULTS_PATH / "report_migration_strategy.csv"` | Input: migration strategy |
| `CSV_OUTPUT` | `RESULTS_PATH / "report_prioritization.csv"` | Output |
| `W_CC` | `0.30` | Weight for cyclomatic complexity component |
| `W_FAN_IN` | `0.30` | Weight for Fan-In (criticality) component |
| `W_LEGACY` | `0.20` | Weight for legacy construct density component |
| `W_CLONE` | `0.15` | Weight for clone penalty component |
| `W_E4` | `0.05` | Weight for E4 scope risk component |
| `THRESH_CRITICAL` | `40` | Score threshold for `CRITICAL` priority |
| `THRESH_HIGH` | `25` | Score threshold for `HIGH` priority |
| `THRESH_MEDIUM` | `12` | Score threshold for `MEDIUM` priority |

> **Note on heuristics:** The component weights (`W_*`) and priority thresholds
> (`THRESH_*`) are project-defined values calibrated for typical Fortran legacy
> corpora. Adjust them if the score distribution is too concentrated in one tier.

---

## Inputs

- `<FORT_OUT>/report_consolidated.csv`
- `<FORT_OUT>/report_clones.csv`
- `<FORT_OUT>/report_migration_strategy.csv` (optional)

---

## Output: `<FORT_OUT>/report_prioritization.csv`

One row per program unit, sorted by priority tier then by score descending.
Dead code units appear last.

| Column | Description |
| :--- | :--- |
| `Priority` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, or `DEAD_CODE` |
| `Score` | Composite score 0–100 |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `CC` | McCabe cyclomatic complexity |
| `Fan_In` | Number of units that call this one |
| `Pct_Legacy` | Percentage of legacy statements |
| `Reachability_Status` | `REACHABLE`, `UNREACHABLE`, or `ENTRY_POINT` |
| `Clone_Status` | Worst clone state for this unit: `DIVERGED`, `SIMILAR`, `IDENTICAL`, or blank |
| `Strategy` | Migration strategy recommendation |
| `Implicit_None` | `YES` / `NO` / blank — from `symbol_implicit.csv` via consolidated |
| `Has_Equiv` | `YES` / `NO` — whether the unit has EQUIVALENCE aliasing |
| `Score_CC` | CC component contribution (0–30) |
| `Score_FanIn` | Fan-In component contribution (0–30) |
| `Score_Legacy` | Legacy component contribution (0–20) |
| `Score_Clon` | Clone component contribution (0–15) |
| `Score_E4` | E4 Risk component contribution (0–5) |

---

## Scoring

**Score = (W_CC × CC_norm + W_FAN_IN × FanIn_norm + W_LEGACY × Legacy_norm + W_CLONE × Clone_norm + W_E4 × E4_norm) × 100**

Each component is normalized to 0–1:

| Component | Normalization |
| :--- | :--- |
| CC | `min(CC / P95_CC, 1.0)` — 95th percentile of CC among reachable units |
| Fan_In | `min(Fan_In / P95_FanIn, 1.0)` — 95th percentile of Fan_In |
| Pct_Legacy | `Pct_Legacy / 100` |
| Clone | `1.0` if DIVERGED, `0.5` if SIMILAR, `0.25` if IDENTICAL, `0.0` if no clones |
| E4_Risk | `0.70` if no IMPLICIT NONE + `0.30` if has EQUIVALENCE (capped at 1.0) |

Units with no IMPLICIT statement (implicit typing active) are treated the same
as units with explicit non-NONE rules — both receive the full E4 penalty.

The 95th percentile is used as the normalization reference (instead of the
maximum) to prevent a single outlier — such as an IMPLICIT-MAIN unit with
very high CC — from compressing the entire scale.

---

## Priority Levels

| Level | Score | Meaning |
| :--- | :--- | :--- |
| `CRITICAL` | ≥ 40 | High complexity or criticality, requires early planning |
| `HIGH` | ≥ 25 | Significant risk in at least one dimension |
| `MEDIUM` | ≥ 12 | Moderate — plan but not urgent |
| `LOW` | < 12 | Low risk, straightforward migration |
| `DEAD_CODE` | — | `UNREACHABLE` — evaluate for deletion before migrating |

---

## Notes

- Normalization is computed only over reachable units (`Reachability_Status ≠ UNREACHABLE`)
  so that dead code does not skew the reference values.
- `Clone_Status` reflects the **worst** clone state among all pairs involving
  that unit. A unit that is IDENTICAL to one copy but DIVERGED from another
  is classified as DIVERGED.
- The component score columns (`Score_CC`, `Score_FanIn`, etc.) are included
  to help diagnose why a unit received its score and to calibrate weights.
