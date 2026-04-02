# visual_graph.py

## Purpose

Generates Graphviz DOT files for visual exploration of the call graph.
Supports a full corpus view or filtered subgraphs scoped to one or more
entry points (executables).

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `GRAPH_CSV` | `RESULTS_PATH / "dep_02_unit_graph.csv"` | Input: call graph edges |
| `CONSOL_PATH` | `RESULTS_PATH / "report_consolidated.csv"` | Input: node metadata |

---

## Inputs

- `<FORT_OUT>/dep_02_unit_graph.csv`
- `<FORT_OUT>/report_consolidated.csv`

---

## Usage

> **Note:** `visual_graph.py` accepts command-line arguments (`--list`, `--entry`, `--use`)
> that are not yet supported through the `forti4d` CLI. Run it directly via:
> ```bash
> python -m forti4d.analyzers.visual_graph [options]
> ```
> CLI integration is planned for a future release.

```bash
# List available entry points
python -m forti4d.analyzers.visual_graph --list

# Full corpus graph (all entry points, all edges)
python -m forti4d.analyzers.visual_graph

# Subgraph for a single executable
python -m forti4d.analyzers.visual_graph --entry mcdes

# Subgraph for multiple executables
# (nodes reachable from more than one EP are highlighted in yellow)
python -m forti4d.analyzers.visual_graph --entry util0 util1 util2

# Include USE (module import) edges — omitted by default
python -m forti4d.analyzers.visual_graph --entry mcdes --use
```

---

## Outputs

| File | Generated when |
| :--- | :--- |
| `<FORT_OUT>/graph_complete.dot` | No `--entry` flag (all nodes, all edges including USE) |
| `<FORT_OUT>/graph_simple.dot` | No `--entry` flag (reachable nodes only, CALL + FUNC_CALL only) |
| `<FORT_OUT>/graph_<names>.dot` | `--entry` specified — one file named after the selected entry points |

---

## Rendering (requires Graphviz)

```bash
dot -Tpng results/graph_mcdes.dot      -o results/graph_mcdes.png
dot -Tsvg results/graph_complete.dot   -o results/graph_complete.svg
dot -Tpdf results/graph_simple.dot     -o results/graph_simple.pdf
```

---

## Visual Conventions

### Node color (by reachability status)

| Color | Status |
| :--- | :--- |
| Blue `#4472C4` | Entry point (PROGRAM / IMPLICIT-MAIN) |
| Green `#70AD47` | Reachable unit |
| Grey `#A6A6A6` | Dead code (UNREACHABLE) |
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

`dep_02_unit_graph.csv` stores IMPLICIT-MAIN origins as `MAIN__<filename>`
(e.g. `MAIN__chcump.f90`). `visual_graph.py` resolves these to the
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
