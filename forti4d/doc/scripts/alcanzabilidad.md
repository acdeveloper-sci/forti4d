# alcanzabilidad.py

## Purpose

Dead code detection via BFS from all entry points. Traverses the call graph
starting from every PROGRAM and IMPLICIT-MAIN unit and classifies each unit
as reachable, unreachable, or an entry point itself.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `GRAFO_CSV` | `RUTA_RESULTADOS / "dep_02_grafo_unidades.csv"` | Input: resolved call graph |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"` | Output |

---

## Inputs

- `<FORT_OUT>/dep_02_grafo_unidades.csv`
- `<FORT_OUT>/reporte_inventario.csv` (via `cargar_inventario()`)

---

## Output: `<FORT_OUT>/reporte_alcanzabilidad.csv`

One row per program unit.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `Padre` | Parent unit name, or `GLOBAL` |
| `Estado` | `ENTRADA`, `ALCANZABLE`, or `NO_ALCANZABLE` |
| `Via_Entradas` | Semicolon-separated list of entry points that reach this unit |
| `Razon` | Explanation when `Estado = NO_ALCANZABLE` |

---

## States

| State | Meaning |
| :--- | :--- |
| `ENTRADA` | The unit is itself an entry point (PROGRAM or IMPLICIT-MAIN) |
| `ALCANZABLE` | Reachable from at least one entry point via CALL, USE, or FUNC_CALL edges |
| `NO_ALCANZABLE` | Not reachable from any entry point — dead code candidate |

---

## Transitivity Rules

- A unit inside a module (`Padre ≠ GLOBAL`) is considered reachable if its
  parent module is reachable.
- A unit inside an entry point is considered reachable directly.

---

## MAIN__ Node Resolution

`dependencias.py` represents IMPLICIT-MAIN units in the call graph as
`MAIN__<filename>` (e.g. `MAIN__chcump.f90`). `alcanzabilidad.py` resolves
these back to the inventory unit name (`chcump`) using the `Archivo` field
of the inventory, so the output always shows the human-readable name.

---

## Notes

- The BFS follows all three edge types: `CALL`, `USE`, and `FUNC_CALL`.
- A corpus with multiple executables (several PROGRAM / IMPLICIT-MAIN files
  in the same directory) will have multiple independent BFS roots. A unit
  is `ALCANZABLE` if reachable from *any* of them.
- `<FORT_OUT>/reporte_alcanzabilidad.csv` is consumed by `consolidar.py` and
  `grafo_visual.py`.
