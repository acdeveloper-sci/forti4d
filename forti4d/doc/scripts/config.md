# config.py

## Purpose

Central configuration module. Defines the two path constants shared by every
script in the toolkit: the Fortran source directory to analyze and the output
directory where all reports are written.

Not run directly. Imported by every pipeline script.

---

## Configuration

| Constant | Environment Variable | Default | Description |
| :--- | :--- | :--- | :--- |
| `CODE_PATH` | `FORT_SRC` | `tests/fixtures/` | Directory containing the Fortran source files to analyze |
| `RESULTS_PATH` | `FORT_OUT` | `results/` | Root directory for all output files (CSVs, audit/, blocks/, DOTs) |

Both constants are `pathlib.Path` objects.

---

## Priority Order

Each constant is resolved in this order:

1. **Environment variable present** → use that value.
2. **Environment variable absent** → use the hardcoded default.

The default values reflect the fallback path for development and testing.
To point at a real project, either edit the defaults in `config.py` or
supply the environment variables.

---

## Usage

### Editing the default (persistent change)

```python
# config.py
CODE_PATH    = Path(os.environ.get("FORT_SRC", "/new/project/path/"))
RESULTS_PATH = Path(os.environ.get("FORT_OUT", "results/"))
```

### Environment variable (one-off run)

```bash
FORT_SRC=/path/to/project FORT_OUT=out/ forti4d
```

### Via the CLI (recommended)

```bash
forti4d --project /path/to/project --output out/
```

`pipeline.py` sets `FORT_SRC` and `FORT_OUT` automatically before launching
each subprocess, so individual scripts never need to be called with env vars
when running through the pipeline.

---

## Notes

- `RESULTS_PATH` is created automatically (`mkdir(parents=True, exist_ok=True)`)
  by the first script that writes output in any given run. You do not need to
  create it manually.
- Scripts that write to subdirectories (`audit/`, `blocks/`) also create them
  as needed.
- `block_analysis.py` calls `load_inventory()` with no arguments; it relies
  on the default path in `inventory.py`, which itself reads `RESULTS_PATH`
  from `config.py`.
