# cross_analysis.py

## Purpose

Assigns a migration strategy to each unit by crossing statement density
metrics with call graph coupling data. Computes two composite indices and
applies a rule engine to recommend an action for each unit.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `DENSITY_FILE` | `RESULTS_PATH / "report_density.csv"` | Input: statement density profiles |
| `IMPACT_FILE` | `RESULTS_PATH / "dep_03_impact_matrix.csv"` | Input: Fan-In / Fan-Out |
| `OUTPUT_FILE` | `RESULTS_PATH / "report_migration_strategy.csv"` | Output |
| `REACHABILITY_CSV` | `RESULTS_PATH / "report_reachability.csv"` | Optional: reachability status |
| `SYMBOLS_IMPL_CSV` | `RESULTS_PATH / "symbol_implicit.csv"` | Optional: IMPLICIT NONE status |
| `EQUIVALENCES_CSV` | `RESULTS_PATH / "equivalences.csv"` | Optional: EQUIVALENCE aliasing groups |

E4 penalty parameters: `E4_PENALTY_MAX = 7.0`, `W_E4_IMPL = 0.70`, `W_E4_EQUIV = 0.30`.

---

## Inputs

Required:
- `<FORT_OUT>/report_density.csv`
- `<FORT_OUT>/dep_03_impact_matrix.csv`

Optional (used if present, silently skipped otherwise):
- `<FORT_OUT>/report_reachability.csv` — enables confirmed dead-code rule
- `<FORT_OUT>/symbol_implicit.csv` — enables E4 ICM penalty
- `<FORT_OUT>/equivalences.csv` — enables E4 ICM penalty

---

## Output: `<FORT_OUT>/report_migration_strategy.csv`

One row per unit, sorted by `Priority_Num` ascending (most urgent first),
then by `IVC` descending within the same priority.

| Column | Description |
| :--- | :--- |
| `Priority_Num` | Numeric priority (1 = most urgent) |
| `Strategy` | Recommended action (see below) |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `ICM` | Migration Complexity Index (base + E4 penalty) |
| `IVC` | Calculation Value Index (= `Pct_Calc`) |
| `Pct_Calc` | % calculation statements |
| `Pct_Control` | % control-flow statements |
| `Pct_Legacy` | % legacy statements |
| `Fan_In` | Number of callers |
| `Fan_Out` | Number of callees |
| `Reachability_Status` | Reachability status from `reachability.py` (empty if CSV not present) |
| `Explanation` | Human-readable reason for the strategy |

---

## Composite Indices

**IVC (Calculation Value Index):** equals `Pct_Calc`. Measures how much
of the unit is pure algorithmic computation.

**ICM (Migration Complexity Index):**
```
ICM_base = 0.15 × Pct_Control
         + 0.45 × min(Pct_Legacy × 4, 100)
         + 0.20 × min(Fan_Out × 5, 100)
         + 0.20 × min(Fan_In × 5, 100)

E4_penalty = 7.0 × (0.70 × no_IMPLICIT_NONE + 0.30 × has_EQUIVALENCE)

ICM = ICM_base + E4_penalty
```

The E4 penalty is applied only when `symbol_implicit.csv` and/or
`equivalences.csv` are present. `no_IMPLICIT_NONE` is 1 when the unit
does not have `IMPLICIT NONE`; `has_EQUIVALENCE` is 1 when the unit
has at least one EQUIVALENCE aliasing group. Maximum additive penalty: 7.0 points.

> **Note:** ICM, IVC, and their weights (0.15 / 0.45 / 0.20 / 0.20 for ICM base;
> 0.70 / 0.30 for the E4 penalty) are project-defined composite indices, not
> industry-standard metrics. The rule engine thresholds (IVC > 50, ICM < 30,
> ICM > 25, etc.) are empirically calibrated against real Fortran legacy corpora.

---

## Strategy Rule Engine

Rules are evaluated in order; the first match wins.

| Priority | Rule | Strategy | Condition |
| :---: | :--- | :--- | :--- |
| — | -1 | `ELIMINATE` | `Reachability_Status = UNREACHABLE` — confirmed dead code (requires reachability CSV) |
| 1 | 0 | `ANALYZE_UTILITY` / `ELIMINATE` | Fan-In = 0 (proxy dead-code check when reachability not available) |
| 2 | 1 | `DIRECT_MIGRATION` | IVC > 50 and ICM < 30 — pure algorithm, low coupling |
| 3 | 2 | `REPLACE_LIB` | Pct_IO > 30 or Pct_Decl > 40, and IVC < 20 — infrastructure/boilerplate |
| 4 | 3 | `REFACTOR_CORE` | ICM > 25 and Fan-In > 5 — high-risk, high-dependency knot |
| 5 | 4 | `REWRITE_ISOLATED` | ICM > 20 — complex but low systemic impact |
| 6 | default | `STANDARD_MIGRATION` | All other connected units |

**Rule -1** fires before any other rule when `report_reachability.csv` is
present. Units confirmed as `UNREACHABLE` always receive `ELIMINATE`
regardless of Fan-In, ICM, or IVC values.

Units with type `PROGRAM`, `IMPLICIT-MAIN`, `MODULE`, or `BLOCK DATA` are
exempt from the Fan-In = 0 dead-code rule (Rule 0).

---

## Known Limitation

In a full pipeline run, `cross_analysis` executes at step 6 — before
`symbols` (step 10), `equivalences` (step 12), and `reachability` (step 13).
As a result, the three optional inputs are **never available** during a
standard pipeline run; the E4 penalty and the `UNREACHABLE → ELIMINATE` rule
are silently skipped.

To use the full rule engine, re-run `cross_analysis` manually after the
pipeline completes:

```bash
forti4d --from cross_analysis --only cross_analysis
```

**Planned fix (v0.8):** move `cross_analysis` to after `reachability` in the
pipeline. The three optional inputs will become required.
