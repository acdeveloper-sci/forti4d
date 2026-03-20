# resumen_ejecutivo.py

## Purpose

Produces a high-level executive summary of the corpus: global metrics, type
distribution, largest files, legacy/I/O health indicators, and the most
critical and most orchestrating units.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTARIO` | `"reporte_inventario.csv"` | Input: unit inventory |
| `DEPENDENCIAS` | `"dep_03_matriz_impacto.csv"` | Input: Fan-In / Fan-Out |
| `OUT_MD` | `"RESUMEN_PROYECTO.md"` | Output: Markdown summary |
| `OUT_CSV` | `"estadisticas_por_archivo.csv"` | Output: per-file statistics |

---

## Inputs

- `reporte_inventario.csv`
- `dep_03_matriz_impacto.csv`

---

## Outputs

### `RESUMEN_PROYECTO.md`

Markdown document with the following sections:

1. **Global Metrics** — total files, LOC, units, average LOC per file
2. **Unit Type Distribution** — count and % per type
3. **Top 10 Largest Files** — sorted by LOC, with unit count and types
4. **Health Indicators (Legacy)** — units with legacy constructs and I/O,
   with frequency tables for each construct type
5. **Critical Units (highest Fan-In)** — top 15 most reused units
6. **Orchestrating Units (highest Fan-Out)** — top 15 units with most dependencies

### `estadisticas_por_archivo.csv`

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
