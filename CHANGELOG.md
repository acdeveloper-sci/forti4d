# Changelog

All notable changes to forti4d are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/) from v0.7.0 onward.

---

## [Unreleased]

### Added
- **In-process library API** (Bloque 1): `import forti4d; forti4d.run_pipeline(...)`
  runs the full pipeline without subprocess — no more shelling out to
  `python -m forti4d.pipeline`. All 19 analyzers now follow a consistent
  `analyze_xxx()` / `write_xxx()` / `main()` contract, returning results in
  memory in addition to (never instead of) writing their CSV/report files.
  CLI behavior, flags, and output files are unchanged.
- **Opt-in per-file parallelism** (Bloque 2): `--workers N` / `FORT_WORKERS`
  parallelizes the three heaviest, fully-independent-per-file steps —
  `inventory`, `profiler`, `blocks` — via `ProcessPoolExecutor`. Default is
  `workers=1` (sequential); behavior is unchanged unless explicitly requested.
  `forti4d/lib/parallel.py::pmap()` guarantees sequential/parallel output
  parity by construction — both modes run the exact same code path.
- **Real logging via loguru** (Bloque 3): all internal `print()` diagnostics
  across the 19 analyzers replaced with `logger.debug/info/success/warning/
  error()` calls. Every run now writes a full-detail log to
  `<results_dir>/forti4d.log` (always DEBUG+, regardless of `--quiet`); new
  `--log-file PATH` and `--no-log-file` CLI flags override or disable it.
  Library callers (`forti4d.run_pipeline()`) stay silent by default — call
  the new `forti4d.configure_logging()` to opt in to console/file output.
  `loguru` is forti4d's first third-party dependency.

### Changed
- **`--quiet` redefined**: now a console log-level filter (WARNING+ instead
  of INFO+) rather than an all-or-nothing toggle. Previously a successful
  `--quiet` run discarded all internal diagnostic output with no trace
  anywhere; now it's always captured in `forti4d.log`.
- `run_pipeline()`'s `on_step_end` callback signature changed from
  `(name, success, elapsed, error, output)` to `(name, success, elapsed,
  error)` — the `output` param (captured stdout) is gone now that step
  output goes through loguru instead of `redirect_stdout`. `run_pipeline()`
  also drops its `quiet=` parameter (superseded by `configure_logging()`).
  Both breaks are on this unpublished feature branch — no external consumer
  depends on either signature yet.

### Fixed
- `cross_analysis.py::to_float()`: crashed on native `int`/`float` values for
  `Fan_In`/`Fan_Out` when fed in-memory (non-CSV-string) data from the new
  library API — added an `isinstance(val, str)` guard before `.strip()`.
- `visual_graph.py`: treated `0` (native int, from in-memory data) as falsy
  but `"0"` (CSV string) as truthy, silently dropping the `Fi=0` label for
  units with zero Fan-In — changed to explicit `!= ""` comparisons.

### Documentation
- `README.md`: Requirements section now lists `loguru` instead of claiming
  stdlib-only; Quick Start documents the new `--quiet` semantics and
  `--no-log-file`.

### Tests
- `tests/test_output_manifest.py`, `tests/test_lib_pipeline.py`: new —
  byte-for-byte regression gate and library-vs-CLI parity check.
- `tests/test_parallel_helper.py`, `tests/test_parallel_parity.py`: new —
  `pmap()` order/parity guarantees and workers=1 vs workers=2 output parity,
  scoped and full-pipeline.
- `tests/test_logging_setup.py`, `tests/test_logging_behavior.py`: new —
  raw loguru API assumptions, `configure_logging()` behavior, and CLI/library
  end-to-end logging behavior via subprocess.

---

## [0.7.4] — 2026-07-31

### Fixed
- `dependencies.py`: always write all six `dep_*` output files (`dep_01` through
  `dep_06`) even when the corpus has no cross-file dependencies — previously the
  files were omitted for pure library/module corpora, causing downstream failures
  in `structure_analysis`, `reachability`, and `clones`; also moves
  `dep_06_include_files.csv` out of the incorrectly nested `file_deps_map` block

### Documentation
- `doc/scripts/dependencies.md`: correct constant names in Configuration table
  (`OUT_*` → `*_OUT`); add "Always written" note to all seven `dep_*` outputs

### Tests
- `tests/fixtures_lib_only/` + `tests/test_empty_outputs.py`: mini-corpus of two
  module-only `.f90` files and three tests verifying that `dep_00_ambiguities.csv`,
  `report_clones.csv`, and `report_reachability.csv` are written empty (headers
  only) for a pure-library corpus — exercises the code paths fixed in v0.7.2,
  v0.7.3, and v0.7.4

---

## [0.7.3] — 2026-07-31

### Fixed
- `reachability.py`: always write `report_reachability.csv` (headers only if
  no entry points exist) — previously the file was omitted for pure library or
  module-only corpora that contain no `PROGRAM` or `IMPLICIT-MAIN` units

### Documentation
- `doc/scripts/reachability.md`: note that the output file is always written
  and that downstream consumers (`consolidate.py`, `cross_analysis.py`) handle
  the empty-file case gracefully

---

## [0.7.2] — 2026-07-31

### Fixed
- `dependencies.py`: always write `dep_00_ambiguities.csv` (headers only if no
  duplicates found) — previously the file was omitted when the corpus had no
  units with the same name in multiple files, causing `clones.py` to treat a
  valid zero-ambiguity run as a missing-file error
