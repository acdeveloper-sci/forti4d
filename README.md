# Fortran Static Analysis Toolkit

A Python toolkit for static analysis of Fortran source code.
Designed to work with real-world hybrid Fortran corpora (mixed F77/F90/F95),
where general-purpose parsers typically fail.

---

## Fortran Standard Support

| Standard | Support |
| :--- | :--- |
| FORTRAN 77 (F77) | Full — fixed-form, COMMON, EQUIVALENCE, IMPLICIT, BLOCK DATA |
| Fortran 90 (F90) | Full — free-form, modules, USE, derived types, INTERFACE blocks |
| Fortran 95 (F95) | Full — FORALL, WHERE, PURE/ELEMENTAL attributes |
| Fortran 2003+ | Not supported (see Future Work) |

---

## Installation

```bash
pip install forti4d
```

---

## Quick Start

```bash
forti4d                                        # run full 19-step pipeline
forti4d --project ../myproject --output out/   # specify source and output dirs
forti4d --list                                 # show all pipeline steps
forti4d --from symbols                         # resume from a specific step
forti4d --quiet                                # suppress step output
```

See `doc/scripts/pipeline.md` for all flags and options.

---

## Requirements

- Python 3.8+
- [Graphviz](https://graphviz.org/) — only required for rendering `.dot` files
  produced by `visual_graph.py`
- No third-party Python packages — standard library only

---

## Pipeline

The 19 steps in dependency order:

```
inventory.py          →  inventory_report.csv
dependencies.py       →  dep_00_ambiguities.csv
                         dep_01_master_data.csv
                         dep_02_unit_graph.csv
                         dep_03_impact_matrix.csv
                         dep_04_external_orphans.csv
                         dep_05_file_dependencies.csv
                         dep_06_include_files.csv
profiler.py           →  report_density.csv
                         audit/<file>_DEBUG.csv  (one per source file)
block_analysis.py     →  blocks/<file>_blocks.txt  (one per source file)
structure_analysis.py →  report_structure_analysis.csv
cross_analysis.py     →  report_migration_strategy.csv
executive_summary.py  →  PROJECT_SUMMARY.md
                         file_statistics.csv
complexity.py         →  report_complexity.csv
common_blocks.py      →  common_usage.csv
                         common_coupling.csv
─── E4 ScopeManager ──────────────────────────────────────────────────────────
symbols.py            →  symbol_variables.csv
                         symbol_signatures.csv
                         symbol_implicit.csv
derived_types.py      →  type_definitions.csv
                         type_components.csv
equivalences.py       →  equivalences.csv
─── ──────────────────────────────────────────────────────────────────────────
reachability.py       →  report_reachability.csv
sloc.py               →  report_sloc.csv
clones.py             →  report_clones.csv
consolidate.py        →  report_consolidated.csv
visual_graph.py       →  graph_*.dot
prioritization.py     →  report_prioritization.csv
html_report.py        →  report.html
```

> `profiler.py` must run before `complexity.py`, `common_blocks.py`,
> `symbols.py`, `derived_types.py`, and `equivalences.py` — all read
> the `audit/*_DEBUG.csv` files it produces.
>
> `consolidate.py` must run after all analysis scripts — it joins all reports.
>
> `prioritization.py` must run after `consolidate.py`.

---

## Output Files

| File | Produced by | Description |
| :--- | :--- | :--- |
| `inventory_report.csv` | `inventory.py` | All program units with type, line range, and audit flags |
| `dep_00_ambiguities.csv` | `dependencies.py` | Units defined in more than one source file |
| `dep_01_master_data.csv` | `dependencies.py` | Raw call/use relationships |
| `dep_02_unit_graph.csv` | `dependencies.py` | Resolved call graph (CALL, USE, FUNC_CALL edges) |
| `dep_03_impact_matrix.csv` | `dependencies.py` | Fan-In and Fan-Out per unit |
| `dep_04_external_orphans.csv` | `dependencies.py` | External references with no known definition in the corpus |
| `dep_05_file_dependencies.csv` | `dependencies.py` | File-level dependency summary |
| `dep_06_include_files.csv` | `dependencies.py` | INCLUDE file references with existence status |
| `report_density.csv` | `profiler.py` | Statement density profile per unit (% calculation, control, I/O, legacy) |
| `audit/<file>_DEBUG.csv` | `profiler.py` | Per-line statement classification for each source file |
| `blocks/<file>_blocks.txt` | `block_analysis.py` | Block topology per source file |
| `report_structure_analysis.csv` | `structure_analysis.py` | Structural categories (islands, hubs, entry points, etc.) |
| `report_migration_strategy.csv` | `cross_analysis.py` | Migration strategy per unit |
| `PROJECT_SUMMARY.md` | `executive_summary.py` | Executive summary in Markdown |
| `file_statistics.csv` | `executive_summary.py` | Per-file summary statistics |
| `report_complexity.csv` | `complexity.py` | McCabe cyclomatic complexity per unit |
| `common_usage.csv` | `common_blocks.py` | COMMON block usage per unit |
| `common_coupling.csv` | `common_blocks.py` | COMMON block coupling risk |
| `symbol_variables.csv` | `symbols.py` | Variable and PARAMETER constant declarations per unit |
| `symbol_signatures.csv` | `symbols.py` | Formal arguments per subroutine/function |
| `symbol_implicit.csv` | `symbols.py` | IMPLICIT rules per unit |
| `type_definitions.csv` | `derived_types.py` | Derived TYPE definitions with host unit and component count |
| `type_components.csv` | `derived_types.py` | Component fields of each derived TYPE |
| `equivalences.csv` | `equivalences.py` | EQUIVALENCE aliasing groups (union-find) |
| `report_reachability.csv` | `reachability.py` | Reachability from entry points (dead code detection) |
| `report_sloc.csv` | `sloc.py` | Precise SLOC count per unit (LOC, blanks, comments, continuations) |
| `report_clones.csv` | `clones.py` | Identical/similar/diverged duplicate unit pairs |
| `report_consolidated.csv` | `consolidate.py` | All metrics joined — one row per unit |
| `graph_*.dot` | `visual_graph.py` | Graphviz call graph (full, simplified, or per entry point) |
| `report_prioritization.csv` | `prioritization.py` | Units ranked by composite migration risk score |
| `report.html` | `html_report.py` | Self-contained HTML report — filterable and sortable unit table |

---

## Support Scripts

These are not run directly but are imported by the pipeline:

| File | Role |
| :--- | :--- |
| `config.py` | Centralized path configuration — reads `FORT_SRC` / `FORT_OUT` env vars |
| `reader_logical.py` | Fortran logical line reader — handles F77 fixed-form and F90 free-form continuation |
| `patterns_v1.py` | Regex patterns for unit boundaries (used by `inventory.py`) |
| `patterns_v2.py` | Extended regex patterns for statement classification (used by `profiler.py`) |
| `kinds.py` | Enum of statement kinds |

---

## Documentation

Detailed documentation for each script is in `doc/scripts/`. Architecture
overview and design decisions are in `doc/architecture.md`.

For development setup and contribution guidelines, see `CONTRIBUTING.md`.

---

## Design Notes

- **No external parser required.** The toolkit uses a custom logical-line
  reader (`reader_logical.py`) and regex patterns calibrated for hybrid
  Fortran code. This is intentional — general-purpose Fortran parsers
  (fparser, OFP) are unreliable on real-world legacy codebases.

- **Scope resolution** is based on the line ranges (`Start_Line`, `End_Line`)
  recorded in the inventory. Every metric is attributed to the innermost
  program unit containing the statement's line number.

- **Entry points** are units with type `PROGRAM` or `IMPLICIT-MAIN`
  (files that compile to an executable without an explicit `PROGRAM`
  statement). The corpus may contain several — one per executable.

- **E4 ScopeManager** scripts (`symbols.py`, `derived_types.py`,
  `equivalences.py`) populate the symbol-level layer of the analysis:
  what is declared inside each unit, not just that the unit exists.

---

## Known Limitations

- **Fortran 2003+ not supported.** OOP features (`CLASS`, `TYPE EXTENDS`,
  procedure pointers, `BIND(C)`) are not detected or analyzed.
- **Preprocessor directives** (`#ifdef`, `#include` via cpp) are not
  expanded — only native Fortran `INCLUDE` statements are tracked.
- **INCLUDE files** are detected and cross-referenced but not recursively
  analyzed as independent units.
- **Assumed character lengths** (`CHARACTER*(*)`) may not be fully captured
  in symbol signatures.
- **ENTRY statements** are flagged in the audit but not modeled as
  independent callable units in the inventory.

---

## Future Work

- **Fortran 2003:** CLASS hierarchy, TYPE EXTENDS, BIND(C), procedure
  pointers, deferred-length strings.
- **Fortran 2008:** Submodules, BLOCK construct, DO CONCURRENT,
  CRITICAL/SYNC primitives.
- **Fortran 2018:** Teams, events, collective subroutines (Coarray Fortran).
- **Deeper INCLUDE analysis:** Recursive parsing of included files as
  first-class units.
- **PyPI packaging** after v1.0 GitHub release.

---

## License

MIT — see `LICENSE`.
