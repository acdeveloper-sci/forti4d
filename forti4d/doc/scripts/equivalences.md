# equivalences.py

## Purpose

Detects EQUIVALENCE aliasing groups within each program unit. EQUIVALENCE
statements cause two or more variables to share the same memory location —
a legacy F77 construct that complicates static analysis, type inference, and
safe refactoring. This script resolves transitive aliasing using a union-find
algorithm and produces a normalized report of all aliasing groups.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory containing `*_DEBUG.csv` files |
| `OUTPUT_CSV` | `RESULTS_PATH / "equivalences.csv"` | One row per variable per aliasing group |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file — reads lines
  classified as `EQUIVALENCE_STMT`.
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`) — used for
  scope resolution (which unit each statement belongs to).

---

## Output: `<FORT_OUT>/equivalences.csv`

One row per variable member of each aliasing group.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Containing unit name |
| `Unit_Type` | Unit type (SUBROUTINE, FUNCTION, MODULE, etc.) |
| `Group_ID` | Sequential group identifier within the unit (1-based) |
| `Position` | Position of this variable within the group (1-based, sorted alphabetically) |
| `Var_Name` | Variable name (uppercase); array subscripts are stripped |
| `N_Members` | Total number of variables in this aliasing group |
| `Stmt_Lines` | Semicolon-separated line numbers of the EQUIVALENCE statements that define this group |

---

## Union-Find Algorithm

EQUIVALENCE aliasing is transitive: if `A` aliases `B` and `B` aliases `C`
(across separate statements), then `A`, `B`, and `C` form a single group.

The script processes all `EQUIVALENCE_STMT` lines within a unit and builds a
union-find structure:

1. Parse each statement to extract parenthesized variable lists.
2. Union all variables within each list.
3. After processing all statements in the unit, extract connected components.
4. Assign sequential `Group_ID` values (sorted by first member name).

This handles the general case correctly, including:

```fortran
EQUIVALENCE (A, B)   ! Group: {A, B}
EQUIVALENCE (B, C)   ! Merges into: {A, B, C}
```

---

## Notes

- Array subscripts in EQUIVALENCE references (e.g. `A(1)`) are stripped — only
  the variable name is recorded. Offset-based partial aliasing is not analyzed.
- Units with no EQUIVALENCE statements produce no rows.
- The presence of EQUIVALENCE in a unit is a legacy indicator and is reflected
  in `Pct_Legacy` in `report_density.csv` (detected by `profiler.py`).
- This script requires `profiler.py` (audit CSVs) and `inventory.py` to have
  run first. In the pipeline it is step 12, immediately after `derived_types`.
