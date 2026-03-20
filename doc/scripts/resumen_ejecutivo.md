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
| `OUT_MD` | `RUTA_RESULTADOS / "RESUMEN_PROYECTO.md"` | Output: Markdown summary |
| `OUT_CSV` | `RUTA_RESULTADOS / "estadisticas_por_archivo.csv"` | Output: per-file statistics |

---

## Inputs

- `<FORT_OUT>/reporte_inventario.csv`
- `<FORT_OUT>/dep_03_matriz_impacto.csv`

---

## Outputs

### `<FORT_OUT>/RESUMEN_PROYECTO.md`

Markdown document with the following sections:

1. **Global Metrics** — total files, LOC, units, average LOC per file
2. **Unit Type Distribution** — count and % per type
3. **Top 10 Largest Files** — sorted by LOC, with unit count and types
4. **Health Indicators (Legacy)** — units with legacy constructs and I/O,
   with frequency tables for each construct type
5. **Critical Units (highest Fan-In)** — top 15 most reused units
6. **Orchestrating Units (highest Fan-Out)** — top 15 units with most dependencies

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
