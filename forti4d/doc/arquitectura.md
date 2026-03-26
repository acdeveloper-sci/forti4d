# Architecture

## Overview

The toolkit is organized as a sequential pipeline of independent Python scripts.
Each script reads one or more CSV files produced by earlier steps and writes
its own output files. No script modifies another script's output.

All scripts are run from the `src/` directory. Output files are written to the
current directory (or to `audit/` and `bloques/` for intermediate artifacts).

---

## Script Tiers

### Tier 1 — Support Libraries (not run directly)

| Script | Role |
| :--- | :--- |
| `reader_logical.py` | Core Fortran line reader. Handles F77 fixed-form and F90 free-form continuation, comments, and blank lines. Returns a list of `LogicalLine` objects. Used by `inventario.py`, `perfilador.py`, and `sloc.py`. |
| `patterns_v1.py` | Regex patterns for program unit boundaries (`PROGRAM`, `MODULE`, `SUBROUTINE`, `FUNCTION`, `BLOCK DATA`, `END`). Used by `inventario.py`. |
| `patterns_v2.py` | Extended regex patterns for statement classification (control flow, I/O, declarations, legacy constructs, etc.). Used by `perfilador.py`. |
| `kinds.py` | Enum of statement kinds (`StatementKind`). Referenced by `perfilador.py` to classify and group statements. |

---

### Tier 2 — Original Pipeline

These scripts form the foundation. They must run in order.

```
inventario.py
    └─ dependencias.py
    └─ perfilador.py
            └─ analisis_bloques_v8.py  (per-file, interactive)
    └─ analisis_estructura.py
    └─ analisis_cruzado.py
    └─ resumen_ejecutivo.py
```

#### `inventario.py`
- **Reads:** Fortran source files in `CARPETA_CODIGO`
- **Writes:** `reporte_inventario.csv`
- **Role:** Foundation of the entire pipeline. Scans all source files, identifies every program unit (PROGRAM, MODULE, SUBROUTINE, FUNCTION, BLOCK DATA), records its type, parent unit, line range, and audit flags (legacy constructs, I/O statements).
- **All other scripts depend on this output.**

#### `dependencias.py`
- **Reads:** `reporte_inventario.csv` + Fortran source files
- **Writes:** `dep_00_ambiguedades.csv`, `dep_01_datos_maestros.csv`, `dep_02_grafo_unidades.csv`, `dep_03_matriz_impacto.csv`, `dep_04_externos_huerfanos.csv`, `dep_05_dependencia_archivos.csv`, `dep_06_include_files.csv`
- **Role:** Builds the call graph. Resolves CALL, USE, and function-call references between units. Computes Fan-In and Fan-Out per unit. Flags units defined in multiple files (ambiguities) and references with no known definition (orphans).

#### `perfilador.py`
- **Reads:** `reporte_inventario.csv` + Fortran source files
- **Writes:** `reporte_densidad.csv` + `audit/<file>_DEBUG.csv` (one per source file)
- **Role:** Classifies every logical statement in every source file using `patterns_v2.py` and `kinds.py`. Computes statement density profiles per unit (% calculation, % control flow, % I/O, % legacy, % declarations). The `audit/` DEBUG files are the primary intermediate artifact consumed by the extended analysis tier.

#### `analisis_bloques_v8.py`
- **Reads:** a single `audit/<file>_DEBUG.csv` (passed as command-line argument)
- **Writes:** stdout only (redirect to save)
- **Role:** Diagnostic tool for block topology analysis. Takes one DEBUG file at a time and prints a hierarchical view of control-flow block nesting (IF/DO/SELECT depth) per unit in that file. Not a batch pipeline script.
- **Usage:** `python analisis_bloques_v8.py audit/geolec.f90_DEBUG.csv`
- **Batch usage:** `for f in audit/*_DEBUG.csv; do python analisis_bloques_v8.py "$f" > bloques/$(basename $f _DEBUG.csv)_bloques.txt; done`

