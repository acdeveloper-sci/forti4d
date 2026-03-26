# reporte_html.py

## Purpose

Generates a self-contained HTML report from `reporte_priorizacion.csv`.
The output is a single `.html` file with inline CSS and JavaScript — no
external dependencies, no internet connection required to view it.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `PRIORIDAD_CSV` | `RUTA_RESULTADOS / "reporte_priorizacion.csv"` | Input |
| `SALIDA_HTML` | `RUTA_RESULTADOS / "reporte.html"` | Output |

---

## Inputs

- `<FORT_OUT>/reporte_priorizacion.csv` (required)

---

## Output: `<FORT_OUT>/reporte.html`

Single self-contained HTML file. Sections:

1. **Header** — project title, generation date and time, total unit count
2. **Priority summary** — one card per tier (CRITICA / ALTA / MEDIA / BAJA /
   DEAD_CODE / TOTAL) showing count and percentage
3. **Main table** — all units from `reporte_priorizacion.csv`, with:
   - Color-coded `Prioridad` badge per row
   - Filter buttons to show only one priority tier
   - Click-to-sort on every column header (numeric-aware)

### Visible columns

| Column | Source field |
| :--- | :--- |
| Prioridad | `Prioridad` |
| Score | `Score` |
| Archivo | `Archivo` |
| Unidad | `Unidad` |
| Tipo | `Tipo` |
| CC | `CC` |
| Fan-In | `Fan_In` |
| Pct_Legacy | `Pct_Legacy` |
| Alcanzabilidad | `Estado_Alcanz` |
| Estrategia | `Estrategia` |
| Impl.None | `Implicit_None` |
| Equiv | `Tiene_Equiv` |

---

## Notes

- No third-party Python packages required — standard library only.
- No external CSS frameworks or JavaScript libraries — the HTML file
  is fully standalone.
- Priority tier colors: CRITICA=red, ALTA=orange, MEDIA=yellow,
  BAJA=green, DEAD_CODE=grey.
- The sort is stable within equal values; numeric columns sort
  numerically, text columns sort lexicographically.
