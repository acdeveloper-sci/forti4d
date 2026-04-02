# reachability.py

## Purpose

Dead code detection via BFS from all entry points. Traverses the call graph
starting from every PROGRAM and IMPLICIT-MAIN unit and classifies each unit
as reachable, unreachable, or an entry point itself.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `GRAPH_CSV` | `RESULTS_PATH / "dep_02_unit_graph.csv"` | Input: resolved call graph |
| `OUTPUT_CSV` | `RESULTS_PATH / "report_reachability.csv"` | Output |

---

## Inputs

- `<FORT_OUT>/dep_02_unit_graph.csv`
- `<FORT_OUT>/inventory_report.csv` (via `load_inventory()`)

---

## Output: `<FORT_OUT>/report_reachability.csv`

One row per program unit.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Unit` | Unit name |
| `Type` | Unit type |
| `Parent` | Parent unit name, or `GLOBAL` |
| `Status` | `ENTRY_POINT`, `REACHABLE`, or `UNREACHABLE` |
| `Via_Entry_Points` | Semicolon-separated list of entry points that reach this unit |
| `Reason` | Explanation when `Status = UNREACHABLE` |

---

## States

| State | Meaning |
| :--- | :--- |
| `ENTRY_POINT` | The unit is itself an entry point (PROGRAM or IMPLICIT-MAIN) |
| `REACHABLE` | Reachable from at least one entry point via CALL, USE, or FUNC_CALL edges |
| `UNREACHABLE` | Not reachable from any entry point — dead code candidate |

---

## Transitivity Rules

- A unit inside a module (`Parent ≠ GLOBAL`) is considered reachable if its
  parent module is reachable.
- A unit inside an entry point is considered reachable directly.

---

## MAIN__ Node Resolution

`dependencies.py` represents IMPLICIT-MAIN units in the call graph as
`MAIN__<filename>` (e.g. `MAIN__solver_main.f90`). `reachability.py` resolves
these back to the inventory unit name using the `File` field of the inventory,
so the output always shows the human-readable name.

---

## Notes

- The BFS follows all three edge types: `CALL`, `USE`, and `FUNC_CALL`.
- A corpus with multiple executables (several PROGRAM / IMPLICIT-MAIN files
  in the same directory) will have multiple independent BFS roots. A unit
  is `REACHABLE` if reachable from *any* of them.
- `report_reachability.csv` is consumed by `consolidate.py` and
  `visual_graph.py`.
