# Architecture

## Overview

The toolkit is organized as a sequential pipeline of independent Python scripts,
orchestrated by `pipeline.py` (the `forti4d` CLI command). Each script reads one
or more CSV files produced by earlier steps and writes its own output files.
No script modifies another script's output.

Input files are read from the source directory configured via `FORT_SRC` (or
`--project`). Output files are written to `results/` by default, or to the
directory configured via `FORT_OUT` (or `--output`).

---

## Script Tiers

### Tier 1 — Support Libraries (not run directly)

| Script | Role |
| :--- | :--- |
| `reader_logical.py` | Core Fortran line reader. Handles F77 fixed-form and F90 free-form continuation, comments, and blank lines. Returns a list of `LogicalLine` objects. Used by `inventory.py`, `profiler.py`, and `sloc.py`. |
| `patterns_v1.py` | Regex patterns for program unit boundaries (`PROGRAM`, `MODULE`, `SUBROUTINE`, `FUNCTION`, `BLOCK DATA`, `END`). Used by `inventory.py`. |
| `patterns_v2.py` | Extended regex patterns for statement classification (control flow, I/O, declarations, legacy constructs, etc.). Used by `profiler.py`. |
| `kinds.py` | Enum of statement kinds (`StatementKind`). Referenced by `profiler.py` to classify and group statements. |

---

### Tier 2 — Original Pipeline

These scripts form the foundation. They must run in order.

```
inventory.py
    └─ dependencies.py
    └─ profiler.py
            └─ block_analysis.py  (batch, one file per source)
    └─ structure_analysis.py
    └─ cross_analysis.py
    └─ executive_summary.py
```

#### `inventory.py`
- **Reads:** Fortran source files in `CODE_PATH`
- **Writes:** `inventory_report.csv`
- **Role:** Foundation of the entire pipeline. Scans all source files, identifies every program unit (PROGRAM, MODULE, SUBROUTINE, FUNCTION, BLOCK DATA), records its type, parent unit, line range, and audit flags (legacy constructs, I/O statements).
- **All other scripts depend on this output.**

#### `dependencies.py`
- **Reads:** `inventory_report.csv` + Fortran source files
- **Writes:** `dep_00_ambiguities.csv`, `dep_01_master_data.csv`, `dep_02_unit_graph.csv`, `dep_03_impact_matrix.csv`, `dep_04_external_orphans.csv`, `dep_05_file_dependencies.csv`, `dep_06_include_files.csv`
- **Role:** Builds the call graph. Resolves CALL, USE, and function-call references between units. Computes Fan-In and Fan-Out per unit. Flags units defined in multiple files (ambiguities) and references with no known definition (orphans).

#### `profiler.py`
- **Reads:** `inventory_report.csv` + Fortran source files
- **Writes:** `report_density.csv` + `audit/<file>_DEBUG.csv` (one per source file)
- **Role:** Classifies every logical statement in every source file using `patterns_v2.py` and `kinds.py`. Computes statement density profiles per unit (% calculation, % control flow, % I/O, % legacy, % declarations). The `audit/` DEBUG files are the primary intermediate artifact consumed by the extended analysis tier.

#### `block_analysis.py`
- **Reads:** `audit/<file>_DEBUG.csv` files produced by `profiler.py`
- **Writes:** `blocks/<file>_blocks.txt` (one per source file)
- **Role:** Block topology analysis. For each source file, produces a hierarchical view of control-flow block nesting (IF/DO/SELECT depth) per unit. Run as a batch step by the pipeline.

#### `structure_analysis.py`
- **Reads:** `dep_03_impact_matrix.csv`, `inventory_report.csv`
- **Writes:** `report_structure_analysis.csv`
- **Role:** Classifies each source file into an architectural role based on its Fan-In/Fan-Out profile: `CRITICAL_NODE` (high Fan-In), `ORCHESTRATOR` (high Fan-Out), `ENTRY_POINT` (executable), `WORKER` (service routine), `ISLAND` (no connections), or `MIXED`.

