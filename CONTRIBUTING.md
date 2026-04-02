# Contributing to forti4d

This guide is for developers who want to run, test, or contribute to forti4d
from source.

---

## Prerequisites

- Python 3.8+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [Graphviz](https://graphviz.org/) — optional, only needed to render `.dot` files

---

## Setup

```bash
git clone https://github.com/acdeveloper-sci/forti4d.git
cd forti4d
```

Install in editable mode with dev dependencies:

```bash
# with uv (recommended)
uv pip install -e ".[dev]"

# with pip
pip install -e ".[dev]"
```

This installs the `forti4d` CLI command pointing to your local source,
so any code changes take effect immediately without reinstalling.

---

## Running the Pipeline

```bash
forti4d --project /path/to/fortran/source --output out/
forti4d --list          # show all 19 steps
forti4d --from symbols  # resume from a specific step
forti4d --quiet         # suppress step output
```

Or without installing:

```bash
uv run forti4d --project /path/to/fortran/source --output out/
python -m forti4d.pipeline --project /path/to/fortran/source
```

---

## Running Tests

The test suite runs the full pipeline against a synthetic Fortran corpus
in `tests/fixtures/` and validates all outputs:

```bash
uv run pytest tests/ -q                      # all 67 tests
uv run pytest tests/test_inventory.py -v     # single module
```

Tests generate output to `tests/results/` (git-ignored).

---

## Project Structure

```
forti4d/                  ← Python package
├── pipeline.py           ← CLI entry point (forti4d command)
├── config.py             ← FORT_SRC / FORT_OUT env vars
├── lib/                  ← shared libraries
│   ├── reader_logical.py
│   ├── patterns_v1.py
│   ├── patterns_v2.py
│   └── kinds.py
├── analyzers/            ← 19 pipeline steps + support scripts
└── doc/                  ← documentation
    ├── architecture.md
    ├── interpretation.md
    ├── mi4d.md
    └── scripts/          ← one .md per analyzer
tests/
├── conftest.py           ← session fixture: runs pipeline once
├── fixtures/             ← synthetic Fortran corpus (8 files)
├── results/              ← generated at test time (git-ignored)
└── test_*.py             ← one module per analysis area
```

---

## Commit Conventions

```
<scope>: <short description>

fix: inventory — closed_unit.type attribute error
feat: reachability — add ENTRY_POINT status
translate: complete English translation Nivel 3a+3b+3c
docs: update README with Known Limitations and Future Work
chore: bump version to 0.7.0
```

---

## Branch Conventions

- `main` — stable, tagged releases
- `dev` — active development branch; merge to main with `--no-ff`

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `FORT_SRC` | `tests/fixtures/` | Path to Fortran source directory |
| `FORT_OUT` | `results/` | Path to output directory |
