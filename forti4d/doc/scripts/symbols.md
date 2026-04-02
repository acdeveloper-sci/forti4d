# symbols.py

## Purpose

Extracts the symbol-level microstructure of each program unit: variable
declarations, formal parameters of subroutines/functions, and IMPLICIT rules.
Produces three normalized CSV reports that populate the Axis Z (scope) layer of
the MI4D model — the information needed to understand *what is declared* inside
each unit, not just that the unit exists.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory containing `*_DEBUG.csv` files |
| `OUTPUT_VARS` | `RESULTS_PATH / "symbol_variables.csv"` | Variables and constants per unit |
| `OUTPUT_SIGNATURES` | `RESULTS_PATH / "symbol_signatures.csv"` | Formal parameters per subroutine/function |
| `OUTPUT_IMPLICIT` | `RESULTS_PATH / "symbol_implicit.csv"` | IMPLICIT rules per unit |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file — reads lines
  classified as `VAR_DECLARATION`, `PARAMETER_STMT`, `IMPLICIT_STMT`,
  `COMMON_STMT`, `SUBROUTINE_UNIT`, or `FUNCTION_UNIT`.
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`) — used for
  scope resolution (which unit each line belongs to).

---

## Outputs

### `<FORT_OUT>/symbol_variables.csv`
One row per declared variable or PARAMETER constant.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Containing unit name |
| `Unit_Type` | Unit type (SUBROUTINE, FUNCTION, PROGRAM, etc.) |
| `Line` | Line number of the declaration |
| `Var_Name` | Variable name (uppercase) |
| `Fortran_Type` | Base type: `INTEGER`, `REAL`, `CHARACTER`, `TYPE`, etc. |
| `Kind_Param` | KIND or byte-size modifier, e.g. `8`, `*4`, `*8` |
| `Dimension` | Array dimension spec, e.g. `100` or `N,M` or `0:10`; empty if scalar |
| `Attributes` | Pipe-separated attribute list, e.g. `INTENT(IN)\|DIMENSION(10)` |
| `Intent` | `IN`, `OUT`, or `INOUT` if declared; empty otherwise |
| `Initial_Value` | Compile-time value for PARAMETER constants; empty for regular vars |
| `Is_Parameter` | `YES` if the variable is a PARAMETER constant, `NO` otherwise |
| `In_Common` | COMMON block name if the variable appears in a COMMON statement; empty otherwise |
| `Truncated` | `YES` if the source line was near the 120-character audit truncation limit |

### `<FORT_OUT>/symbol_signatures.csv`
One row per formal argument of each SUBROUTINE or FUNCTION.
Units with no arguments produce no rows.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Subroutine or function name |
| `Unit_Type` | `SUBROUTINE` or `FUNCTION` |
| `Signature_Line` | Line number of the unit header |
| `Position` | Argument position (1-based) |
| `Arg_Name` | Formal argument name (uppercase) |
| `Return_Type` | Declared return type for FUNCTION units (e.g. `REAL`, `REAL*8`); empty for SUBROUTINE |

### `<FORT_OUT>/symbol_implicit.csv`
One row per IMPLICIT statement found in each unit.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Unit_Type` | Unit type |
| `Line` | Line number of the IMPLICIT statement |
| `Rule` | `NONE` for `IMPLICIT NONE`; otherwise the rule as written in the source |
| `Is_None` | `YES` if the statement is `IMPLICIT NONE`, `NO` otherwise |

---

## Declaration Parsing

The parser handles both Fortran dialects by detecting the presence of `::`:

| Syntax | Style | Example |
| :--- | :--- | :--- |
| `TYPE [attrs] :: var_list` | F90 | `REAL(KIND=8), INTENT(IN) :: X, Y` |
| `TYPE[*size] var_list` | F77 | `REAL*8 X, Y(100)` |
| `PARAMETER (NAME=val, ...)` | F77 standalone | `PARAMETER (PI=3.14159, N=100)` |
| `TYPE, PARAMETER :: NAME=val` | F90 inline | `INTEGER, PARAMETER :: MAX=200` |
| `ATTR var_list` | F90 attr-only | `DIMENSION X(100)`, `ALLOCATABLE Y` |

Variable lists are split by comma with a paren-depth counter so that array
dimensions — e.g. `A(10,5)` — are never broken at the interior comma.

KIND expressions with nested parentheses are handled correctly:
`REAL(KIND=selected_real_kind(15,307))` extracts `selected_real_kind(15,307)`.

---

## COMMON Cross-Reference

Variables that appear in a `COMMON` statement within the same unit are
identified post-processing: the `In_Common` field is filled with the block name
after all lines of all files have been scanned. This cross-reference works at
unit scope — a variable in unit A and the same-named variable in unit B are
treated independently.

The blank (unnamed) COMMON is represented as `(BLANK)`, consistent with
`common_blocks.py`.

---

## Notes

- Attribute-only statements (`ALLOCATABLE :: X`, `DIMENSION X(100)`) are
  captured with an empty `Fortran_Type`; they represent supplementary
  attributes, not type declarations.
- F77 alternate-return arguments (`*`) are skipped in `symbol_signatures.csv`.
- `EQUIVALENCE` aliasing is detected by `profiler.py` as a legacy flag but
  is not analyzed here; it is handled by `equivalences.py` (step 12).
- This script requires `profiler.py` (audit CSVs) and `inventory.py` to have
  run first. In the pipeline it is step 10, immediately after `common_blocks`.
- Derived TYPE definitions and their component fields are extracted separately
  by `derived_types.py` (step 11).