#### `cross_analysis.py`
- **Reads:** `report_density.csv`, `dep_03_impact_matrix.csv` + optionally `report_reachability.csv`, `symbol_implicit.csv`, `equivalences.csv`
- **Writes:** `report_migration_strategy.csv`
- **Role:** Assigns a migration strategy to each unit by crossing density metrics with coupling data. Computes two composite indices — ICM (migration complexity) and IVC (calculation value) — and applies a rule engine to classify each unit as: `DIRECT_MIGRATION`, `STANDARD_MIGRATION`, `REPLACE_LIB`, `REFACTOR_CORE`, `REWRITE_ISOLATED`, `ANALYZE_UTILITY`, or `ELIMINATE`. When reachability data is present, confirmed `NOT_REACHABLE` units are forced to `ELIMINATE`. When E4 data is present, adds a penalty (max 7 points) to ICM for units without IMPLICIT NONE and/or with EQUIVALENCE aliasing.

#### `executive_summary.py`
- **Reads:** `inventory_report.csv`, `dep_03_impact_matrix.csv` + optionally `symbol_implicit.csv`, `equivalences.csv`, `common_usage.csv`, `symbol_variables.csv`
- **Writes:** `PROJECT_SUMMARY.md`, `file_statistics.csv`
- **Role:** Produces a high-level executive summary in Markdown. Reports global metrics (LOC, unit counts, type distribution), top monolithic files, legacy/I/O health indicators, and the most critical and most orchestrating units. When E4 data is present, adds a "Scope Health" section with IMPLICIT NONE coverage, EQUIVALENCE/COMMON exposure, scope-clean unit count, and top units by variable density.

---

### Tier 3 — Extended Analysis

These scripts add deeper metrics. They require Tier 2 outputs to be present,
especially the `audit/` directory produced by `profiler.py`.

```
complexity.py       ─┐
common_blocks.py    ─┤─ all read audit/*_DEBUG.csv + inventory_report.csv
reachability.py     ─┘─ reads dep_02_unit_graph.csv + inventory_report.csv
sloc.py             ─── reads source files + inventory_report.csv
clones.py           ─── reads source files + inventory_report.csv
        │
        └──► consolidate.py  ─── joins all reports → report_consolidated.csv
                    │
                    ├──► visual_graph.py   ─── reads dep_02 + report_consolidated.csv
                    │
                    ├──► prioritization.py ─── reads consolidated + clones + strategy
                    │
                    └──► html_report.py    ─── reads report_prioritization.csv
```

#### `complexity.py`
- **Reads:** `audit/*_DEBUG.csv`, `inventory_report.csv`
- **Writes:** `report_complexity.csv`
- **Role:** Computes McCabe cyclomatic complexity (CC) per unit by counting decision points (IF, ELSE IF, DO, non-default CASE, WHERE, FORALL) from the DEBUG files. Uses scope resolution via line ranges. CC scale: LOW (1–10), MEDIUM (11–20), HIGH (21–50), CRITICAL (>50).

#### `common_blocks.py`
- **Reads:** `audit/*_DEBUG.csv`, `inventory_report.csv`
- **Writes:** `common_usage.csv`, `common_coupling.csv`
- **Role:** Detects F77 COMMON block usage. Parses COMMON statements, resolves block names (including blank COMMON represented as `(BLANK)`), and reports which units share each block. Assigns coupling risk: LOW (1 unit), MEDIUM (2–4 units), HIGH (5+ units).

#### `reachability.py`
- **Reads:** `dep_02_unit_graph.csv`, `inventory_report.csv`
- **Writes:** `report_reachability.csv`
- **Role:** Dead code detection via BFS from all entry points (PROGRAM and IMPLICIT-MAIN units). Follows CALL, USE, and FUNC_CALL edges. Classifies each unit as `ENTRY_POINT`, `REACHABLE`, or `NOT_REACHABLE`. Resolves the `MAIN__<file>` node naming convention used by `dependencies.py` for IMPLICIT-MAIN units.

