# clones.py

## Purpose

Detects whether same-named units across multiple files are identical copies,
similar variants, or fully diverged independent implementations.

Reads the duplicate-unit list from `dep_00_ambiguities.csv`, extracts and
normalizes the source of each unit instance, and performs pairwise comparison
using `difflib.SequenceMatcher` (Python standard library).

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AMBIGUITIES_FILE` | `RESULTS_PATH / "dep_00_ambiguities.csv"` | Input: duplicate unit list |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_clones.csv"` | Output |
| `SIMILARITY_THRESHOLD` | `0.80` | Similarity ratio threshold for `SIMILAR` vs `DIVERGED` |

---

## Inputs

- `<FORT_OUT>/dep_00_ambiguities.csv` (from `dependencies.py`)
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`)
- Fortran source files in `CODE_PATH`

---

## Output: `<FORT_OUT>/report_clones.csv`

One row per pair of same-named units. Groups with N copies produce N×(N-1)/2
rows (e.g. 3 copies → 3 pairs).

| Column | Description |
| :--- | :--- |
| `Unit` | Unit name |
| `Type` | Unit type |
| `File_A` | First file |
| `File_B` | Second file |
| `SLOC_A` | Normalized line count of unit in File_A |
| `SLOC_B` | Normalized line count of unit in File_B |
| `Similarity_Pct` | Similarity percentage (0–100) |
| `Status` | `IDENTICAL`, `SIMILAR`, or `DIVERGED` |

Rows are sorted: `DIVERGED` first, then `SIMILAR`, then `IDENTICAL`.

---

## Classification

| Status | Condition |
| :--- | :--- |
| `IDENTICAL` | Similarity ratio = 1.00 (byte-for-byte identical after normalization) |
| `SIMILAR` | Ratio ≥ `SIMILARITY_THRESHOLD` (default 0.80) |
| `DIVERGED` | Ratio < `SIMILARITY_THRESHOLD` |

> **Note:** The `SIMILARITY_THRESHOLD` of 0.80 is a project-defined heuristic.
> It was calibrated against real Fortran legacy corpora where units with ≥ 80%
> token similarity were consistently found to be maintained copies of the same
> original. This threshold is a candidate for a future configuration parameter.

---

## Normalization

Before comparison, each unit's source is normalized:

1. Logical lines outside `[Start_Line, End_Line]` are excluded.
2. Comment lines and blank lines are removed.
3. Each remaining line is uppercased and whitespace-collapsed to a single space.

This makes the comparison insensitive to formatting differences, comment
additions, and case conventions while preserving structural differences.

---

## Notes

- Requires `dependencies.py` and `inventory.py` to have been run first.
- If `dep_00_ambiguities.csv` is empty (no duplicate names in the corpus),
  `report_clones.csv` is written with headers only.
- `report_clones.csv` is consumed by `prioritization.py` to compute the clone
  penalty component of the risk score.
