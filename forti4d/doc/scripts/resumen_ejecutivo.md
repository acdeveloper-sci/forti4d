# resumen_ejecutivo.py

## Purpose

Produces a high-level executive summary of the corpus: global metrics, type
distribution, largest files, legacy/I/O health indicators, and the most
critical and most orchestrating units.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTARIO` | `RUTA_RESULTADOS / "reporte_inventario.csv"` | Input: unit inventory |
| `DEPENDENCIAS` | `RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"` | Input: Fan-In / Fan-Out |
| `SIMBOLOS_IMPL_CSV` | `RUTA_RESULTADOS / "simbolos_implicit.csv"` | Optional: IMPLICIT NONE coverage |
| `EQUIVALENCIAS_CSV` | `RUTA_RESULTADOS / "equivalencias.csv"` | Optional: EQUIVALENCE aliasing |
| `COMMON_USO_CSV` | `RUTA_RESULTADOS / "common_uso.csv"` | Optional: COMMON block usage |
| `SIMBOLOS_VARS_CSV` | `RUTA_RESULTADOS / "simbolos_variables.csv"` | Optional: variable density per unit |
| `OUT_MD` | `RUTA_RESULTADOS / "RESUMEN_PROYECTO.md"` | Output: Markdown summary |
| `OUT_CSV` | `RUTA_RESULTADOS / "estadisticas_por_archivo.csv"` | Output: per-file statistics |

---

## Inputs

Required:
- `<FORT_OUT>/reporte_inventario.csv`
- `<FORT_OUT>/dep_03_matriz_impacto.csv`

Optional (section 5 is generated only when at least one of these exists):
- `<FORT_OUT>/simbolos_implicit.csv`
- `<FORT_OUT>/equivalencias.csv`
- `<FORT_OUT>/common_uso.csv`
- `<FORT_OUT>/simbolos_variables.csv`

---

## Outputs

### `<FORT_OUT>/RESUMEN_PROYECTO.md`

Markdown document with the following sections:

1. **Global Metrics** — total files, LOC, units, average LOC per file
2. **Unit Type Distribution** — count and % per type
3. **Top 10 Largest Files** — sorted by LOC, with unit count and types
4. **Health Indicators (Legacy)** — units with legacy constructs and I/O,
   with frequency tables for each construct type
5. **Scope Health (E4)** — IMPLICIT NONE coverage, EQUIVALENCE and COMMON
   block exposure, scope-clean unit count, top 5 by variable density.
   Only generated when at least one E4 optional source is present.
6. **Critical Units (highest Fan-In)** — top 15 most reused units
7. **Orchestrating Units (highest Fan-Out)** — top 15 units with most dependencies

### `<FORT_OUT>/estadisticas_por_archivo.csv`

One row per source file.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Total_Lineas` | Total LOC (from root-level units only, to avoid double-counting) |
| `Total_Unidades` | Number of units in the file |
| `Tiene_Legacy` | `SI` / `NO` |
| `Tiene_IO` | `SI` / `NO` |
| `Tipos_Presentes` | Semicolon-separated list of unit types in the file |

---

## Notes

- LOC is taken from the `Lineas_Total` column of the inventory. Only
  root-level units (`Padre = GLOBAL`) are summed per file to avoid
  double-counting nested units.
- The Legacy and I/O percentages in the Markdown report are computed as
  *units with at least one flag / total units*, not as raw flag counts.
- **Scope-clean** units in section 5 are those with `IMPLICIT NONE`,
  no EQUIVALENCE groups, and no COMMON blocks — the safest candidates
  for direct migration.
- The variable density top-5 counts only non-PARAMETER declarations
  (`Es_Parametro != SI` in `simbolos_variables.csv`).
- `estadisticas_por_archivo.csv` is not affected by the E4 optional sources.
