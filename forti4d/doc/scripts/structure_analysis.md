# structure_analysis.py

## Purpose

Classifies each source file into an architectural role based on its Fan-In
and Fan-Out profile from the call graph.

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `IMPACT_FILE` | `RESULTS_PATH / "dep_03_impact_matrix.csv"` | Input: Fan-In/Fan-Out per unit |
| `INVENTORY_FILE` | `RESULTS_PATH / "inventory_report.csv"` | Input: unit types (to detect IMPLICIT-MAIN) |
| `OUTPUT_FILE` | `RESULTS_PATH / "report_structure_analysis.csv"` | Output |
| `CRITICAL_THRESHOLD` | `10` | Min Fan-In to classify a file as `CRITICAL_NODE` |

---

## Inputs

- `<FORT_OUT>/dep_03_impact_matrix.csv`
- `<FORT_OUT>/inventory_report.csv`

---

## Output: `<FORT_OUT>/report_structure_analysis.csv`

One row per source file.

| Column | Description |
| :--- | :--- |
| `File` | Source file name |
| `Category` | Architectural role (see below) |
| `Fan_In_Max` | Maximum Fan-In across all units in the file |
| `Unit_Max_In` | Unit with the highest Fan-In |
| `Fan_Out_Max` | Maximum Fan-Out across all units in the file |
| `Unit_Max_Out` | Unit with the highest Fan-Out |
| `Total_Units` | Number of units in the file |
| `Has_Main` | `YES` if the file contains a PROGRAM or IMPLICIT-MAIN unit |
| `Detail` | Human-readable explanation of the classification |

---

## Categories

Assigned in priority order (first matching rule wins):

| Category | Condition | Meaning |
| :--- | :--- | :--- |
| `ENTRY_POINT` | File contains an IMPLICIT-MAIN unit | Compiles to an executable |
| `ISLAND` | Fan-In = 0 and Fan-Out = 0 | No connections — potential dead code |
| `CRITICAL_NODE` | Max Fan-In ≥ `CRITICAL_THRESHOLD` (10) | High reuse — core library unit |
| `ORCHESTRATOR` | Max Fan-Out ≥ `CRITICAL_THRESHOLD` (10) | Coordinates many dependencies |
| `WORKER` | Connected but Fan-Out < 5 | Service or calculation routine |
| `MIXED` | All other cases | Standard functionality |

> **Note:** The category scheme (CRITICAL_NODE, ORCHESTRATOR, WORKER, ISLAND,
> MIXED) and classification rules are project-defined heuristics based on
> Fan-In/Fan-Out thresholds. The categories are inspired by common software
> architecture patterns but are not derived from a published standard.

---

## Notes

- Files present in `inventory_report.csv` but absent from `dep_03` (no
  call graph entries) are automatically classified as `ISLAND`.
- Output is sorted by category priority:
  `CRITICAL_NODE` → `ORCHESTRATOR` → `ENTRY_POINT` → `MIXED` → `WORKER` → `ISLAND`.
- `CRITICAL_THRESHOLD` is hardcoded (empirical value). It is a candidate for
  a future `FORT_CRITICAL_THRESHOLD` env var or `--critical-threshold` CLI flag.
