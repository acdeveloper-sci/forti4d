# grafo_visual.py

## Purpose

Generates Graphviz DOT files for visual exploration of the call graph.
Supports a full corpus view or filtered subgraphs scoped to one or more
entry points (executables).

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `GRAFO_CSV` | `"dep_02_grafo_unidades.csv"` | Input: call graph edges |
| `CONSOLIDADO` | `"reporte_consolidado.csv"` | Input: node metadata |

---

## Inputs

- `dep_02_grafo_unidades.csv`
- `reporte_consolidado.csv`

---

## Usage

```bash
# List available entry points
python grafo_visual.py --list

# Full corpus graph (all entry points, all edges)
python grafo_visual.py

# Subgraph for a single executable
python grafo_visual.py --entry mcdes

# Subgraph for multiple executables
# (nodes reachable from more than one EP are highlighted in yellow)
python grafo_visual.py --entry util0 util1 util2

# Include USE (module import) edges — omitted by default
python grafo_visual.py --entry mcdes --use
```

---

## Outputs

| File | Generated when |
| :--- | :--- |
| `grafo_completo.dot` | No `--entry` flag (all nodes, all edges including USE) |
| `grafo_simple.dot` | No `--entry` flag (reachable nodes only, CALL + FUNC_CALL only) |
| `grafo_<names>.dot` | `--entry` specified — one file named after the selected entry points |

---

## Rendering (requires Graphviz)

```bash
dot -Tpng grafo_mcdes.dot    -o grafo_mcdes.png
dot -Tsvg grafo_completo.dot -o grafo_completo.svg
dot -Tpdf grafo_simple.dot   -o grafo_simple.pdf
```

---

## Visual Conventions

### Node color (by reachability status)

| Color | Status |
| :--- | :--- |
| Blue `#4472C4` | Entry point (PROGRAM / IMPLICIT-MAIN) |
| Green `#70AD47` | Reachable unit |
| Grey `#A6A6A6` | Dead code (NO_ALCANZABLE) |
| Yellow `#FFD966` | Reachable from multiple selected entry points (multi-`--entry` only) |

### Node shape (by unit type)

| Shape | Type |
| :--- | :--- |
| `doubleoctagon` | PROGRAM, IMPLICIT-MAIN |
| `hexagon` | MODULE |
| `ellipse` | FUNCTION |
| `diamond` | BLOCK_DATA |
| `box` | SUBROUTINE (and default) |

### Edge style (by dependency type)

| Style | Type |
| :--- | :--- |
| Solid black | CALL |
| Solid green | FUNC_CALL |
| Dashed blue | USE (module import) |

### Node label

Each node displays: `unit_name`, `CC=<value>`, `Fi=<Fan_In>` (when available).

### Clusters

Nodes are grouped into subgraphs by source file.

---

## MAIN__ Node Resolution

`dep_02_grafo_unidades.csv` stores IMPLICIT-MAIN origins as `MAIN__<filename>`
(e.g. `MAIN__chcump.f90`). `grafo_visual.py` resolves these to the
inventory unit name (`chcump`) for display.

---

## Notes

- When `--entry` is used, only nodes reachable from the selected entry points
  via BFS are included. This produces a subgraph corresponding to the
  transitive dependencies of a single executable.
- Entry point names are matched case-insensitively. Use `--list` to see
  the exact names available in the current corpus.
- The `--use` flag includes module USE edges, which can make large graphs
  significantly denser. Recommended for targeted subgraphs, not for the
  full corpus view.
