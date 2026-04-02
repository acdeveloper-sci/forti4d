# complexity.py

## Purpose

Computes McCabe cyclomatic complexity (CC) per program unit by counting
decision points from the `audit/*_DEBUG.csv` files produced by `profiler.py`.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory containing `*_DEBUG.csv` files |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_complexity.csv"` | Output file |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`)

---

## Output: `<FORT_OUT>/report_complexity.csv`

One row per program unit, sorted by CC descending.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `CC` | McCabe cyclomatic complexity |
| `Level` | Complexity level: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `Start_Line` | First line of the unit |
| `End_Line` | Last line of the unit |
| `Total_Lines` | Physical line count of the unit |

---

## CC Calculation

McCabe cyclomatic complexity measures the number of linearly independent paths
through a unit's control flow. See [McCabe (1976)](https://doi.org/10.1109/TSE.1976.233837)
or the [Wikipedia article](https://en.wikipedia.org/wiki/Cyclomatic_complexity) for background.

CC = 1 + (number of decision points in the unit)

**Decision point rules:**

| Statement kind | Count |
| :--- | :--- |
| `IF_CONSTRUCT` | +1 (block IF and single-line IF) |
| `ELSE_STMT` | +1 only if `ELSE IF` / `ELSEIF`; plain `ELSE` = 0 |
| `DO_CONSTRUCT` | +1 |
| `SELECT_CONSTRUCT` | 0 (branches counted via CASE) |
| `CASE_STMT` | +1 unless `CASE DEFAULT` or `CLASS DEFAULT` |
| `WHERE_CONSTRUCT` | +1 |
| `FORALL_CONSTRUCT` | +1 |

---

## Complexity Scale

| Level | CC range | Meaning |
| :--- | :--- | :--- |
| `LOW` | 1 – 10 | Simple, easy to test |
| `MEDIUM` | 11 – 20 | Moderate complexity |
| `HIGH` | 21 – 50 | High complexity, refactoring recommended |
| `CRITICAL` | > 50 | Very high risk, hard to maintain |

> **Note:** The 4-level scale (LOW / MEDIUM / HIGH / CRITICAL) is a project
> adaptation. McCabe's original paper suggested 10 as a single complexity
> threshold. The extended scale and ranges used here are calibrated for
> Fortran legacy codebases.

---

## Notes

- Scope resolution assigns each decision point to the innermost unit whose
  `[Start_Line, End_Line]` range contains the statement's line number.
- CC is computed from `<FORT_OUT>/audit/` DEBUG files, not directly from source.
  `profiler.py` must be run first.
