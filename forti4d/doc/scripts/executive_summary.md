# executive_summary.py

## Purpose

Produces a high-level executive summary of the corpus: global metrics, type
distribution, largest files, legacy/I/O health indicators, and the most
critical and most orchestrating units.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTORY_FILE` | `RESULTS_PATH / "inventory_report.csv"` | Input: unit inventory |
| `IMPACT_FILE` | `RESULTS_PATH / "dep_03_impact_matrix.csv"` | Input: Fan-In / Fan-Out |
| `SYMBOLS_IMPL_CSV` | `RESULTS_PATH / "symbol_implicit.csv"` | Optional: IMPLICIT NONE coverage |
| `EQUIVALENCES_CSV` | `RESULTS_PATH / "equivalences.csv"` | Optional: EQUIVALENCE aliasing |
| `COMMON_USAGE_CSV` | `RESULTS_PATH / "common_usage.csv"` | Optional: COMMON block usage |
| `SYMBOLS_VARS_CSV` | `RESULTS_PATH / "symbol_variables.csv"` | Optional: variable density per unit |
| `OUT_MD` | `RESULTS_PATH / "PROJECT_SUMMARY.md"` | Output: Markdown summary |
| `OUT_CSV` | `RESULTS_PATH / "file_statistics.csv"` | Output: per-file statistics |

---

## Inputs

Required:
- `<FORT_OUT>/inventory_report.csv`
- `<FORT_OUT>/dep_03_impact_matrix.csv`

Optional (section 5 is generated only when at least one of these exists):
- `<FORT_OUT>/symbol_implicit.csv`
- `<FORT_OUT>/equivalences.csv`
- `<FORT_OUT>/common_usage.csv`
- `<FORT_OUT>/symbol_variables.csv`

---

## Outputs

### `<FORT_OUT>/PROJECT_SUMMARY.md`

Markdown document with the following sections:

1. **Global Metrics** — total files, LOC, units, average LOC per file
2. **Unit Type Distribution** — count and % per type
3. **Top 10 Largest Files** — sorted by LOC, with unit count and types
4. **Health Indicators (Legacy)** — units with legacy constructs and I/O,
   with frequency tables for each construct type
5. **Scope Health (E4)** — IMPLICIT NONE coverage, EQUIVALENCE and COMMON
   block exposure, scope-clean unit count, top 5 by variable density.
   Only generated when at least one E4 optional source is present.
6. **Critical Units (highest Fan-In)** — top 15 most reused units
7. **Orchestrating Units (highest Fan-Out)** — top 15 units with most dependencies

### `<FORT_OUT>/file_statistics.csv`

One row per source file.

| Column | Description |
| :--- | :--- |
| `File` | Source file relative path (e.g. `subdir/file.f90`); equals the basename for flat single-directory projects |
| `Total_Lines` | Total LOC (from root-level units only, to avoid double-counting) |
| `Total_Units` | Number of units in the file |
| `Has_Legacy` | `YES` / `NO` |
| `Has_IO` | `YES` / `NO` |
| `Types_Present` | Semicolon-separated list of unit types in the file |

---

## Notes

- LOC is taken from the `Total_Lines` column of the inventory. Only
  root-level units (`Parent = GLOBAL`) are summed per file to avoid
  double-counting nested units.
- The Legacy and I/O percentages in the Markdown report are computed as
  *units with at least one flag / total units*, not as raw flag counts.
- **Scope-clean** units in section 5 are those with `IMPLICIT NONE`,
  no EQUIVALENCE groups, and no COMMON blocks — the safest candidates
  for direct migration.
- The variable density top-5 counts only non-PARAMETER declarations
  (`Is_Parameter != YES` in `symbol_variables.csv`).
- `file_statistics.csv` is not affected by the E4 optional sources.

---

## Known Limitation

Like `cross_analysis`, `executive_summary` runs at step 7 — before the E4
scripts (`symbols`, `derived_types`, `equivalences`, steps 10–12) and
`reachability` (step 13). Section 5 (Scope Health) is therefore always
absent in a standard full pipeline run.

To generate a complete summary including E4 data, re-run after the pipeline
completes:

```bash
forti4d --from executive_summary --only executive_summary
```

**Planned fix (v0.8):** reposition both `cross_analysis` and
`executive_summary` after `reachability` in the pipeline.
