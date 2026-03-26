# tipos_derivados.py

## Purpose

Extracts derived TYPE definitions and their component fields from the audit
CSVs produced by `perfilador.py`. Populates the Eje Z (scope) layer of the
MI4D model at the type-structure level — the information needed to understand
the internal layout of user-defined data types, not just that they are used.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `RUTA_AUDIT` | `RUTA_RESULTADOS / "audit"` | Directory containing `*_DEBUG.csv` files |
| `SALIDA_TIPOS` | `RUTA_RESULTADOS / "tipos_definicion.csv"` | One row per TYPE definition |
| `SALIDA_COMPS` | `RUTA_RESULTADOS / "tipos_componentes.csv"` | One row per component field |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file — reads lines
  classified as `TYPE_DEFINITION`, `VAR_DECLARATION`, or `END_BLOCK_STMT`.
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`) — used to
  identify the host unit (MODULE, PROGRAM, etc.) that contains each TYPE.

---

## Outputs

### `<FORT_OUT>/tipos_definicion.csv`
One row per derived TYPE definition found.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Name of the host unit (MODULE, SUBROUTINE, etc.) containing the TYPE |
| `Tipo_Unidad` | Host unit type (e.g. `MODULE`) |
| `Linea_Inicio` | Line number of the `TYPE name` statement |
| `Linea_Fin` | Line number of the matching `END TYPE` statement |
| `Nombre_Tipo` | TYPE name (uppercase) |
| `N_Componentes` | Number of component fields declared inside the TYPE |

### `<FORT_OUT>/tipos_componentes.csv`
One row per component field of each derived TYPE.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Nombre_Tipo` | Parent TYPE name (uppercase) |
| `Linea` | Line number of the component declaration |
| `Posicion` | Component position within the TYPE (1-based) |
| `Nombre_Comp` | Component field name (uppercase) |
| `Tipo_Fortran` | Base type: `INTEGER`, `REAL`, `LOGICAL`, `CHARACTER`, etc. |
| `Kind_Param` | KIND or byte-size modifier, e.g. `*4`, `*8` |
| `Dimension` | Array dimension spec if the component is an array; empty if scalar |
| `Atributos` | Pipe-separated attribute list (e.g. `ALLOCATABLE`, `POINTER`) |

---

## State Machine

The script uses a per-file state machine to track TYPE bodies:

1. **`TYPE_DEFINITION`** — enter TYPE body: record type name and host unit via
   scope resolution.
2. **`VAR_DECLARATION`** (while inside TYPE body) — parse as component field.
3. **`END_BLOCK_STMT`** matching `END TYPE` — close the TYPE body and emit rows.

All other statement kinds are ignored while inside a TYPE body. Nested TYPE
definitions are not expected in Fortran and are not handled.

---

## Component Parsing

Component declarations follow the same F77/F90 hybrid rules as `simbolos.py`:

| Syntax | Style | Example |
| :--- | :--- | :--- |
| `TYPE [attrs] :: comp_list` | F90 | `REAL(KIND=8), DIMENSION(N) :: X` |
| `TYPE[*size] comp_list` | F77 | `LOGICAL*4 flag` |

---

## Notes

- `RE_TYPE_DEF` in `patterns_v2.py` detects both `TYPE :: name` (F90 with
  attributes) and `TYPE name` (F90/F95 without `::`), but excludes `TYPE(name)`
  (variable use) and `TYPE IS (...)` (SELECT TYPE construct).
- `perfilador.py` must be re-run after any fix to `RE_TYPE_DEF` in
  `patterns_v2.py`, since the audit CSVs are the source of truth for
  `TYPE_DEFINITION` line detection.
- This script requires `perfilador` (audit CSVs) and `inventario` to have run
  first. In the pipeline it is step 11, immediately after `simbolos`.
- `EQUIVALENCE` aliasing across TYPE instances is not analyzed here; it is
  reserved for a future `equivalencias.py` step.
