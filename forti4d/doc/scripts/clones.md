# clones.py

## Purpose

Detects whether same-named units across multiple files are identical copies,
similar variants, or fully diverged independent implementations.

Reads the duplicate-unit list from `dep_00_ambiguedades.csv`, extracts and
normalizes the source of each unit instance, and performs pairwise comparison
using `difflib.SequenceMatcher`.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `AMBIGUEDADES` | `RUTA_RESULTADOS / "dep_00_ambiguedades.csv"` | Input: duplicate unit list |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_clones.csv"` | Output |
| `UMBRAL_SIMILAR` | `0.80` | Similarity ratio threshold for `SIMILAR` vs `DIVERGIDO` |

---

## Inputs

- `<FORT_OUT>/dep_00_ambiguedades.csv` (from `dependencias.py`)
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`)
- Fortran source files in `CARPETA_CODIGO`

---

## Output: `<FORT_OUT>/reporte_clones.csv`

One row per pair of same-named units. Groups with N copies produce N×(N-1)/2
rows (e.g. 3 copies → 3 pairs).

| Column | Description |
| :--- | :--- |
| `Nombre` | Unit name |
| `Tipo` | Unit type |
| `Archivo_A` | First file |
| `Archivo_B` | Second file |
| `SLOC_A` | Normalized line count of unit in Archivo_A |
| `SLOC_B` | Normalized line count of unit in Archivo_B |
| `Similitud_Pct` | Similarity percentage (0–100) |
| `Estado` | `IDENTICO`, `SIMILAR`, or `DIVERGIDO` |

Rows are sorted: `DIVERGIDO` first, then `SIMILAR`, then `IDENTICO`.

---

## Classification

| Estado | Condition |
| :--- | :--- |
| `IDENTICO` | Similarity ratio = 1.00 (byte-for-byte identical after normalization) |
| `SIMILAR` | Ratio ≥ `UMBRAL_SIMILAR` (default 0.80) |
| `DIVERGIDO` | Ratio < `UMBRAL_SIMILAR` |

---

## Normalization

Before comparison, each unit's source is normalized:

1. Logical lines outside `[Linea_Inicio, Linea_Fin]` are excluded.
2. Comment lines and blank lines are removed.
3. Each remaining line is uppercased and whitespace-collapsed to a single space.

This makes the comparison insensitive to formatting differences, comment
additions, and case conventions while preserving structural differences.

---

## Notes

- Requires `dependencias.py` and `inventario.py` to have been run first.
- If `dep_00_ambiguedades.csv` is empty (no duplicate names in the corpus),
  `reporte_clones.csv` is written with headers only.
- `reporte_clones.csv` is consumed by `priorizacion.py` to compute the clone
  penalty component of the risk score.