#### `sloc.py`
- **Reads:** Fortran source files + `inventory_report.csv`
- **Writes:** `report_sloc.csv`
- **Role:** Precise SLOC counting per unit. Uses `reader_logical.py` to classify each physical line as BLANK, COMMENT, CODE, or CONTINUATION. Computes LOC, physical SLOC (LOC minus blanks and comments), net SLOC (logical statements only), and comment density percentage.

#### `consolidate.py`
- **Reads:** `inventory_report.csv`, `report_sloc.csv`, `report_complexity.csv`, `dep_03_impact_matrix.csv`, `report_density.csv`, `report_reachability.csv`, `common_usage.csv`, `symbol_variables.csv`, `symbol_signatures.csv`, `symbol_implicit.csv`, `type_definitions.csv`, `equivalences.csv`, `audit/*_DEBUG.csv`
- **Writes:** `report_consolidated.csv`
- **Role:** Joins all per-unit reports into a single CSV (one row per unit). Adds the derived metric CC_SLOC, E4 symbol summary columns (N_Local_Vars, N_Params, N_Formal_Args, Implicit_None, N_Derived_Types, Has_Equiv, N_Equiv_Groups), and statement-level counts from the audit CSVs (N_Data_Stmts, N_Entry_Stmts). Must run after all other analysis scripts.

#### `clones.py`
- **Reads:** `inventory_report.csv`, Fortran source files
- **Writes:** `report_clones.csv`
- **Role:** Detects identical, similar, and diverged duplicate units across files. Compares units with the same name appearing in multiple files using normalized token sequences. Classifies each pair as `IDENTICAL`, `SIMILAR`, or `DIVERGED`.

#### `visual_graph.py`
- **Reads:** `dep_02_unit_graph.csv`, `report_consolidated.csv`
- **Writes:** `graph_full.dot`, `graph_simple.dot`, and/or `graph_<entry>.dot`
- **Role:** Generates Graphviz DOT files for call graph visualization. Supports full corpus view or per-entry-point filtered subgraphs. Nodes are colored by reachability status and shaped by unit type. Clusters source files. Resolves `MAIN__` node names to inventory names.
- **Flags:** `--list`, `--entry <name> [name…]`, `--use`

#### `prioritization.py`
- **Reads:** `report_consolidated.csv`, `report_clones.csv`, `report_migration_strategy.csv`
- **Writes:** `report_prioritization.csv`
- **Role:** Computes a composite risk/effort score (0–100) per unit across five signals: cyclomatic complexity (30%), Fan-In criticality (30%), legacy density (20%), clone state (15%), and E4 scope risk — no IMPLICIT NONE + EQUIVALENCE aliasing (5%). Ranks units into CRITICAL / HIGH / MEDIUM / LOW / DEAD_CODE tiers for migration planning.

#### `html_report.py`
- **Reads:** `report_prioritization.csv`
- **Writes:** `report.html`
- **Role:** Generates a self-contained HTML report with priority summary cards and a filterable/sortable unit table. No external dependencies — stdlib only, inline CSS and JavaScript.

---

### Tier 4 — E4 ScopeManager

These scripts extract the symbol-level microstructure of each unit (Axis Z of
the MI4D model). They all read `audit/*_DEBUG.csv` produced by `profiler.py`
and the inventory for scope resolution.

```
audit/*_DEBUG.csv + inventory_report.csv
        │
        ├──► symbols.py       → symbol_variables.csv
        │                        symbol_signatures.csv
        │                        symbol_implicit.csv
        │
        ├──► derived_types.py → type_definitions.csv
        │                        type_components.csv
        │
        └──► equivalences.py  → equivalences.csv
```

