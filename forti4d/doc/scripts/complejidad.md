# complejidad.py

## Purpose

Computes McCabe cyclomatic complexity (CC) per program unit by counting
decision points from the `audit/*_DEBUG.csv` files produced by `perfilador.py`.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `RUTA_AUDIT` | `RUTA_RESULTADOS / "audit"` | Directory containing `*_DEBUG.csv` files |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_complejidad.csv"` | Output file |

---

## Inputs

- `<FORT_OUT>/audit/<filename>_DEBUG.csv` for each source file
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`)

---

## Output: `<FORT_OUT>/reporte_complejidad.csv`

One row per program unit, sorted by CC descending.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `CC` | McCabe cyclomatic complexity |
| `Interpretacion` | Complexity level: `BAJA`, `MEDIA`, `ALTA`, `CRITICA` |
| `Linea_Inicio` | First line of the unit |
| `Linea_Fin` | Last line of the unit |
| `Lineas_Total` | Physical line count of the unit |

---

## CC Calculation

CC = 1 + (number of decision points in the unit)

**Decision point rules:**

| Statement kind | Count |
| :--- | :--- |
| `IF_CONSTRUCT` | +1 (block IF and single-line IF) |
| `ELSE_STMT` | +1 only if `ELSE IF` / `ELSEIF`; plain `ELSE` = 0 |
| `DO_CONSTRUCT` | +1 |
| `SELECT_CONSTRUCT` | 0 (branches counted via CASE) |
| `CASE_STMT` | +1 unless `CASE DEFAULT` or `CLASS DEFAULT` |
| `WHERE_CONSTRUCT` | +1 |
| `FORALL_CONSTRUCT` | +1 |

---

## Complexity Scale

| Level | CC range | Meaning |
| :--- | :--- | :--- |
| `BAJA` | 1 – 10 | Simple, easy to test |
| `MEDIA` | 11 – 20 | Moderate complexity |
| `ALTA` | 21 – 50 | High complexity, refactoring recommended |
| `CRITICA` | > 50 | Very high risk, hard to maintain |

---

## Notes

- Scope resolution assigns each decision point to the innermost unit whose
  `[Linea_Inicio, Linea_Fin]` range contains the statement's line number.
- CC is computed from `<FORT_OUT>/audit/` DEBUG files, not directly from source.
  `perfilador.py` must be run first.
