# dependencias.py

## Purpose

Builds the call graph of the corpus. Resolves CALL, USE, and function-call
references between units. Computes Fan-In and Fan-Out per unit. Identifies
units defined in multiple files (ambiguities) and external references with
no known definition (orphans).

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `ARCHIVO_INVENTARIO` | `RUTA_RESULTADOS / "reporte_inventario.csv"` | Input: unit inventory |
| `OUT_AMBIGUOS` | `RUTA_RESULTADOS / "dep_00_ambiguedades.csv"` | Units with the same name in multiple files |
| `OUT_MAESTRO` | `RUTA_RESULTADOS / "dep_01_datos_maestros.csv"` | All resolved call/use relationships |
| `OUT_GRAFO` | `RUTA_RESULTADOS / "dep_02_grafo_unidades.csv"` | Resolved call graph edges |
| `OUT_IMPACTO` | `RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"` | Fan-In and Fan-Out per unit |
| `OUT_HUERFANOS` | `RUTA_RESULTADOS / "dep_04_externos_huerfanos.csv"` | References with no known definition |
| `OUT_ARCHIVOS` | `RUTA_RESULTADOS / "dep_05_dependencia_archivos.csv"` | File-level dependency summary |
| `OUT_INCLUDES` | `RUTA_RESULTADOS / "dep_06_include_files.csv"` | Explicit INCLUDE file references |

---

## Inputs

- `<FORT_OUT>/reporte_inventario.csv`
- Fortran source files in `CARPETA_CODIGO`

---

## Outputs

### `dep_00_ambiguedades.csv`
Units with the same name defined in more than one source file.

| Column | Description |
| :--- | :--- |
| `Nombre_Unidad` | Unit name |
| `Tipo` | Unit type |
| `Cantidad_Apariciones` | Number of files where this name is defined |
| `Lista_Archivos` | Semicolon-separated list of those files |

### `dep_01_datos_maestros.csv`
All detected call/use relationships before resolution.

### `dep_02_grafo_unidades.csv`
Resolved call graph. One row per directed edge.

| Column | Description |
| :--- | :--- |
| `Unidad_Origen` | Calling unit. IMPLICIT-MAIN units appear as `MAIN__<filename>` |
| `Tipo_Origen` | Type of the calling unit |
| `Unidad_Destino` | Called/used unit |
| `Tipo_Destino` | Type of the called unit |
| `Tipo_Dep` | Edge type: `CALL`, `USE`, or `FUNC_CALL` |
| `Archivo_Destino` | Source file(s) of the destination unit |
| `Peso` | Number of times this dependency appears in the calling unit |

### `dep_03_matriz_impacto.csv`
Fan-In and Fan-Out per unit.

| Column | Description |
| :--- | :--- |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `Archivo` | Source file |
| `Fan_In` | Number of units that call/use this unit |
| `Fan_Out` | Number of distinct units this unit calls/uses |

### `dep_04_externos_huerfanos.csv`
References found in source code with no matching definition in the corpus
(external library calls, unresolved symbols).

### `dep_05_dependencia_archivos.csv`
Aggregated dependency summary at file level.

### `dep_06_include_files.csv`
Explicit INCLUDE file references — one row per unique `(Archivo_Origen, Unidad_Origen, Archivo_Incluido)` triple.

| Column | Description |
| :--- | :--- |
| `Archivo_Origen` | Source file containing the INCLUDE statement |
| `Unidad_Origen` | Unit (scope) in which the INCLUDE appears |
| `Archivo_Incluido` | Filename referenced by the INCLUDE directive |
| `Estado` | `PRESENTE` if the file exists in `CARPETA_CODIGO`; `FALTANTE` otherwise |

Duplicate INCLUDE references (same triple, different lines) are deduplicated.

---

## Notes

- **IMPLICIT-MAIN naming:** `dependencias.py` represents IMPLICIT-MAIN entry
  points as `MAIN__<filename>` in `dep_02_grafo_unidades.csv`. This convention
  is resolved back to the inventory name by `alcanzabilidad.py` and
  `grafo_visual.py`.
- **Ambiguities:** When a called name matches multiple definitions
  (`dep_00_ambiguedades.csv`), the edge in `dep_02` may point to multiple
  candidate files (semicolon-separated in `Archivo_Destino`).