- `clones.py`: treat absent `dep_00_ambiguities.csv` as zero ambiguities instead
  of aborting with an ERROR message; create `report_clones.csv` empty in that
  case; fix typo `_wrtite_empty_csv` → `_write_empty_csv`

### Documentation
- `doc/scripts/dependencies.md`: note that `dep_00_ambiguities.csv` is always
  written, even when empty
- `doc/scripts/clones.md`: clarify that absent or empty `dep_00_ambiguities.csv`
  is a valid outcome; note that `prioritization.py` handles the empty case

---

## [0.7.1] — 2026-07-21

### Fixed
- `sloc.py`: replaced `max()` with `+=` when accumulating per-file LOC in the
  console summary — `max()` returned only the largest unit per file, causing
  Total LOC to appear smaller than Physical SLOC (arithmetically impossible)
- `executive_summary.py`: group files by `Relative_Path` instead of `File`
  (basename) — basename collisions across subdirectories caused incorrect file
  counts and merged LOC for files sharing the same name in different directories
- `pipeline.py`: validate `FORT_SRC` directory before executing steps —
  provides a clear error message when the source path is missing or invalid
- `inventory.py` + 9 analyzers (`profiler`, `sloc`, `complexity`, `symbols`,
  `derived_types`, `equivalences`, `common_blocks`, `consolidate`,
  `dependencies`): add `Relative_Path` column to inventory and thread it
  through all file-access and debug-CSV naming — fixes "file not found" errors
  for source files located in subdirectories
- `reader_logical.py`: replace extension-only format detection with a
  content-based heuristic (`detect_fortran_format`) — correctly handles HPC
  code that uses `.F` extension but is written in free-form F90+ syntax

### Documentation
- `README.md`, `doc/mi4d.md`: document C preprocessor directive limitation
  (directives not evaluated; conditional branches always captured; macros and
  `#include` not resolved)
- `doc/scripts/reader_logical.md`: document `detect_fortran_format()` and
  the two-phase format detection logic
- `doc/scripts/executive_summary.md`: update `File` column description in
  `file_statistics.csv` to reflect relative path usage

---

## [0.7.0] — 2026-04-02

### Added
- Complete English documentation: README rewrite (PyPI mindset, CLI usage,
  Known Limitations, Future Work), CONTRIBUTING.md, `doc/architecture.md`,
  `doc/interpretation.md`, `doc/mi4d.md` (MI4D conceptual overview)
- `doc/scripts/`: 22 script reference files — all translated, renamed to
  English, and updated to reflect current column names and constants
- `uv.lock`: lockfile for reproducible installs
- `.gitignore`: standard Python/editor exclusions

### Changed
- Complete English translation of all source code: CSV column names,
  output filenames, config constants, print statements, internal identifiers
- SemVer versioning adopted (prior releases tagged as v0.1–v0.6)
- Development branch renamed: `desarrollo` → `dev`

### Fixed
- `inventory.py`: `closed_unit.tipo` → `closed_unit.type` (AttributeError
  blocking the full pipeline)
- `profiler.py`, `sloc.py`: `FOLDER_CODE` → `CODE_PATH` (ImportError)
- `complexity.py`, `consolidate.py`, `sloc.py`, `executive_summary.py`:
  `r['Archivo']` → `r['File']` in print/report generation (KeyError)

### Removed
- All Spanish-language `.md` documentation files (replaced by English versions)

---

## [0.6] — TBD

### Added
- Synthetic Fortran fixtures corpus for testing (`tests/fixtures/`)
- pytest test suite: 67 tests covering the full pipeline

### Fixed
- `inventory.py`: detection of anonymous INTERFACE blocks
- Two parser bugs exposed by the fixtures corpus

---

## [0.5] — TBD

### Changed
- Full restructure into a proper Python package (`forti4d/`)
- Source reorganized into `lib/` and `analyzers/` subdirectories
- `pyproject.toml` added; `forti4d` CLI entry point configured

---

## [0.4] — TBD

### Added
- `html_report.py`: self-contained HTML report from prioritization data
  (step 19 — pipeline grows to 19 steps)
- INCLUDE directive tracking in `profiler.py` and `inventory.py`

---

## [0.3] — TBD

### Changed
- E4 scope signals (`Implicit_None`, `Has_Equiv`) integrated into
  `cross_analysis.py` migration strategy assignment and `prioritization.py`
  risk scoring

---

## [0.2] — TBD

### Added
- `symbols.py` (step 10): variable, parameter, and implicit symbol extraction
- `derived_types.py` (step 11): derived TYPE definition extraction
- `equivalences.py` (step 12): EQUIVALENCE aliasing groups via union-find
- E4 scope risk signal (`Score_E4`) in `prioritization.py`
- EQUIVALENCE summary columns in `consolidate.py`
- Pipeline grows to 18 steps

---

## [0.1] — TBD

### Added
- Initial 15-step static analysis pipeline for Fortran (F77/F90/F95)
- Core scripts: `inventory.py`, `dependencies.py`, `profiler.py`,
  `block_analysis.py`, `structure_analysis.py`, `cross_analysis.py`,
  `executive_summary.py`, `complexity.py`, `common_blocks.py`, `sloc.py`,
  `clones.py`, `consolidate.py`, `visual_graph.py`, `prioritization.py`
- `pipeline.py`: single-command orchestrator with `--from`, `--only`,
  `--skip`, `--quiet` flags
- `config.py`: centralized path configuration via `FORT_SRC`/`FORT_OUT`
  environment variables
- `reader_logical.py`: F77 fixed-form and F90 free-form continuation handling
