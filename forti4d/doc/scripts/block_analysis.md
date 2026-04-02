# block_analysis.py

## Purpose

Block topology analysis. Takes one `audit/*_DEBUG.csv` file at a time and
prints a hierarchical tree of control-flow block nesting (IF/DO/SELECT/WHERE/FORALL
depth) per unit in that file.

When invoked via the pipeline, output is written automatically to
`<FORT_OUT>/blocks/`. When invoked manually, it prints to stdout.

---

## Usage

```bash
# Analyze one file (manual)
python -m forti4d.analyzers.block_analysis results/audit/solver_main.f90_DEBUG.csv

# Save output manually
python -m forti4d.analyzers.block_analysis results/audit/solver_main.f90_DEBUG.csv \
    > results/blocks/solver_main.f90_blocks.txt

# Run via pipeline (batch — processes all files automatically)
forti4d --only blocks
```

---

## Inputs

- A single `<FORT_OUT>/audit/<filename>_DEBUG.csv`
- `<FORT_OUT>/inventory_report.csv` (loaded via `load_inventory()` to get unit line ranges)

---

## Output

### Via pipeline: `<FORT_OUT>/blocks/<filename>_blocks.txt`
One file per source file.

### Manual (stdout)
A text tree showing block topology per unit. Example:

```
STRUCTURAL ANALYSIS: solver_main.f90
================================================================================

>> UNIT: solver_main (SUBROUTINE)
    1-   45 |  0 |                              IF_CONSTRUCT        | IF_CONSTRUCT:12, ...
   45-  120 |  1 | |_                          DO_CONSTRUCT        | DO_CONSTRUCT:8, ...
  120-  145 |  2 | | |_                        SELECT_CONSTRUCT    | CASE_STMT:5, ...
```

Columns: `start_line - end_line | depth | tree_indent type | top_3_kinds`

---

## Constructs Tracked

**Block openers:** `IF_CONSTRUCT`, `DO_CONSTRUCT`, `DO_WHILE_CONSTRUCT`,
`SELECT_CONSTRUCT`, `SELECT_TYPE_CONSTRUCT`, `BLOCK_CONSTRUCT`,
`INTERFACE_BLOCK`, `TYPE_DEFINITION`, `ASSOCIATE_CONSTRUCT`,
`FORALL_CONSTRUCT`, `WHERE_CONSTRUCT`, `CRITICAL_CONSTRUCT`

**Block closers:** `END_IF_STMT`, `END_DO_STMT`, `END_SELECT_STMT`,
`END_BLOCK_STMT`, `END_ASSOCIATE_STMT`, `END_FORALL_STMT`, `END_WHERE_STMT`,
`END_CRITICAL_STMT`, `END_INTERFACE_STMT`, `END_TYPE_STMT`,
`END_FUNCTION_STMT`, `END_SUBROUTINE_STMT`, `END_MODULE_STMT`,
`END_PROGRAM_STMT`

---

## Notes

- Requires `profiler.py` to have been run first (reads from `<FORT_OUT>/audit/`).
- Manual invocation via `python -m forti4d.analyzers.block_analysis` is a
  temporary workaround. A dedicated CLI subcommand for scripts with file
  arguments is planned.
