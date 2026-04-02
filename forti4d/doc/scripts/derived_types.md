# derived_types.py

## Purpose

Extracts derived TYPE definitions and their component fields from the audit
CSVs produced by `profiler.py`. Populates the Axis Z (scope) layer of the
MI4D model at the type-structure level — the information needed to understand
the internal layout of user-defined data types, not just that they are used.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory containing `*_DEBUG.csv` files |
| `OUTPUT_TYPES` | `RESULTS_PATH / "type_definitions.csv"` | One row per TYPE definition |
| `OUTPUT_COMPONENTS` | `RESULTS_PATH / "type_components.csv"` | One row per component field |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file — reads lines
  classified as `TYPE_DEFINITION`, `VAR_DECLARATION`, or `END_BLOCK_STMT`.
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`) — used to
  identify the host unit (MODULE, PROGRAM, etc.) that contains each TYPE.

---

## Outputs

### `<FORT_OUT>/type_definitions.csv`
One row per derived TYPE definition found.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Name of the host unit (MODULE, SUBROUTINE, etc.) containing the TYPE |
| `Unit_Type` | Host unit type (e.g. `MODULE`) |
| `Start_Line` | Line number of the `TYPE name` statement |
| `End_Line` | Line number of the matching `END TYPE` statement |
| `Type_Name` | TYPE name (uppercase) |
| `N_Components` | Number of component fields declared inside the TYPE |

### `<FORT_OUT>/type_components.csv`
One row per component field of each derived TYPE.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Type_Name` | Parent TYPE name (uppercase) |
| `Line` | Line number of the component declaration |
| `Position` | Component position within the TYPE (1-based) |
| `Comp_Name` | Component field name (uppercase) |
| `Fortran_Type` | Base type: `INTEGER`, `REAL`, `LOGICAL`, `CHARACTER`, etc. |
| `Kind_Param` | KIND or byte-size modifier, e.g. `*4`, `*8` |
| `Dimension` | Array dimension spec if the component is an array; empty if scalar |
| `Attributes` | Pipe-separated attribute list (e.g. `ALLOCATABLE`, `POINTER`) |

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

Component declarations follow the same F77/F90 hybrid rules as `symbols.py`:

| Syntax | Style | Example |
| :--- | :--- | :--- |
| `TYPE [attrs] :: comp_list` | F90 | `REAL(KIND=8), DIMENSION(N) :: X` |
| `TYPE[*size] comp_list` | F77 | `LOGICAL*4 flag` |

---

## Notes

- `RE_TYPE_DEF` in `patterns_v2.py` detects both `TYPE :: name` (F90 with
  attributes) and `TYPE name` (F90/F95 without `::`), but excludes `TYPE(name)`
  (variable use) and `TYPE IS (...)` (SELECT TYPE construct).
- `profiler.py` must be re-run after any fix to `RE_TYPE_DEF` in
  `patterns_v2.py`, since the audit CSVs are the source of truth for
  `TYPE_DEFINITION` line detection.
- This script requires `profiler.py` (audit CSVs) and `inventory.py` to have
  run first. In the pipeline it is step 11, immediately after `symbols`.
- `EQUIVALENCE` aliasing across TYPE instances is not analyzed here; it is
  handled by `equivalences.py` (step 12).
