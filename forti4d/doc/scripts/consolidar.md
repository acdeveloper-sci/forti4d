# consolidar.py

## Purpose

Joins all per-unit reports into a single CSV with one row per unit and
34 columns. Must run after all other analysis scripts. Also adds the
derived metric `CC_SLOC`.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTARIO` | `RUTA_RESULTADOS / "reporte_inventario.csv"` | Base — defines the row set |
| `SLOC` | `RUTA_RESULTADOS / "reporte_sloc.csv"` | Size and comment density |
| `COMPLEJIDAD` | `RUTA_RESULTADOS / "reporte_complejidad.csv"` | McCabe CC |
| `IMPACTO` | `RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"` | Fan-In / Fan-Out |
| `DENSIDAD` | `RUTA_RESULTADOS / "reporte_densidad.csv"` | Statement density profiles |
| `ALCANZ` | `RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"` | Reachability status |
| `COMMON_USO` | `RUTA_RESULTADOS / "common_uso.csv"` | COMMON block usage |
| `SIMB_VARS` | `RUTA_RESULTADOS / "simbolos_variables.csv"` | Variable and constant declarations |
| `SIMB_FIRMAS` | `RUTA_RESULTADOS / "simbolos_firmas.csv"` | Formal arguments per unit |
| `SIMB_IMPL` | `RUTA_RESULTADOS / "simbolos_implicit.csv"` | IMPLICIT rules per unit |
| `TIPOS_DEF` | `RUTA_RESULTADOS / "tipos_definicion.csv"` | Derived TYPE definitions |
| `EQUIV_CSV` | `RUTA_RESULTADOS / "equivalencias.csv"` | EQUIVALENCE aliasing groups |
| `RUTA_AUDIT` | `RUTA_RESULTADOS / "audit"` | Directory of `*_DEBUG.csv` files (for DATA/ENTRY counts) |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_consolidado.csv"` | Output |

All sources except `INVENTARIO` are optional — missing files produce empty
values for their columns without stopping the script.

---

## Inputs

All reports listed in the configuration table above.

---

## Output: `<FORT_OUT>/reporte_consolidado.csv`

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
| `N_Vars_Locales` | simbolos_variables | Count of declared variables (non-PARAMETER) |
| `N_Params` | simbolos_variables | Count of PARAMETER constants |
| `N_Args_Formales` | simbolos_firmas | Count of formal arguments (0 for non-callable units) |
| `Implicit_None` | simbolos_implicit | `SI` if unit has `IMPLICIT NONE`; `NO` if has rules; empty if no IMPLICIT statement |
| `N_Tipos_Derivados` | tipos_definicion | Count of derived TYPE definitions hosted in this unit |
| `Tiene_Equiv` | equivalencias | `SI` if the unit has any EQUIVALENCE aliasing groups, `NO` otherwise |
| `N_Grupos_Equiv` | equivalencias | Number of distinct aliasing groups in the unit |
| `N_Data_Stmts` | audit CSVs | Count of DATA statements in the unit |
| `N_Entry_Stmts` | audit CSVs | Count of ENTRY statements in the unit |
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
- Symbol sources (`SIMB_VARS`, `SIMB_FIRMAS`, `SIMB_IMPL`, `TIPOS_DEF`,
  `EQUIV_CSV`) may contain multiple rows per unit and are aggregated into
  summary counts. These sources require `simbolos`, `tipos_derivados`, and
  `equivalencias` to have run first.
- `N_Data_Stmts` and `N_Entry_Stmts` are computed by scanning
  `audit/*_DEBUG.csv` directly using scope resolution (innermost unit
  whose `[Linea_Inicio, Linea_Fin]` range contains the statement line).
  The `audit/` directory must be present (produced by `perfilador.py`).
  If missing, both columns default to 0.
- `reporte_clones.csv` (produced by `clones.py`) is not currently joined here.
  Clone state per unit is read directly by `priorizacion.py`. A future
  integration could add `Estado_Clon` and `N_Copias` columns to this report.
