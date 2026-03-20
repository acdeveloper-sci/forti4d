# Fortran Static Analysis Toolkit

A collection of Python scripts for static analysis of Fortran source code.
Designed to work with real-world hybrid Fortran corpora (mixed F77/F90),
where general-purpose parsers typically fail.

> **Language note:** Source code, variable names, CSV column headers, and
> console output are currently in Spanish. Migration to English is planned
> for a future release.

---

## Requirements

- Python 3.8+
- [Graphviz](https://graphviz.org/) — only required for rendering `.dot` files
  produced by `grafo_visual.py`
- No third-party Python packages — standard library only

---

## Input

All scripts expect the Fortran source files to be in a directory configured
in `inventario.py` via the `CARPETA_CODIGO` constant (default: `../athys/mercedes/`).

The pipeline must be run **in order**: each script produces CSV files that
later scripts consume.

---

## Pipeline

```
inventario.py          →  reporte_inventario.csv
dependencias.py        →  dep_00_ambiguedades.csv
                          dep_01_llamadas.csv
                          dep_02_grafo_unidades.csv
                          dep_03_matriz_impacto.csv
perfilador.py          →  reporte_densidad.csv
                          audit/<file>_DEBUG.csv  (one per source file)
analisis_estructura.py →  reporte_estructura.csv
analisis_bloques_v8.py →  reporte_bloques.csv
analisis_cruzado.py    →  reporte_cruzado.csv
resumen_ejecutivo.py   →  RESUMEN_PROYECTO.md
                          estadisticas_por_archivo.csv
─── above: original pipeline ──────────────────────────────────────────────
complejidad.py         →  reporte_complejidad.csv
common_blocks.py       →  common_uso.csv
                          common_acoplamiento.csv
alcanzabilidad.py      →  reporte_alcanzabilidad.csv
sloc.py                →  reporte_sloc.csv
consolidar.py          →  reporte_consolidado.csv
grafo_visual.py        →  grafo_completo.dot
                          grafo_simple.dot
                          grafo_<entry>.dot  (when --entry is used)
```

> `perfilador.py` must run before `complejidad.py`, `common_blocks.py`,
> and `alcanzabilidad.py`, because all three read the `audit/*_DEBUG.csv`
> files it produces.
>
> `consolidar.py` must run last — it joins all other reports.

---

## Usage

Run each script from the `src/` directory:

```bash
python inventario.py
python dependencias.py
python perfilador.py
python analisis_estructura.py
python analisis_bloques_v8.py
python analisis_cruzado.py
python resumen_ejecutivo.py
python complejidad.py
python common_blocks.py
python alcanzabilidad.py
python sloc.py
python consolidar.py
python grafo_visual.py
```

### grafo_visual.py options

```bash
# List all entry points found in the corpus
python grafo_visual.py --list

# Generate the call graph for a single executable
python grafo_visual.py --entry mcdes

# Generate a combined graph for several executables
# (shared nodes are highlighted in yellow)
python grafo_visual.py --entry util0 util1 util2

# Include USE (module import) edges — omitted by default
python grafo_visual.py --entry mcdes --use

# Render a .dot file (requires Graphviz)
dot -Tpng grafo_mcdes.dot -o grafo_mcdes.png
dot -Tsvg grafo_completo.dot -o grafo_completo.svg
```

---

## Output Files

| File | Produced by | Description |
| :--- | :--- | :--- |
| `reporte_inventario.csv` | `inventario.py` | All program units with type, line range, and audit flags |
| `dep_00_ambiguedades.csv` | `dependencias.py` | Units defined in more than one source file |
| `dep_01_llamadas.csv` | `dependencias.py` | Raw call/use relationships |
| `dep_02_grafo_unidades.csv` | `dependencias.py` | Resolved call graph (CALL, USE, FUNC_CALL edges) |
| `dep_03_matriz_impacto.csv` | `dependencias.py` | Fan-In and Fan-Out per unit |
| `reporte_densidad.csv` | `perfilador.py` | Statement density profile per unit (% calculation, control, I/O, legacy) |
| `audit/<file>_DEBUG.csv` | `perfilador.py` | Per-line statement classification for each source file |
| `reporte_estructura.csv` | `analisis_estructura.py` | Structural categories (islands, hubs, entry points, etc.) |
| `reporte_bloques.csv` | `analisis_bloques_v8.py` | Block nesting depth and construct counts per unit |
| `reporte_cruzado.csv` | `analisis_cruzado.py` | Cross-analysis combining density and structural metrics |
| `RESUMEN_PROYECTO.md` | `resumen_ejecutivo.py` | Executive summary in Markdown |
| `estadisticas_por_archivo.csv` | `resumen_ejecutivo.py` | Per-file summary statistics |
| `reporte_complejidad.csv` | `complejidad.py` | McCabe cyclomatic complexity per unit |
| `common_uso.csv` | `common_blocks.py` | COMMON block usage per unit |
| `common_acoplamiento.csv` | `common_blocks.py` | COMMON block coupling risk |
| `reporte_alcanzabilidad.csv` | `alcanzabilidad.py` | Reachability from entry points (dead code detection) |
| `reporte_sloc.csv` | `sloc.py` | Precise SLOC count per unit (LOC, blanks, comments, continuations) |
| `reporte_consolidado.csv` | `consolidar.py` | All metrics joined — one row per unit, 25 columns |
| `grafo_*.dot` | `grafo_visual.py` | Graphviz call graph (full, simplified, or per entry point) |

---

## Support Scripts

These are not run directly but are imported by the pipeline scripts:

| File | Role |
| :--- | :--- |
| `reader_logical.py` | Fortran logical line reader — handles F77 fixed-form and F90 free-form continuation |
| `patterns_v1.py` | Regex patterns for unit boundaries (used by `inventario.py`) |
| `patterns_v2.py` | Extended regex patterns for statement classification (used by `perfilador.py`) |
| `kinds.py` | Enum of statement kinds |

---

## Design Notes

- **No external parser required.** The toolkit uses a custom logical-line
  reader (`reader_logical.py`) and regex patterns calibrated for hybrid
  Fortran code. This is intentional — general-purpose Fortran parsers
  (fparser, OFP) are unreliable on real-world legacy codebases.

- **Scope resolution** is based on the line ranges (`Linea_Inicio`,
  `Linea_Fin`) recorded in the inventory. Every metric is attributed to
  the innermost program unit containing the statement's line number.

- **Entry points** are units with type `PROGRAM` or `IMPLICIT-MAIN`
  (files that compile to an executable without an explicit `PROGRAM`
  statement). The corpus may contain several — one per executable.
