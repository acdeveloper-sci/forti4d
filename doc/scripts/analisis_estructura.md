# analisis_estructura.py

## Purpose

Classifies each source file into an architectural role based on its Fan-In
and Fan-Out profile from the call graph.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `ARCHIVO_IMPACTO` | `"dep_03_matriz_impacto.csv"` | Input: Fan-In/Fan-Out per unit |
| `ARCHIVO_INVENTARIO` | `"reporte_inventario.csv"` | Input: unit types (to detect IMPLICIT-MAIN) |
| `ARCHIVO_SALIDA` | `"analisis_nodos_criticos.csv"` | Output |
| `UMBRAL_CRITICO` | `10` | Min Fan-In to classify a file as `NODO_CRITICO` |

---

## Inputs

- `dep_03_matriz_impacto.csv`
- `reporte_inventario.csv`

---

## Output: `analisis_nodos_criticos.csv`

One row per source file.

| Column | Description |
| :--- | :--- |
| `Archivo` | Source file name |
| `Categoria` | Architectural role (see below) |
| `Fan_In_Max` | Maximum Fan-In across all units in the file |
| `Unidad_Max_In` | Unit with the highest Fan-In |
| `Fan_Out_Max` | Maximum Fan-Out across all units in the file |
| `Unidad_Max_Out` | Unit with the highest Fan-Out |
| `Total_Unidades` | Number of units in the file |
| `Tiene_Main` | `SI` if the file contains a PROGRAM or IMPLICIT-MAIN unit |
| `Detalle` | Human-readable explanation of the classification |

---

## Categories

Assigned in priority order (first matching rule wins):

| Category | Condition | Meaning |
| :--- | :--- | :--- |
| `ENTRY_POINT` | File contains an IMPLICIT-MAIN unit | Compiles to an executable |
| `ISLA` | Fan-In = 0 and Fan-Out = 0 | No connections — potential dead code |
| `NODO_CRITICO` | Max Fan-In ≥ `UMBRAL_CRITICO` (10) | High reuse — core library unit |
| `ORQUESTADOR` | Max Fan-Out ≥ `UMBRAL_CRITICO` (10) | Coordinates many dependencies |
| `OBRERO` | Connected but Fan-Out < 5 | Service or calculation routine |
| `MIXTO` | All other cases | Standard functionality |

---

## Notes

- Files present in `reporte_inventario.csv` but absent from `dep_03` (no
  call graph entries) are automatically classified as `ISLA`.
- Output is sorted by category priority:
  `NODO_CRITICO` → `ORQUESTADOR` → `ENTRY_POINT` → `MIXTO` → `OBRERO` → `ISLA`.