#### `symbols.py`
- **Reads:** `audit/*_DEBUG.csv`, `inventory_report.csv`
- **Writes:** `symbol_variables.csv`, `symbol_signatures.csv`, `symbol_implicit.csv`
- **Role:** Extracts variable declarations, PARAMETER constants, formal arguments of subroutines/functions, and IMPLICIT rules from each unit. Handles F77 and F90 syntax. Cross-references COMMON statements to populate the `In_Common` field post-processing.

#### `derived_types.py`
- **Reads:** `audit/*_DEBUG.csv`, `inventory_report.csv`
- **Writes:** `type_definitions.csv`, `type_components.csv`
- **Role:** Extracts derived TYPE definitions and their component fields using a per-file state machine. Identifies the host unit for each TYPE via scope resolution.

#### `equivalences.py`
- **Reads:** `audit/*_DEBUG.csv`, `inventory_report.csv`
- **Writes:** `equivalences.csv`
- **Role:** Detects EQUIVALENCE aliasing groups using a union-find algorithm. Resolves transitive aliasing across multiple EQUIVALENCE statements within the same unit. One row per variable per aliasing group.

---

## Data Flow Diagram

```
Fortran source files ──────────────────────────────────────────────┐
         │                                                          │
         ▼                                                          │
   inventory.py → inventory_report.csv ─────────────────────────┐  │
         │                                                       │  │
         ├──► dependencies.py → dep_00…dep_06_*.csv ────────┐   │  │
         │                           │                       │   │  │
         │                    dep_02_unit_graph.csv ─────────┼──► reachability.py
         │                    dep_03_impact_matrix.csv ──────┼──► structure_analysis.py
         │                                                   │    cross_analysis.py
         │                                                   │    executive_summary.py
         │                                                   │
         ├──► profiler.py → report_density.csv               │
         │              └──► audit/*_DEBUG.csv ──────────────┼──► complexity.py
         │                        │                          │    common_blocks.py
         │                        │                          │    symbols.py      ─┐
         │                        │                          │    derived_types.py ─┤→ E4 CSVs
         │                        │                          │    equivalences.py ─┘
         │                        └──► block_analysis.py     │
         │                             (blocks/*.txt)        │
         ├──► sloc.py → report_sloc.csv                      │
         │                                                   │
         └──► clones.py → report_clones.csv                  │
                                                             │
              [all reports above] ──────────────────────────┘
                        │
                        ▼
                 consolidate.py → report_consolidated.csv
                        │
                        ├──► visual_graph.py  → graph_*.dot
                        │
                        ├──► prioritization.py → report_prioritization.csv
                        │
                        └──► html_report.py  → report.html
```

---

## Key Design Decisions

**Scope resolution** — Every metric that must be attributed to a specific unit
(CC, SLOC, density, COMMON usage) uses the same approach: for each source line,
find all units whose `[Start_Line, End_Line]` range contains that line, then
assign to the innermost one (the one with the highest `Start_Line`).

**No external parser** — The toolkit deliberately avoids general-purpose Fortran
parsers. `reader_logical.py` handles continuation lines and comment detection
for both F77 fixed-form and F90 free-form. Statement classification is done with
calibrated regex patterns (`patterns_v1.py`, `patterns_v2.py`). This makes the
toolkit robust on hybrid real-world codebases where standard parsers fail.

**IMPLICIT-MAIN units** — Files that compile to an executable without an
explicit `PROGRAM` statement are identified as `IMPLICIT-MAIN` in the inventory.
`dependencies.py` represents them as `MAIN__<filename>` nodes in the call graph.
`reachability.py` and `visual_graph.py` resolve this convention back to the
inventory name for display.

**Pipeline orchestration** — The full 19-step pipeline is orchestrated by
`pipeline.py` (the `forti4d` CLI command). Individual scripts can also be run
independently if their required input files are already present, with the
exception of the `audit/` dependency between `profiler.py` and the extended
analysis scripts.
