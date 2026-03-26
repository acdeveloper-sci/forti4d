# simbolos.py

## Purpose

Extracts the symbol-level microstructure of each program unit: variable
declarations, formal parameters of subroutines/functions, and IMPLICIT rules.
Produces three normalized CSV reports that populate the Eje Z (scope) layer of
the MI4D model — the information needed to understand *what is declared* inside
each unit, not just that the unit exists.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `RUTA_AUDIT` | `RUTA_RESULTADOS / "audit"` | Directory containing `*_DEBUG.csv` files |
| `SALIDA_VARS` | `RUTA_RESULTADOS / "simbolos_variables.csv"` | Variables and constants per unit |
| `SALIDA_FIRMAS` | `RUTA_RESULTADOS / "simbolos_firmas.csv"` | Formal parameters per subroutine/function |
| `SALIDA_IMPL` | `RUTA_RESULTADOS / "simbolos_implicit.csv"` | IMPLICIT rules per unit |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file — reads lines
  classified as `VAR_DECLARATION`, `PARAMETER_STMT`, `IMPLICIT_STMT`,
  `COMMON_STMT`, `SUBROUTINE_UNIT`, or `FUNCTION_UNIT`.
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`) — used for
  scope resolution (which unit each line belongs to).

---

## Outputs

### `<FORT_OUT>/simbolos_variables.csv`
One row per declared variable or PARAMETER constant.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Containing unit name |
| `Tipo_Unidad` | Unit type (SUBROUTINE, FUNCTION, PROGRAM, etc.) |
| `Linea` | Line number of the declaration |
| `Nombre_Var` | Variable name (uppercase) |
| `Tipo_Fortran` | Base type: `INTEGER`, `REAL`, `CHARACTER`, `TYPE`, etc. |
| `Kind_Param` | KIND or byte-size modifier, e.g. `8`, `*4`, `*8` |
| `Dimension` | Array dimension spec, e.g. `100` or `N,M` or `0:10`; empty if scalar |
| `Atributos` | Pipe-separated attribute list, e.g. `INTENT(IN)\|DIMENSION(10)` |
| `Intent` | `IN`, `OUT`, or `INOUT` if declared; empty otherwise |
| `Valor_Inicial` | Compile-time value for PARAMETER constants; empty for regular vars |
| `Es_Parametro` | `SI` if the variable is a PARAMETER constant, `NO` otherwise |
| `En_Common` | COMMON block name if the variable appears in a COMMON statement; empty otherwise |
| `Truncada` | `SI` if the source line was near the 120-character audit truncation limit |

### `<FORT_OUT>/simbolos_firmas.csv`
One row per formal argument of each SUBROUTINE or FUNCTION.
Units with no arguments produce no rows.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Subroutine or function name |
| `Tipo_Unidad` | `SUBROUTINE` or `FUNCTION` |
| `Linea_Firma` | Line number of the unit header |
| `Posicion` | Argument position (1-based) |
| `Nombre_Arg` | Formal argument name (uppercase) |
| `Tipo_Retorno` | Declared return type for FUNCTION units (e.g. `REAL`, `REAL*8`); empty for SUBROUTINE |

### `<FORT_OUT>/simbolos_implicit.csv`
One row per IMPLICIT statement found in each unit.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo_Unidad` | Unit type |
| `Linea` | Line number of the IMPLICIT statement |
| `Regla` | `NONE` for `IMPLICIT NONE`; otherwise the rule as written in the source |
| `Es_None` | `SI` if the statement is `IMPLICIT NONE`, `NO` otherwise |

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
identified post-processing: the `En_Common` field is filled with the block name
after all lines of all files have been scanned. This cross-reference works at
unit scope — a variable in unit A and the same-named variable in unit B are
treated independently.

The blank (unnamed) COMMON is represented as `(BLANK)`, consistent with
`common_blocks.py`.

---

## Notes

- Attribute-only statements (`ALLOCATABLE :: X`, `DIMENSION X(100)`) are
  captured with an empty `Tipo_Fortran`; they represent supplementary
  attributes, not type declarations.
- F77 alternate-return arguments (`*`) are skipped in `simbolos_firmas.csv`.
- `EQUIVALENCE` aliasing is detected by `perfilador.py` as a legacy flag but
  is not analyzed here; it is reserved for a future `equivalencias.py` step.
- This script requires `perfilador` (audit CSVs) and `inventario` to have run
  first. In the pipeline it is step 10, immediately after `common_blocks`.
- Derived TYPE definitions and their component fields are extracted separately
  by `tipos_derivados.py` (step 11).
