# dependencies.py

## Purpose

Builds the call graph of the corpus. Resolves CALL, USE, and function-call
references between units. Computes Fan-In and Fan-Out per unit. Identifies
units defined in multiple files (ambiguities) and external references with
no known definition (orphans).

---

## Configuration

All paths are resolved under `RESULTS_PATH`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `INVENTORY_FILE` | `RESULTS_PATH / "inventory_report.csv"` | Input: unit inventory |
| `AMBIGUITIES_OUT` | `RESULTS_PATH / "dep_00_ambiguities.csv"` | Units with the same name in multiple files |
| `MASTER_OUT` | `RESULTS_PATH / "dep_01_master_data.csv"` | All resolved call/use relationships |
| `GRAPH_OUT` | `RESULTS_PATH / "dep_02_unit_graph.csv"` | Resolved call graph edges |
| `IMPACT_OUT` | `RESULTS_PATH / "dep_03_impact_matrix.csv"` | Fan-In and Fan-Out per unit |
| `ORPHANS_OUT` | `RESULTS_PATH / "dep_04_external_orphans.csv"` | References with no known definition |
| `DEPENDS_OUT` | `RESULTS_PATH / "dep_05_file_dependencies.csv"` | File-level dependency summary |
| `INCLUDES_OUT` | `RESULTS_PATH / "dep_06_include_files.csv"` | Explicit INCLUDE file references |

---

## Inputs

- `<FORT_OUT>/inventory_report.csv`
- Fortran source files in `CODE_PATH`

---

## Outputs

### `dep_00_ambiguities.csv`
Units with the same name defined in more than one source file. Always written
(headers only if no ambiguities exist) so downstream steps can distinguish
"dependencies ran, no duplicates found" from "dependencies never ran".

| Column | Description |
| :--- | :--- |
| `Unit_Name` | Unit name |
| `Type` | Unit type |
| `Count` | Number of files where this name is defined |
| `File_List` | Semicolon-separated list of those files |

### `dep_01_master_data.csv`
All detected call/use relationships before resolution. Always written (headers
only when no dependencies are found).

### `dep_02_unit_graph.csv`
Resolved call graph. One row per directed edge. Always written (headers only
when no resolved edges exist — e.g. a pure library corpus with no cross-file
dependencies).

| Column | Description |
| :--- | :--- |
| `Source_Unit` | Calling unit. IMPLICIT-MAIN units appear as `MAIN__<filename>` |
| `Source_Type` | Type of the calling unit |
| `Target_Unit` | Called/used unit |
| `Target_Type` | Type of the called unit |
| `Dep_Type` | Edge type: `CALL`, `USE`, or `FUNC_CALL` |
| `Target_File` | Source file(s) of the destination unit |
| `Weight` | Number of times this dependency appears in the calling unit |

### `dep_03_impact_matrix.csv`
Fan-In and Fan-Out per unit. Always written (headers only when no resolved
dependencies exist).

| Column | Description |
| :--- | :--- |
| `Unit` | Unit name |
| `Type` | Unit type |
| `File` | Source file |
| `Fan_In` | Number of units that call/use this unit |
| `Fan_Out` | Number of distinct units this unit calls/uses |

### `dep_04_external_orphans.csv`
References found in source code with no matching definition in the corpus
(external library calls, unresolved symbols). Always written (headers only when
all references are resolved internally).

### `dep_05_file_dependencies.csv`
Aggregated dependency summary at file level. Always written (headers only when
all units reside in a single file or have no cross-file dependencies).

### `dep_06_include_files.csv`
Explicit INCLUDE file references — one row per unique `(Source_File, Source_Unit, Included_File)` triple.
Always written (headers only when no INCLUDE directives are found).

| Column | Description |
| :--- | :--- |
| `Source_File` | Source file containing the INCLUDE statement |
| `Source_Unit` | Unit (scope) in which the INCLUDE appears |
| `Included_File` | Filename referenced by the INCLUDE directive |
| `Status` | `PRESENT` if the file exists in `CODE_PATH`; `MISSING` otherwise |

Duplicate INCLUDE references (same triple, different lines) are deduplicated.

---

## Notes

- **IMPLICIT-MAIN naming:** `dependencies.py` represents IMPLICIT-MAIN entry
  points as `MAIN__<filename>` in `dep_02_unit_graph.csv`. This convention
  is resolved back to the inventory name by `reachability.py` and
  `visual_graph.py`.
- **Ambiguities:** When a called name matches multiple definitions
  (`dep_00_ambiguities.csv`), the edge in `dep_02` may point to multiple
  candidate files (semicolon-separated in `Target_File`).
