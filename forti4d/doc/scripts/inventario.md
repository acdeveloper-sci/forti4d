# inventario.py

## Purpose

Foundation of the entire pipeline. Scans all Fortran source files and builds
a complete inventory of every program unit: its type, parent unit, line range,
and audit flags for legacy constructs and I/O statements.

All other scripts depend on `<FORT_OUT>/reporte_inventario.csv`.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CARPETA_CODIGO` | `FORT_SRC` env var → `../athys/mercedes/` | Path to the Fortran source directory |
| `ARCHIVO_SALIDA` | `RUTA_RESULTADOS / "reporte_inventario.csv"` | Output file |

---

## Input

Fortran source files in `CARPETA_CODIGO`. Processes `.f90`, `.f95`, `.f`, `.for`, `.f77`.

---

## Output: `<FORT_OUT>/reporte_inventario.csv`

One row per program unit found.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name (basename only) |
| `Tipo` | Unit type: `PROGRAM`, `IMPLICIT-MAIN`, `MODULE`, `SUBROUTINE`, `FUNCTION`, `BLOCK_DATA`, `GENERIC_INTERFACE` |
| `Nombre` | Unit name as declared in source |
| `Padre` | Name of the enclosing unit, or `GLOBAL` if top-level |
| `Linea_Inicio` | First physical line of the unit |
| `Linea_Fin` | Last physical line of the unit |
| `Lineas_Total` | `Linea_Fin - Linea_Inicio + 1` |
| `Legacy` | Comma-separated list of legacy constructs found (COMMON, GOTO, EQUIVALENCE, etc.) |
| `IO` | Comma-separated list of I/O statements found (OPEN, READ, WRITE, CLOSE, etc.) |
| `Custom` | Reserved for additional audit flags |

---

## Unit Types

| Type | Description |
| :--- | :--- |
| `PROGRAM` | Explicit `PROGRAM` statement |
| `IMPLICIT-MAIN` | File that compiles to an executable with no `PROGRAM` statement |
| `MODULE` | F90 `MODULE` |
| `SUBROUTINE` | `SUBROUTINE` |
| `FUNCTION` | `FUNCTION` |
| `BLOCK_DATA` | F77 `BLOCK DATA` |
| `GENERIC_INTERFACE` | `INTERFACE` block inside a module |

---

## Notes

- **Scope resolution** uses a stack: when a unit-opening statement is matched,
  a new scope is pushed; when the corresponding `END` is matched, it is popped.
  The innermost scope is the current unit's parent.
- `Linea_Fin` for `GENERIC_INTERFACE` is set equal to `Linea_Inicio` by design
  (interfaces are treated as point declarations, not as containers).
- `IMPLICIT-MAIN` is detected when a file contains executable statements but
  no `PROGRAM` statement at the top level.
