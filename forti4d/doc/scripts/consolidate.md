# consolidate.py

## Purpose

Joins all per-unit reports into a single CSV with one row per unit and
34 columns. Must run after all other analysis scripts. Also adds the
derived metric `CC_SLOC`.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTORY_FILE` | `RESULTS_PATH / "inventory_report.csv"` | Base — defines the row set |
| `SLOC_FILE` | `RESULTS_PATH / "report_sloc.csv"` | Size and comment density |
| `COMPLEXITY_FILE` | `RESULTS_PATH / "report_complexity.csv"` | McCabe CC |
| `IMPACT_FILE` | `RESULTS_PATH / "dep_03_impact_matrix.csv"` | Fan-In / Fan-Out |
| `DENSITY_FILE` | `RESULTS_PATH / "report_density.csv"` | Statement density profiles |
| `REACHABILITY_FILE` | `RESULTS_PATH / "report_reachability.csv"` | Reachability status |
| `COMMON_USAGE_FILE` | `RESULTS_PATH / "common_usage.csv"` | COMMON block usage |
| `SYMBOLS_VARS_FILE` | `RESULTS_PATH / "symbol_variables.csv"` | Variable and constant declarations |
| `SYMBOLS_SIGS_FILE` | `RESULTS_PATH / "symbol_signatures.csv"` | Formal arguments per unit |
| `SYMBOLS_IMPL_FILE` | `RESULTS_PATH / "symbol_implicit.csv"` | IMPLICIT rules per unit |
| `TYPES_DEF_FILE` | `RESULTS_PATH / "type_definitions.csv"` | Derived TYPE definitions |
| `EQUIV_FILE` | `RESULTS_PATH / "equivalences.csv"` | EQUIVALENCE aliasing groups |
| `AUDIT_PATH` | `RESULTS_PATH / "audit"` | Directory of `*_DEBUG.csv` files (for DATA/ENTRY counts) |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_consolidated.csv"` | Output |

All sources except `INVENTORY_FILE` are optional — missing files produce empty
values for their columns without stopping the script.

---

## Inputs

All reports listed in the configuration table above.

---

## Output: `<FORT_OUT>/report_consolidated.csv`

One row per program unit, sorted alphabetically by `File` then `Unit`.

| Column | Source | Description |
| :--- | :--- | :--- |
| `File` | inventory | Source file name |
| `Unit` | inventory | Unit name |
| `Type` | inventory | Unit type |
| `Parent` | inventory | Parent unit or `GLOBAL` |
| `LOC` | sloc | Physical line count |
| `SLOC_physical` | sloc | LOC minus blanks and comments |
| `SLOC_net` | sloc | Logical statements only |
| `N_Comments` | sloc | Comment line count |
| `N_Continuation` | sloc | Continuation line count |
| `Pct_Comment` | sloc | Comment density % |
| `CC` | complexity | McCabe cyclomatic complexity |
| `CC_Level` | complexity | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |
| `CC_SLOC` | derived | `CC / SLOC_net` — complexity per logical statement |
| `Fan_In` | impact | Number of callers |
| `Fan_Out` | impact | Number of callees |
| `Pct_Calc` | density | % calculation statements |
| `Pct_Control` | density | % control-flow statements |
| `Pct_IO` | density | % I/O statements |
| `Pct_Legacy` | density | % legacy statements |
| `N_Common_Blocks` | common_usage | Number of distinct COMMON blocks used |
| `Common_Blocks` | common_usage | Semicolon-separated block names |
| `Status` | reachability | `ENTRY_POINT` / `REACHABLE` / `UNREACHABLE` |
| `Via_Entry_Points` | reachability | Entry points that reach this unit |
| `N_Local_Vars` | symbol_variables | Count of declared variables (non-PARAMETER) |
| `N_Params` | symbol_variables | Count of PARAMETER constants |
| `N_Formal_Args` | symbol_signatures | Count of formal arguments (0 for non-callable units) |
| `Implicit_None` | symbol_implicit | `YES` if unit has `IMPLICIT NONE`; `NO` if has rules; empty if no IMPLICIT statement |
| `N_Derived_Types` | type_definitions | Count of derived TYPE definitions hosted in this unit |
| `Has_Equiv` | equivalences | `YES` if the unit has any EQUIVALENCE aliasing groups, `NO` otherwise |
| `N_Equiv_Groups` | equivalences | Number of distinct aliasing groups in the unit |
| `N_Data_Stmts` | audit CSVs | Count of DATA statements in the unit |
| `N_Entry_Stmts` | audit CSVs | Count of ENTRY statements in the unit |
| `Legacy_Flags` | inventory | Legacy constructs detected (from inventory) |
| `IO_Flags` | inventory | I/O statements detected (from inventory) |

---

## Notes

- The join key is `(File, Unit)`. The inventory defines which rows exist;
  all other sources are left-joined against it.
- `CC_SLOC = 0` when `SLOC_net = 0` (avoids division by zero).
- `COMMON_USAGE` may contain multiple rows per unit (one per block). These are
  aggregated: `N_Common_Blocks` = count of distinct blocks, `Common_Blocks`
  = sorted semicolon-separated names.
- Symbol sources (`symbol_variables`, `symbol_signatures`, `symbol_implicit`,
  `type_definitions`, `equivalences`) may contain multiple rows per unit and
  are aggregated into summary counts. These sources require `symbols`,
  `derived_types`, and `equivalences` to have run first.
- `N_Data_Stmts` and `N_Entry_Stmts` are computed by scanning
  `audit/*_DEBUG.csv` directly using scope resolution (innermost unit
  whose `[Start_Line, End_Line]` range contains the statement line).
  The `audit/` directory must be present (produced by `profiler.py`).
  If missing, both columns default to 0.
- `report_clones.csv` (produced by `clones.py`) is not currently joined here.
  Clone state per unit is read directly by `prioritization.py`. A future
  integration could add `Clone_Status` and `N_Copies` columns to this report.
