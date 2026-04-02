# inventory.py

## Purpose

Foundation of the entire pipeline. Scans all Fortran source files and builds
a complete inventory of every program unit: its type, parent unit, line range,
and audit flags for legacy constructs and I/O statements.

All other scripts depend on `<FORT_OUT>/inventory_report.csv`.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CODE_PATH` | `FORT_SRC` env var → `tests/fixtures/` | Path to the Fortran source directory |
| `OUTPUT_FILE` | `RESULTS_PATH / "inventory_report.csv"` | Output file |

---

## Input

Fortran source files in `CODE_PATH`. Processes `.f90`, `.f95`, `.f`, `.for`, `.f77`.

---

## Output: `<FORT_OUT>/inventory_report.csv`

One row per program unit found.

| Column | Description |
| :--- | :--- |
| `File` | Source file name (basename only) |
| `Type` | Unit type: `PROGRAM`, `IMPLICIT-MAIN`, `MODULE`, `SUBROUTINE`, `FUNCTION`, `BLOCK_DATA`, `GENERIC_INTERFACE` |
| `Name` | Unit name as declared in source |
| `Parent` | Name of the enclosing unit, or `GLOBAL` if top-level |
| `Start_Line` | First physical line of the unit |
| `End_Line` | Last physical line of the unit |
| `Total_Lines` | `End_Line - Start_Line + 1` |
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
- `End_Line` for `GENERIC_INTERFACE` is set equal to `Start_Line` by design
  (interfaces are treated as point declarations, not as containers).
- `IMPLICIT-MAIN` is detected when a file contains executable statements but
  no `PROGRAM` statement at the top level.
