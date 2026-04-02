# pipeline.py

## Purpose

Orchestrates the full static analysis pipeline. Runs all scripts in
dependency order with a single command, propagating project and output path
configuration to each subprocess via environment variables.

---

## Usage

```bash
# Run all steps with defaults from config.py
forti4d

# Specify project and output directory
forti4d --project ../myproject --output out/

# List steps and active configuration
forti4d --list

# Start from a specific step (re-run from that point forward)
forti4d --from complexity

# Run only selected steps
forti4d --only sloc consolidate

# Skip specific steps
forti4d --skip visual_graph

# Do not stop on first failure
forti4d --continue-on-error

# Suppress script output — show only step names and results
forti4d --quiet
```

Flags can be combined freely:

```bash
forti4d --project ../myproject --output out/ --from complexity --quiet
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
| `inventory` | `inventory.py` | Build unit inventory from source files |
| `dependencies` | `dependencies.py` | Build call graph and compute Fan-In/Fan-Out |
| `profiler` | `profiler.py` | Classify statements and produce `audit/` DEBUG files |
| `blocks` | `block_analysis.py` (batch) | Block topology analysis — one output file per source file |
| `structure_analysis` | `structure_analysis.py` | Classify files by architectural role |
| `cross_analysis` | `cross_analysis.py` | Assign migration strategy per unit |
| `executive_summary` | `executive_summary.py` | Generate executive summary |
| `complexity` | `complexity.py` | Compute McCabe cyclomatic complexity |
| `common_blocks` | `common_blocks.py` | Detect COMMON block coupling |
| `symbols` | `symbols.py` | Extract variable/parameter/implicit symbols per unit |
| `derived_types` | `derived_types.py` | Extract derived TYPE definitions and their components |
| `equivalences` | `equivalences.py` | Detect EQUIVALENCE aliasing groups (union-find) |
| `reachability` | `reachability.py` | Dead code detection from entry points |
| `sloc` | `sloc.py` | Precise SLOC count per unit |
| `clones` | `clones.py` | Detect identical/similar/diverged duplicate units |
| `consolidate` | `consolidate.py` | Join all reports into `report_consolidated.csv` |
| `visual_graph` | `visual_graph.py` | Generate call graph DOT files |
| `prioritization` | `prioritization.py` | Compute composite risk score and rank units for migration |
| `html_report` | `html_report.py` | Generate self-contained HTML report |

---

## The `blocks` Step

The `blocks` step is special: it has no single script. Instead, it
batch-runs `block_analysis.py` once per `*_DEBUG.csv` file found in
`<FORT_OUT>/audit/`. Output files are written to `<FORT_OUT>/blocks/`.

This step requires `profiler` to have run first.

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
Project : ../myproject/
Output  : results/
Steps   : 19

────────────────────────────────────────────────────────────
[1/19] inventory  —  Build unit inventory from source files
────────────────────────────────────────────────────────────
...
  ✓ OK  2.3s

────────────────────────────────────────────────────────────
Summary  —  45.1s total
────────────────────────────────────────────────────────────
  ✓  inventory              2.3s
  ✓  dependencies           8.7s
  ...

All 19 steps completed successfully.
```
