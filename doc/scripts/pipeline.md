# pipeline.py

## Purpose

Orchestrates the full static analysis pipeline. Runs all scripts in
dependency order with a single command, propagating project and output path
configuration to each subprocess via environment variables.

---

## Usage

```bash
# Run all steps with defaults from config.py
python3 pipeline.py

# Specify project and output directory
python3 pipeline.py --project ../myproject --output out/

# List steps and active configuration
python3 pipeline.py --list

# Start from a specific step (re-run from that point forward)
python3 pipeline.py --from complejidad

# Run only selected steps
python3 pipeline.py --only sloc consolidar

# Skip specific steps
python3 pipeline.py --skip grafo_visual

# Do not stop on first failure
python3 pipeline.py --continue-on-error

# Suppress script output — show only step names and results
python3 pipeline.py --quiet
```

Flags can be combined freely:

```bash
python3 pipeline.py --project ../myproject --output out/ --from complejidad --quiet
```

---

## Flags

| Flag | Description |
| :--- | :--- |
| `--project DIR` | Path to the Fortran source directory. Sets `FORT_SRC`. |
| `--output DIR` | Directory for all output files. Sets `FORT_OUT`. |
| `--list` | Print the step list and active `FORT_SRC` / `FORT_OUT` values, then exit. |
| `--from STEP` | Skip all steps before `STEP` (inclusive start). |
| `--only STEP ...` | Run only the listed steps (space-separated). |
| `--skip STEP ...` | Exclude the listed steps. |
| `--continue-on-error` | Proceed to the next step even when a step fails. |
| `--quiet` | Suppress subprocess stdout/stderr. Prints only step name, ✓/✗, and elapsed time. On failure, shows the last 10 lines of captured output. |

---

## Steps

| Name | Script | Description |
| :--- | :--- | :--- |
| `inventario` | `inventario.py` | Build unit inventory from source files |
| `dependencias` | `dependencias.py` | Build call graph and compute Fan-In/Fan-Out |
| `perfilador` | `perfilador.py` | Classify statements and produce `audit/` DEBUG files |
| `bloques` | `analisis_bloques_v8.py` (batch) | Block topology analysis — one output file per source file |
| `analisis_estructura` | `analisis_estructura.py` | Classify files by architectural role |
| `analisis_cruzado` | `analisis_cruzado.py` | Assign migration strategy per unit |
| `resumen_ejecutivo` | `resumen_ejecutivo.py` | Generate executive summary |
| `complejidad` | `complejidad.py` | Compute McCabe cyclomatic complexity |
| `common_blocks` | `common_blocks.py` | Detect COMMON block coupling |
| `alcanzabilidad` | `alcanzabilidad.py` | Dead code detection from entry points |
| `sloc` | `sloc.py` | Precise SLOC count per unit |
| `consolidar` | `consolidar.py` | Join all reports into `reporte_consolidado.csv` |
| `grafo_visual` | `grafo_visual.py` | Generate call graph DOT files |

---

## The `bloques` Step

The `bloques` step is special: it has no single script. Instead, it
batch-runs `analisis_bloques_v8.py` once per `*_DEBUG.csv` file found in
`<FORT_OUT>/audit/`. Output files are written to `<FORT_OUT>/bloques/`.

This step requires `perfilador` to have run first.

---

## Environment Variable Propagation

`--project` and `--output` set `FORT_SRC` and `FORT_OUT` in the environment
inherited by each subprocess. Scripts read these via `config.py`, so they
always use the values specified at pipeline invocation — regardless of the
defaults in `config.py`.

When neither flag is provided, subprocesses use whatever `FORT_SRC`/`FORT_OUT`
are already set in the shell, falling back to the `config.py` defaults.

---

## Output

Terminal output includes per-step timing and a final summary table:

```
=== Fortran Static Analysis Pipeline ===
Project : ../athys/mercedes/
Output  : results/
Steps   : 13

────────────────────────────────────────────────────────────
[1/13] inventario  —  Build unit inventory from source files
────────────────────────────────────────────────────────────
...
  ✓ OK  2.3s

────────────────────────────────────────────────────────────
Summary  —  45.1s total
────────────────────────────────────────────────────────────
  ✓  inventario              2.3s
  ✓  dependencias            8.7s
  ...

All 13 steps completed successfully.
```
