# perfilador.py

## Purpose

Classifies every logical statement in every source file and computes statement
density profiles per unit. Also produces the `audit/` DEBUG files, which are
the primary intermediate artifact consumed by `complejidad.py`,
`common_blocks.py`, and — as a diagnostic tool — `analisis_bloques_v8.py`.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CARPETA_CODIGO` | from `inventario.py` | Path to the Fortran source directory |
| `SALIDA_CSV` | `"reporte_densidad.csv"` | Density profile output |
| `RUTA_AUDIT` | `"audit/"` | Directory for per-file DEBUG files |

> **Note:** `audit/` is currently written relative to `src/`. In `results/`,
> the directory is at `results/audit/`. Migration of output paths to `results/`
> is planned.

---

## Inputs

- `reporte_inventario.csv`
- Fortran source files in `CARPETA_CODIGO`

---

## Outputs

### `reporte_densidad.csv`
One row per program unit.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `Total_Sentencias` | Total classified statements in this unit |
| `Total_Calculo` | Statements in the calculation group |
| `Total_Control` | Statements in the control-flow group |
| `Total_IO` | Statements in the I/O group |
| `Total_Legacy` | Statements in the legacy group |
| `Total_Declar` | Statements in the declaration group |
| `Pct_Calculo` | `Total_Calculo / Total_Sentencias × 100` |
| `Pct_Control` | `Total_Control / Total_Sentencias × 100` |
| `Pct_IO` | `Total_IO / Total_Sentencias × 100` |
| `Pct_Legacy` | `Total_Legacy / Total_Sentencias × 100` |
| `Pct_Declar` | `Total_Declar / Total_Sentencias × 100` |
| `N_Common` | Count of COMMON statements |
| `N_Equiv` | Count of EQUIVALENCE statements |
| `N_Print` | Count of PRINT statements |
| `N_Write` | Count of WRITE statements |

### `audit/<filename>_DEBUG.csv`
One file per source file. One row per logical line.

| Column | Description |
| :--- | :--- |
| `Linea` | Physical start line number |
| `Kind` | Statement kind (e.g. `IF_CONSTRUCT`, `DO_CONSTRUCT`, `ASSIGNMENT_STMT`, `COMMON_STMT`, `IO_STMT`, `COMMENT`, …) |
| `Contenido` | First 120 characters of the logical line text |

---

## Statement Groups

| Group | Kinds included |
| :--- | :--- |
| `CALCULO` | `ASSIGNMENT_STMT` + calculation actions (ALLOCATE, DEALLOCATE, POINTER_ACTION, …) |
| `CONTROL` | `IF_CONSTRUCT`, `DO_CONSTRUCT`, `SELECT_CONSTRUCT`, `ASSOCIATE_CONSTRUCT`, `WHERE_CONSTRUCT`, `FORALL_CONSTRUCT`, `CONTROL_STMT`, `ELSE_STMT`, `CASE_STMT` |
| `IO` | `IO_STMT` |
| `LEGACY` | `COMMON_STMT`, `EQUIVALENCE_STMT`, `DATA_STMT`, `NAMELIST_STMT` |
| `DECLAR` | `VAR_DECLARATION`, `PARAMETER_STMT`, `IMPLICIT_STMT`, `USE_STMT`, `IMPORT_STMT`, `TYPE_DEFINITION`, `ENUM_DEF`, `INTERFACE_BLOCK`, `CONTAINS_STMT`, `END_BLOCK_STMT` |

---

## Notes

- Statement classification uses `patterns_v2.py` regex patterns applied to
  each logical line after masking string literals to avoid false positives.
- Scope resolution assigns each statement to the innermost unit whose line
  range contains the statement's start line.
- The `audit/` directory is created automatically if it does not exist.
