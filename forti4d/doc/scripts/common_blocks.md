# common_blocks.py

## Purpose

Detects F77 COMMON block usage across the corpus. Reports which units
reference each block and quantifies the coupling risk those shared global
data areas introduce.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory containing `*_DEBUG.csv` files |
| `USAGE_OUTPUT` | `RESULTS_PATH / "common_usage.csv"` | Per-unit COMMON usage |
| `COUPLING_OUTPUT` | `RESULTS_PATH / "common_coupling.csv"` | Per-block coupling risk |
| `BLANK_NAME` | `"(BLANK)"` | Label for unnamed (blank) COMMON |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file (reads `COMMON_STMT` lines)
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`)

---

## Outputs

### `<FORT_OUT>/common_usage.csv`
One row per (unit, COMMON block) pair.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `Block` | COMMON block name, or `(BLANK)` for unnamed COMMON |
| `Occurrences` | Number of COMMON statements referencing this block in this unit |

### `<FORT_OUT>/common_coupling.csv`
One row per COMMON block, sorted by `N_Units` descending.

| Column | Description |
| :--- | :--- |
| `Block` | COMMON block name |
| `N_Units` | Number of distinct units that reference this block |
| `N_Files` | Number of distinct source files involved |
| `Risk` | Coupling risk level (see below) |
| `Units` | Semicolon-separated list of unit names |
| `Files` | Semicolon-separated list of file names |

---

## Risk Levels

| Level | Condition |
| :--- | :--- |
| `LOW` | 1 unit references the block |
| `MEDIUM` | 2–4 units reference the block |
| `HIGH` | 5 or more units reference the block |

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