#### `analisis_estructura.py`
- **Reads:** `dep_03_matriz_impacto.csv`, `reporte_inventario.csv`
- **Writes:** `analisis_nodos_criticos.csv`
- **Role:** Classifies each source file into an architectural role based on its Fan-In/Fan-Out profile: `NODO_CRITICO` (high Fan-In), `ORQUESTADOR` (high Fan-Out), `ENTRY_POINT` (executable), `OBRERO` (service routine), `ISLA` (no connections), or `MIXTO`.

#### `analisis_cruzado.py`
- **Reads:** `reporte_densidad.csv`, `dep_03_matriz_impacto.csv` + optionally `reporte_alcanzabilidad.csv`, `simbolos_implicit.csv`, `equivalencias.csv`
- **Writes:** `reporte_estrategia_migracion.csv`
- **Role:** Assigns a migration strategy to each unit by crossing density metrics with coupling data. Computes two composite indices — ICM (migration complexity) and IVC (calculation value) — and applies a rule engine to classify each unit as: `MIGRACION_DIRECTA`, `MIGRACION_ESTANDAR`, `REEMPLAZAR_LIB`, `REFACTORIZAR_CORE`, `REESCRIBIR_AISLADO`, `ANALIZAR_UTILIDAD`, or `ELIMINAR`. When reachability data is present, confirmed `NO_ALCANZABLE` units are forced to `ELIMINAR`. When E4 data is present, adds a penalty (max 7 points) to ICM for units without IMPLICIT NONE and/or with EQUIVALENCE aliasing.

#### `resumen_ejecutivo.py`
- **Reads:** `reporte_inventario.csv`, `dep_03_matriz_impacto.csv` + optionally `simbolos_implicit.csv`, `equivalencias.csv`, `common_uso.csv`, `simbolos_variables.csv`
- **Writes:** `RESUMEN_PROYECTO.md`, `estadisticas_por_archivo.csv`
- **Role:** Produces a high-level executive summary in Markdown. Reports global metrics (LOC, unit counts, type distribution), top monolithic files, legacy/I/O health indicators, and the most critical and most orchestrating units. When E4 data is present, adds a "Scope Health" section with IMPLICIT NONE coverage, EQUIVALENCE/COMMON exposure, scope-clean unit count, and top units by variable density.

---

### Tier 3 — Extended Analysis

These scripts add deeper metrics. They require Tier 2 outputs to be present,
especially the `audit/` directory produced by `perfilador.py`.

```
complejidad.py      ─┐
common_blocks.py    ─┤─ all read audit/*_DEBUG.csv + reporte_inventario.csv
alcanzabilidad.py   ─┘─ reads dep_02_grafo_unidades.csv + reporte_inventario.csv
sloc.py             ─── reads source files + reporte_inventario.csv
clones.py           ─── reads source files + reporte_inventario.csv
        │
        └──► consolidar.py  ─── joins all reports → reporte_consolidado.csv
                    │
                    ├──► grafo_visual.py   ─── reads dep_02 + reporte_consolidado.csv
                    │
                    └──► priorizacion.py  ─── reads consolidado + clones + estrategia
```

#### `complejidad.py`
- **Reads:** `audit/*_DEBUG.csv`, `reporte_inventario.csv`
- **Writes:** `reporte_complejidad.csv`
- **Role:** Computes McCabe cyclomatic complexity (CC) per unit by counting decision points (IF, ELSE IF, DO, non-default CASE, WHERE, FORALL) from the DEBUG files. Uses scope resolution via line ranges. CC scale: BAJA (1–10), MEDIA (11–20), ALTA (21–50), CRITICA (>50).

#### `common_blocks.py`
- **Reads:** `audit/*_DEBUG.csv`, `reporte_inventario.csv`
- **Writes:** `common_uso.csv`, `common_acoplamiento.csv`
- **Role:** Detects F77 COMMON block usage. Parses COMMON statements, resolves block names (including blank COMMON represented as `(BLANK)`), and reports which units share each block. Assigns coupling risk: BAJO (1 unit), MEDIO (2–4 units), ALTO (5+ units).

