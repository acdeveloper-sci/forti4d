# consolidar.py

## Purpose

Joins all per-unit reports into a single CSV with one row per unit and
25 columns. Must run after all other analysis scripts. Also adds the
derived metric `CC_SLOC`.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTARIO` | `"reporte_inventario.csv"` | Base — defines the row set |
| `SLOC` | `"reporte_sloc.csv"` | Size and comment density |
| `COMPLEJIDAD` | `"reporte_complejidad.csv"` | McCabe CC |
| `IMPACTO` | `"dep_03_matriz_impacto.csv"` | Fan-In / Fan-Out |
| `DENSIDAD` | `"reporte_densidad.csv"` | Statement density profiles |
| `ALCANZ` | `"reporte_alcanzabilidad.csv"` | Reachability status |
| `COMMON_USO` | `"common_uso.csv"` | COMMON block usage |
| `SALIDA_CSV` | `"reporte_consolidado.csv"` | Output |

All sources except `INVENTARIO` are optional — missing files produce empty
values for their columns without stopping the script.

---

## Inputs

All reports listed in the configuration table above.

---

## Output: `reporte_consolidado.csv`

One row per program unit, sorted alphabetically by `Archivo` then `Unidad`.

| Column | Source | Description |
| :--- | :--- | :--- |
| `Archivo` | inventario | Source file name |
| `Unidad` | inventario | Unit name |
| `Tipo` | inventario | Unit type |
| `Padre` | inventario | Parent unit or `GLOBAL` |
| `LOC` | sloc | Physical line count |
| `SLOC_fisico` | sloc | LOC minus blanks and comments |
| `SLOC_neto` | sloc | Logical statements only |
| `N_Comentarios` | sloc | Comment line count |
| `N_Continuacion` | sloc | Continuation line count |
| `Pct_Comentario` | sloc | Comment density % |
| `CC` | complejidad | McCabe cyclomatic complexity |
| `CC_Nivel` | complejidad | `BAJA` / `MEDIA` / `ALTA` / `CRITICA` |
| `CC_SLOC` | derived | `CC / SLOC_neto` — complexity per logical statement |
| `Fan_In` | impacto | Number of callers |
| `Fan_Out` | impacto | Number of callees |
| `Pct_Calculo` | densidad | % calculation statements |
| `Pct_Control` | densidad | % control-flow statements |
| `Pct_IO` | densidad | % I/O statements |
| `Pct_Legacy` | densidad | % legacy statements |
| `N_Common_Bloques` | common_uso | Number of distinct COMMON blocks used |
| `Common_Bloques` | common_uso | Semicolon-separated block names |
| `Estado` | alcanzabilidad | `ENTRADA` / `ALCANZABLE` / `NO_ALCANZABLE` |
| `Via_Entradas` | alcanzabilidad | Entry points that reach this unit |
| `Legacy_Flags` | inventario | Legacy constructs detected (from inventory) |
| `IO_Flags` | inventario | I/O statements detected (from inventory) |

---

## Notes

- The join key is `(Archivo, Unidad)`. The inventory defines which rows exist;
  all other sources are left-joined against it.
- `CC_SLOC = 0` when `SLOC_neto = 0` (avoids division by zero).
- `COMMON_USO` may contain multiple rows per unit (one per block). These are
  aggregated: `N_Common_Bloques` = count of distinct blocks, `Common_Bloques`
  = sorted semicolon-separated names.
