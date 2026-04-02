# profiler.py

## Purpose

Classifies every logical statement in every source file and computes statement
density profiles per unit. Also produces the `audit/` DEBUG files, which are
the primary intermediate artifact consumed by `complexity.py`,
`common_blocks.py`, `symbols.py`, `derived_types.py`, and — as a
diagnostic tool — `block_analysis.py`.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CODE_PATH` | `FORT_SRC` env var → `tests/fixtures/` | Path to the Fortran source directory |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_density.csv"` | Density profile output |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory for per-file DEBUG files |

---

## Inputs

- `<FORT_OUT>/inventory_report.csv`
- Fortran source files in `CODE_PATH`

---

## Outputs

### `<FORT_OUT>/report_density.csv`
One row per program unit.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `Total_Statements` | Total classified statements in this unit |
| `Total_Calc` | Statements in the calculation group |
| `Total_Control` | Statements in the control-flow group |
| `Total_IO` | Statements in the I/O group |
| `Total_Legacy` | Statements in the legacy group |
| `Total_Decl` | Statements in the declaration group |
| `Pct_Calc` | `Total_Calc / Total_Statements × 100` |
| `Pct_Control` | `Total_Control / Total_Statements × 100` |
| `Pct_IO` | `Total_IO / Total_Statements × 100` |
| `Pct_Legacy` | `Total_Legacy / Total_Statements × 100` |
| `Pct_Decl` | `Total_Decl / Total_Statements × 100` |
| `N_Common` | Count of COMMON statements |
| `N_Equiv` | Count of EQUIVALENCE statements |
| `N_Print` | Count of PRINT statements |
| `N_Write` | Count of WRITE statements |

### `<FORT_OUT>/audit/<filename>_DEBUG.csv`
One file per source file. One row per logical line.

| Column | Description |
| :--- | :--- |
| `Line` | Physical start line number |
| `Kind` | Statement kind (e.g. `IF_CONSTRUCT`, `DO_CONSTRUCT`, `ASSIGNMENT_STMT`, `COMMON_STMT`, `IO_STMT`, `COMMENT`, …) |
| `Content` | First 120 characters of the logical line text |

---

## Statement Groups

| Group | Kinds included |
| :--- | :--- |
| `CALC` | `ASSIGNMENT_STMT` + calculation actions (ALLOCATE, DEALLOCATE, POINTER_ACTION, …) |
| `CONTROL` | `IF_CONSTRUCT`, `DO_CONSTRUCT`, `SELECT_CONSTRUCT`, `ASSOCIATE_CONSTRUCT`, `WHERE_CONSTRUCT`, `FORALL_CONSTRUCT`, `CONTROL_STMT`, `ELSE_STMT`, `CASE_STMT` |
| `IO` | `IO_STMT` |
| `LEGACY` | `COMMON_STMT`, `EQUIVALENCE_STMT`, `DATA_STMT`, `NAMELIST_STMT` |
| `DECL` | `VAR_DECLARATION`, `PARAMETER_STMT`, `IMPLICIT_STMT`, `USE_STMT`, `IMPORT_STMT`, `TYPE_DEFINITION`, `ENUM_DEF`, `INTERFACE_BLOCK`, `CONTAINS_STMT`, `END_BLOCK_STMT` |

> **Note:** The statement group taxonomy (CALC, CONTROL, IO, LEGACY, DECL)
> is a project-defined classification. The groupings are designed to
> characterize Fortran code for migration analysis — they are not based on
> a published classification standard.

---

## Notes

- Statement classification uses `patterns_v2.py` regex patterns applied to
  each logical line after masking string literals to avoid false positives.
- Scope resolution assigns each statement to the innermost unit whose line
  range contains the statement's start line.
- The `<FORT_OUT>/audit/` directory is created automatically if it does not exist.
