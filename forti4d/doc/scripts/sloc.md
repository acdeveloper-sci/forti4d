# sloc.py

## Purpose

Precise SLOC (Source Lines of Code) counting per program unit. Classifies
every physical line as blank, comment, code, or continuation, then aggregates
counts per unit using scope resolution.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CODE_PATH` | `FORT_SRC` env var → `tests/fixtures/` | Path to the Fortran source directory |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_sloc.csv"` | Output file |

---

## Inputs

- Fortran source files in `CODE_PATH`
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`)

---

## Output: `<FORT_OUT>/report_sloc.csv`

One row per program unit, sorted by `SLOC_net` descending.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `LOC` | Total physical lines in the unit's line range |
| `N_Blank` | Blank physical lines |
| `N_Comments` | Comment-only physical lines |
| `N_Continuation` | Continuation lines (2nd, 3rd… physical line of a multi-line statement) |
| `SLOC_physical` | `LOC - N_Blank - N_Comments` (lines with actual code, including continuations) |
| `SLOC_net` | `SLOC_physical - N_Continuation` (logical statements only) |
| `Pct_Comment` | `N_Comments / LOC × 100` |

---

## Line Classification

Uses `reader_logical.py` to obtain `LogicalLine` objects, then works backwards
from the `raw_lines` field of each logical line:

| Category | Condition |
| :--- | :--- |
| `COMMENT` | `LogicalLine.is_comment = True` |
| `BLANK` | Not a comment, and `LogicalLine.text` is empty/whitespace |
| `CODE` | First physical line of a non-comment, non-blank logical line |
| `CONTINUATION` | 2nd, 3rd, … physical line of a multi-line statement |

---

## Derived Metrics

**SLOC_net** equals the number of logical statements in the unit. This is
the most accurate size measure for comparing units, since it is independent
of coding style (how many continuation lines are used per statement).

**Pct_Comment** measures documentation density. Values below 5% on units
with more than 50 logical statements indicate poorly documented code.

**CC_SLOC** (in `report_consolidated.csv`) = `CC / SLOC_net`. Measures
cyclomatic complexity density — how many decision points exist per logical
statement. More useful than raw CC for comparing units of different sizes.
