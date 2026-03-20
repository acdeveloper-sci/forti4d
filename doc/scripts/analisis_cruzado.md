# analisis_cruzado.py

## Purpose

Assigns a migration strategy to each unit by crossing statement density
metrics with call graph coupling data. Computes two composite indices and
applies a rule engine to recommend an action for each unit.

---

## Configuration

| Constant | Default | Description |
| :--- | :--- | :--- |
| `ARCHIVO_DENSIDAD` | `"reporte_densidad.csv"` | Input: statement density profiles |
| `ARCHIVO_IMPACTO` | `"dep_03_matriz_impacto.csv"` | Input: Fan-In / Fan-Out |
| `SALIDA_ESTRATEGIA` | `"reporte_estrategia_migracion.csv"` | Output |

---

## Inputs

- `reporte_densidad.csv`
- `dep_03_matriz_impacto.csv`

---

## Output: `reporte_estrategia_migracion.csv`

One row per unit, sorted by `Prioridad_Num` ascending (most urgent first),
then by `IVC` descending within the same priority.

| Column | Description |
| :--- | :--- |
| `Prioridad_Num` | Numeric priority (1 = most urgent) |
| `Estrategia` | Recommended action (see below) |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `ICM` | Migration Complexity Index (0–100) |
| `IVC` | Calculation Value Index (= `Pct_Calculo`) |
| `Pct_Calculo` | % calculation statements |
| `Pct_Control` | % control-flow statements |
| `Pct_Legacy` | % legacy statements |
| `Fan_In` | Number of callers |
| `Fan_Out` | Number of callees |
| `Explicacion` | Human-readable reason for the strategy |

---

## Composite Indices

**IVC (Índice de Valor de Cálculo):** equals `Pct_Calculo`. Measures how much
of the unit is pure algorithmic computation.

**ICM (Índice de Complejidad de Migración):**
```
ICM = 0.15 × Pct_Control
    + 0.45 × min(Pct_Legacy × 4, 100)
    + 0.20 × min(Fan_Out × 5, 100)
    + 0.20 × min(Fan_In × 5, 100)
```

---

## Strategy Rule Engine

Rules are evaluated in order; the first match wins.

| Priority | Strategy | Condition |
| :---: | :--- | :--- |
| 1 | `MIGRACION_DIRECTA` | IVC > 50 and ICM < 30 — pure algorithm, low coupling |
| 2 | `MIGRACION_ESTANDAR` | Default for connected units with moderate complexity |
| 3 | `REEMPLAZAR_LIB` | Pct_IO > 30 or Pct_Decl > 40, and IVC < 20 — infrastructure/boilerplate |
| 4 | `REFACTORIZAR_CORE` | ICM > 25 and Fan-In > 5 — high-risk, high-dependency knot |
| 5 | `REESCRIBIR_AISLADO` | ICM > 20 — complex but low systemic impact |
| 6 | `ANALIZAR_UTILIDAD` | Fan-In = 0, Fan-Out > 0, or isolated with substantial logic |
| 7 | `ELIMINAR` | Fan-In = 0, Fan-Out = 0, IVC ≤ 25 — probable dead code |

Units with type `PROGRAM`, `IMPLICIT-MAIN`, `MODULE`, or `BLOCK DATA` are
exempt from the Fan-In = 0 dead-code rule.
