# sloc.py

## Purpose

Precise SLOC (Source Lines of Code) counting per program unit. Classifies
every physical line as blank, comment, code, or continuation, then aggregates
counts per unit using scope resolution.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CARPETA_CODIGO` | `FORT_SRC` env var → `../athys/mercedes/` | Path to the Fortran source directory |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_sloc.csv"` | Output file |

---

## Inputs

- Fortran source files in `CARPETA_CODIGO`
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`)

---

## Output: `<FORT_OUT>/reporte_sloc.csv`

One row per program unit, sorted by `SLOC_neto` descending.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `LOC` | Total physical lines in the unit's line range |
| `N_Blancos` | Blank physical lines |
| `N_Comentarios` | Comment-only physical lines |
| `N_Continuacion` | Continuation lines (2nd, 3rd… physical line of a multi-line statement) |
| `SLOC_fisico` | `LOC - N_Blancos - N_Comentarios` (lines with actual code, including continuations) |
| `SLOC_neto` | `SLOC_fisico - N_Continuacion` (logical statements only) |
| `Pct_Comentario` | `N_Comentarios / LOC × 100` |

---

## Line Classification

Uses `reader_logical.py` to obtain `LogicalLine` objects, then works backwards
from the `raw_lines` field of each logical line:

| Category | Condition |
| :--- | :--- |
| `COMMENT` | `LogicalLine.is_comment = True` |
| `BLANK` | Not a comment, and `LogicalLine.text` is empty/whitespace |
| `CODE` | First physical line of a non-comment, non-blank logical line |
| `CONTINUATION` | 2nd, 3rd, … physical line of a multi-line statement |

---

## Derived Metrics

**SLOC_neto** equals the number of logical statements in the unit. This is
the most accurate size measure for comparing units, since it is independent
of coding style (how many continuation lines are used per statement).

**Pct_Comentario** measures documentation density. Values below 5% on units
with more than 50 logical statements indicate poorly documented code.

**CC_SLOC** (in `reporte_consolidado.csv`) = `CC / SLOC_neto`. Measures
cyclomatic complexity density — how many decision points exist per logical
statement. More useful than raw CC for comparing units of different sizes.