#### `alcanzabilidad.py`
- **Reads:** `dep_02_grafo_unidades.csv`, `reporte_inventario.csv`
- **Writes:** `reporte_alcanzabilidad.csv`
- **Role:** Dead code detection via BFS from all entry points (PROGRAM and IMPLICIT-MAIN units). Follows CALL, USE, and FUNC_CALL edges. Classifies each unit as ENTRADA, ALCANZABLE, or NO_ALCANZABLE. Resolves the `MAIN__<file>` node naming convention used by `dependencias.py` for IMPLICIT-MAIN units.

#### `sloc.py`
- **Reads:** Fortran source files + `reporte_inventario.csv`
- **Writes:** `reporte_sloc.csv`
- **Role:** Precise SLOC counting per unit. Uses `reader_logical.py` to classify each physical line as BLANK, COMMENT, CODE, or CONTINUATION. Computes LOC, SLOC_fisico (LOC minus blanks and comments), SLOC_neto (logical statements only), and comment density percentage.

#### `consolidar.py`
- **Reads:** `reporte_inventario.csv`, `reporte_sloc.csv`, `reporte_complejidad.csv`, `dep_03_matriz_impacto.csv`, `reporte_densidad.csv`, `reporte_alcanzabilidad.csv`, `common_uso.csv`, `simbolos_variables.csv`, `simbolos_firmas.csv`, `simbolos_implicit.csv`, `tipos_definicion.csv`, `equivalencias.csv`, `audit/*_DEBUG.csv`
- **Writes:** `reporte_consolidado.csv`
- **Role:** Joins all per-unit reports into a single 34-column CSV (one row per unit). Adds the derived metric CC_SLOC, E4 symbol summary columns (N_Vars_Locales, N_Params, N_Args_Formales, Implicit_None, N_Tipos_Derivados, Tiene_Equiv, N_Grupos_Equiv), and statement-level counts from the audit CSVs (N_Data_Stmts, N_Entry_Stmts). Must run after all other analysis scripts.

#### `clones.py`
- **Reads:** `reporte_inventario.csv`, Fortran source files
- **Writes:** `reporte_clones.csv`
- **Role:** Detects identical, similar, and diverged duplicate units across files. Compares units with the same name appearing in multiple files using normalized token sequences. Classifies each pair as IDENTICO, SIMILAR, or DIVERGIDO.

#### `grafo_visual.py`
- **Reads:** `dep_02_grafo_unidades.csv`, `reporte_consolidado.csv`
- **Writes:** `grafo_completo.dot`, `grafo_simple.dot`, and/or `grafo_<entry>.dot`
- **Role:** Generates Graphviz DOT files for call graph visualization. Supports full corpus view or per-entry-point filtered subgraphs. Nodes are colored by reachability status and shaped by unit type. Clusters source files. Resolves `MAIN__` node names to inventory names.
- **Flags:** `--list`, `--entry <name> [name…]`, `--use`

#### `priorizacion.py`
- **Reads:** `reporte_consolidado.csv`, `reporte_clones.csv`, `reporte_estrategia_migracion.csv`
- **Writes:** `reporte_priorizacion.csv`
- **Role:** Computes a composite risk/effort score (0–100) per unit across five signals: cyclomatic complexity (30%), Fan-In criticality (30%), legacy density (20%), clone state (15%), and E4 scope risk — no IMPLICIT NONE + EQUIVALENCE aliasing (5%). Ranks units into CRITICA / ALTA / MEDIA / BAJA / DEAD_CODE tiers for migration planning.

#### `reporte_html.py`
- **Reads:** `reporte_priorizacion.csv`
- **Writes:** `reporte.html`
- **Role:** Generates a self-contained HTML report with priority summary cards and a filterable/sortable unit table. No external dependencies — stdlib only, inline CSS and JavaScript.

---

### Tier 4 — E4 ScopeManager

These scripts extract the symbol-level microstructure of each unit (Eje Z of
the MI4D model). They all read `audit/*_DEBUG.csv` produced by `perfilador.py`
and the inventory for scope resolution.

```
audit/*_DEBUG.csv + reporte_inventario.csv
        │
        ├──► simbolos.py       → simbolos_variables.csv
        │                         simbolos_firmas.csv
        │                         simbolos_implicit.csv
        │
        ├──► tipos_derivados.py → tipos_definicion.csv
        │                         tipos_componentes.csv
        │
        └──► equivalencias.py  → equivalencias.csv
```

