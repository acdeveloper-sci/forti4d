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

Source directory and output directory are configured via environment variables
`FORT_SRC` and `FORT_OUT`, with fallbacks in `config.py`.

---

## Quick Start

Run the full 18-step pipeline with a single command:

```bash
python pipeline.py
python pipeline.py --project ../myproject --output out/
python pipeline.py --list          # show all steps
python pipeline.py --from simbolos # resume from a specific step
python pipeline.py --quiet         # suppress script output
```

See `doc/scripts/pipeline.md` for all flags and options.

---

## Pipeline

The 18 steps in dependency order:

```
inventario.py          →  reporte_inventario.csv
dependencias.py        →  dep_00_ambiguedades.csv
                          dep_01_datos_maestros.csv
                          dep_02_grafo_unidades.csv
                          dep_03_matriz_impacto.csv
                          dep_04_externos_huerfanos.csv
                          dep_05_dependencia_archivos.csv
perfilador.py          →  reporte_densidad.csv
                          audit/<file>_DEBUG.csv  (one per source file)
analisis_bloques_v8.py →  bloques/<file>_bloques.txt  (batch, one per source file)
analisis_estructura.py →  analisis_nodos_criticos.csv
analisis_cruzado.py    →  reporte_estrategia_migracion.csv
resumen_ejecutivo.py   →  RESUMEN_PROYECTO.md
                          estadisticas_por_archivo.csv
complejidad.py         →  reporte_complejidad.csv
common_blocks.py       →  common_uso.csv
                          common_acoplamiento.csv
─── E4 ScopeManager ──────────────────────────────────────────────────────────
simbolos.py            →  simbolos_variables.csv
                          simbolos_firmas.csv
                          simbolos_implicit.csv
tipos_derivados.py     →  tipos_definicion.csv
                          tipos_componentes.csv
equivalencias.py       →  equivalencias.csv
─── ──────────────────────────────────────────────────────────────────────────
alcanzabilidad.py      →  reporte_alcanzabilidad.csv
sloc.py                →  reporte_sloc.csv
clones.py              →  reporte_clones.csv
consolidar.py          →  reporte_consolidado.csv
grafo_visual.py        →  grafo_*.dot
priorizacion.py        →  reporte_priorizacion.csv
```

> `perfilador.py` must run before `complejidad.py`, `common_blocks.py`,
> `simbolos.py`, `tipos_derivados.py`, and `equivalencias.py` — all read
> the `audit/*_DEBUG.csv` files it produces.
>
> `consolidar.py` must run after all analysis scripts — it joins all reports.
>
> `priorizacion.py` must run after `consolidar.py`.

---

## Output Files

| File | Produced by | Description |
| :--- | :--- | :--- |
| `reporte_inventario.csv` | `inventario.py` | All program units with type, line range, and audit flags |
| `dep_00_ambiguedades.csv` | `dependencias.py` | Units defined in more than one source file |
| `dep_01_datos_maestros.csv` | `dependencias.py` | Raw call/use relationships |
| `dep_02_grafo_unidades.csv` | `dependencias.py` | Resolved call graph (CALL, USE, FUNC_CALL edges) |
| `dep_03_matriz_impacto.csv` | `dependencias.py` | Fan-In and Fan-Out per unit |
| `dep_04_externos_huerfanos.csv` | `dependencias.py` | External references with no known definition in the corpus |
| `dep_05_dependencia_archivos.csv` | `dependencias.py` | File-level dependency summary |
| `reporte_densidad.csv` | `perfilador.py` | Statement density profile per unit (% calculation, control, I/O, legacy) |
| `audit/<file>_DEBUG.csv` | `perfilador.py` | Per-line statement classification for each source file |
| `bloques/<file>_bloques.txt` | `analisis_bloques_v8.py` | Block topology per source file |
| `analisis_nodos_criticos.csv` | `analisis_estructura.py` | Structural categories (islands, hubs, entry points, etc.) |
| `reporte_estrategia_migracion.csv` | `analisis_cruzado.py` | Migration strategy per unit |
| `RESUMEN_PROYECTO.md` | `resumen_ejecutivo.py` | Executive summary in Markdown |
| `estadisticas_por_archivo.csv` | `resumen_ejecutivo.py` | Per-file summary statistics |
| `reporte_complejidad.csv` | `complejidad.py` | McCabe cyclomatic complexity per unit |
| `common_uso.csv` | `common_blocks.py` | COMMON block usage per unit |
| `common_acoplamiento.csv` | `common_blocks.py` | COMMON block coupling risk |
| `simbolos_variables.csv` | `simbolos.py` | Variable and PARAMETER constant declarations per unit |
| `simbolos_firmas.csv` | `simbolos.py` | Formal arguments per subroutine/function |
| `simbolos_implicit.csv` | `simbolos.py` | IMPLICIT rules per unit |
| `tipos_definicion.csv` | `tipos_derivados.py` | Derived TYPE definitions with host unit and component count |
| `tipos_componentes.csv` | `tipos_derivados.py` | Component fields of each derived TYPE |
| `equivalencias.csv` | `equivalencias.py` | EQUIVALENCE aliasing groups (union-find) |
| `reporte_alcanzabilidad.csv` | `alcanzabilidad.py` | Reachability from entry points (dead code detection) |
| `reporte_sloc.csv` | `sloc.py` | Precise SLOC count per unit (LOC, blanks, comments, continuations) |
| `reporte_clones.csv` | `clones.py` | Identical/similar/diverged duplicate unit pairs |
| `reporte_consolidado.csv` | `consolidar.py` | All metrics joined — one row per unit, 32 columns |
| `grafo_*.dot` | `grafo_visual.py` | Graphviz call graph (full, simplified, or per entry point) |
| `reporte_priorizacion.csv` | `priorizacion.py` | Units ranked by composite migration risk score |

---

## Support Scripts

These are not run directly but are imported by the pipeline scripts:

| File | Role |
| :--- | :--- |
| `config.py` | Centralized path configuration — reads `FORT_SRC` / `FORT_OUT` env vars |
| `reader_logical.py` | Fortran logical line reader — handles F77 fixed-form and F90 free-form continuation |
| `patterns_v1.py` | Regex patterns for unit boundaries (used by `inventario.py`) |
| `patterns_v2.py` | Extended regex patterns for statement classification (used by `perfilador.py`) |
| `kinds.py` | Enum of statement kinds |

---

## Documentation

Detailed documentation for each script is in `doc/scripts/`. Architecture
overview and design decisions are in `doc/arquitectura.md`.

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

- **E4 ScopeManager** scripts (`simbolos.py`, `tipos_derivados.py`,
  `equivalencias.py`) populate the symbol-level layer of the analysis:
  what is declared inside each unit, not just that the unit exists.
