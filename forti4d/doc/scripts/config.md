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
| `CARPETA_CODIGO` | `FORT_SRC` | `../athys/mercedes/` | Directory containing the Fortran source files to analyze |
| `RUTA_RESULTADOS` | `FORT_OUT` | `results/` | Root directory for all output files (CSVs, audit/, bloques/, DOTs) |

Both constants are `pathlib.Path` objects.

---

## Priority Order

Each constant is resolved in this order:

1. **Environment variable present** → use that value.
2. **Environment variable absent** → use the hardcoded default.

The default values reflect the current active project. To switch projects,
either edit the defaults in `config.py` or supply the environment variables.

---

## Usage

### Editing the default (persistent change)

```python
# config.py
CARPETA_CODIGO  = Path(os.environ.get("FORT_SRC", "/new/project/path/"))
RUTA_RESULTADOS = Path(os.environ.get("FORT_OUT", "results/"))
```

### Environment variable (one-off run)

```bash
FORT_SRC=/path/to/project FORT_OUT=out/ python3 inventario.py
```

### Via pipeline.py (recommended)

```bash
python3 pipeline.py --project /path/to/project --output out/
```

`pipeline.py` sets `FORT_SRC` and `FORT_OUT` automatically before launching
each subprocess, so individual scripts never need to be called with env vars
when running through the pipeline.

---

## Notes

- `RUTA_RESULTADOS` is created automatically (`mkdir(parents=True, exist_ok=True)`)
  by the first script that writes output in any given run. You do not need to
  create it manually.
- Scripts that write to subdirectories (`audit/`, `bloques/`) also create them
  as needed.
- `analisis_bloques_v8.py` calls `cargar_inventario()` with no arguments;
  it relies on the default path in `inventario.py`, which itself reads
  `RUTA_RESULTADOS` from `config.py`.
