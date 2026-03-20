# common_blocks.py

## Purpose

Detects F77 COMMON block usage across the corpus. Reports which units
reference each block and quantifies the coupling risk those shared global
data areas introduce.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `RUTA_AUDIT` | `"audit/"` | Directory containing `*_DEBUG.csv` files |
| `SALIDA_USO` | `"common_uso.csv"` | Per-unit COMMON usage |
| `SALIDA_ACOPLAMIENTO` | `"common_acoplamiento.csv"` | Per-block coupling risk |
| `NOMBRE_BLANK` | `"(BLANK)"` | Label for unnamed (blank) COMMON |

---

## Inputs

- `audit/<filename>_DEBUG.csv` for each source file (reads `COMMON_STMT` lines)
- `reporte_inventario.csv` (via `cargar_inventario()`)

---

## Outputs

### `common_uso.csv`
One row per (unit, COMMON block) pair.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `Bloque` | COMMON block name, or `(BLANK)` for unnamed COMMON |
| `Apariciones` | Number of COMMON statements referencing this block in this unit |

### `common_acoplamiento.csv`
One row per COMMON block, sorted by `N_Unidades` descending.

| Column | Description |
| :--- | :--- |
| `Bloque` | COMMON block name |
| `N_Unidades` | Number of distinct units that reference this block |
| `N_Archivos` | Number of distinct source files involved |
| `Riesgo` | Coupling risk level (see below) |
| `Unidades` | Semicolon-separated list of unit names |
| `Archivos` | Semicolon-separated list of file names |

---

## Risk Levels

| Level | Condition |
| :--- | :--- |
| `BAJO` | 1 unit references the block |
| `MEDIO` | 2–4 units reference the block |
| `ALTO` | 5 or more units reference the block |

---

## COMMON Statement Parsing

The parser handles all standard Fortran COMMON syntax variants:

| Syntax | Result |
| :--- | :--- |
| `COMMON /A/ x, y` | Block `A` |
| `COMMON x, y` | Blank COMMON → `(BLANK)` |
| `COMMON //x` | Blank COMMON → `(BLANK)` |
| `COMMON /A/ x /B/ y` | Blocks `A` and `B` |
| `COMMON x /A/ y` | `(BLANK)` and `A` |

Multiple block names on a single line are deduplicated — the same block
appearing twice in one statement is counted once per statement.

---

## Notes

- If no COMMON statements are found in the corpus, both output files are
  written empty (headers only) to maintain pipeline consistency.
- COMMON blocks are a F77 construct. Corpora that use F90 modules for data
  sharing will produce empty outputs here, which is the expected result.
