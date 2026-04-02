# Changelog

All notable changes to forti4d are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/) from v0.7.0 onward.

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