#### `simbolos.py`
- **Reads:** `audit/*_DEBUG.csv`, `reporte_inventario.csv`
- **Writes:** `simbolos_variables.csv`, `simbolos_firmas.csv`, `simbolos_implicit.csv`
- **Role:** Extracts variable declarations, PARAMETER constants, formal arguments of subroutines/functions, and IMPLICIT rules from each unit. Handles F77 and F90 syntax. Cross-references COMMON statements to populate the `En_Common` field post-processing.

#### `tipos_derivados.py`
- **Reads:** `audit/*_DEBUG.csv`, `reporte_inventario.csv`
- **Writes:** `tipos_definicion.csv`, `tipos_componentes.csv`
- **Role:** Extracts derived TYPE definitions and their component fields using a per-file state machine. Identifies the host unit for each TYPE via scope resolution.

#### `equivalencias.py`
- **Reads:** `audit/*_DEBUG.csv`, `reporte_inventario.csv`
- **Writes:** `equivalencias.csv`
- **Role:** Detects EQUIVALENCE aliasing groups using a union-find algorithm. Resolves transitive aliasing across multiple EQUIVALENCE statements within the same unit. One row per variable per aliasing group.

---

## Data Flow Diagram

```
Fortran source files ──────────────────────────────────────────────┐
         │                                                          │
         ▼                                                          │
   inventario.py → reporte_inventario.csv ──────────────────────┐  │
         │                                                       │  │
         ├──► dependencias.py → dep_00…dep_05_*.csv ──────┐     │  │
         │                           │                     │     │  │
         │                    dep_02_grafo.csv ────────────┼──► alcanzabilidad.py
         │                    dep_03_impacto.csv ──────────┼──► analisis_estructura.py
         │                                                 │    analisis_cruzado.py
         │                                                 │    resumen_ejecutivo.py
         │                                                 │
         ├──► perfilador.py → reporte_densidad.csv         │
         │              └──► audit/*_DEBUG.csv ────────────┼──► complejidad.py
         │                        │                        │    common_blocks.py
         │                        │                        │    simbolos.py      ─┐
         │                        │                        │    tipos_derivados.py─┤→ E4 CSVs
         │                        │                        │    equivalencias.py ─┘
         │                        └──► analisis_bloques    │    (diagnostic, per file)
         │                                                 │
         ├──► sloc.py → reporte_sloc.csv                   │
         │                                                 │
         └──► clones.py → reporte_clones.csv               │
                                                           │
              [all reports above] ──────────────────────────┘
                        │
                        ▼
                 consolidar.py → reporte_consolidado.csv
                        │
                        ├──► grafo_visual.py → grafo_*.dot
                        │
                        └──► priorizacion.py → reporte_priorizacion.csv
```

---

## Key Design Decisions

**Scope resolution** — Every metric that must be attributed to a specific unit
(CC, SLOC, density, COMMON usage) uses the same approach: for each source line,
find all units whose `[Linea_Inicio, Linea_Fin]` range contains that line, then
assign to the innermost one (the one with the highest `Linea_Inicio`).

**No external parser** — The toolkit deliberately avoids general-purpose Fortran
parsers. `reader_logical.py` handles continuation lines and comment detection
for both F77 fixed-form and F90 free-form. Statement classification is done with
calibrated regex patterns (`patterns_v1.py`, `patterns_v2.py`). This makes the
toolkit robust on hybrid real-world codebases where standard parsers fail.

**IMPLICIT-MAIN units** — Files that compile to an executable without an
explicit `PROGRAM` statement are identified as `IMPLICIT-MAIN` in the inventory.
`dependencias.py` represents them as `MAIN__<filename>` nodes in the call graph.
`alcanzabilidad.py` and `grafo_visual.py` resolve this convention back to the
inventory name for display.

**All scripts are optional after `inventario.py`** — With the exception of the
`audit/` dependency between `perfilador.py` and the extended analysis scripts,
each script can be run independently if its input files are present. There is no
single entry point that orchestrates the full pipeline.
