# analisis_cruzado.py

## Purpose

Assigns a migration strategy to each unit by crossing statement density
metrics with call graph coupling data. Computes two composite indices and
applies a rule engine to recommend an action for each unit.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `ARCHIVO_DENSIDAD` | `RUTA_RESULTADOS / "reporte_densidad.csv"` | Input: statement density profiles |
| `ARCHIVO_IMPACTO` | `RUTA_RESULTADOS / "dep_03_matriz_impacto.csv"` | Input: Fan-In / Fan-Out |
| `SALIDA_ESTRATEGIA` | `RUTA_RESULTADOS / "reporte_estrategia_migracion.csv"` | Output |
| `ALCANZABILIDAD_CSV` | `RUTA_RESULTADOS / "reporte_alcanzabilidad.csv"` | Optional: reachability status |
| `SIMBOLOS_IMPL_CSV` | `RUTA_RESULTADOS / "simbolos_implicit.csv"` | Optional: IMPLICIT NONE status |
| `EQUIVALENCIAS_CSV` | `RUTA_RESULTADOS / "equivalencias.csv"` | Optional: EQUIVALENCE aliasing groups |

E4 penalty parameters: `E4_PENALTY_MAX = 7.0`, `W_E4_IMPL = 0.70`, `W_E4_EQUIV = 0.30`.

---

## Inputs

Required:
- `<FORT_OUT>/reporte_densidad.csv`
- `<FORT_OUT>/dep_03_matriz_impacto.csv`

Optional (used if present, silently skipped otherwise):
- `<FORT_OUT>/reporte_alcanzabilidad.csv` — enables confirmed dead-code rule
- `<FORT_OUT>/simbolos_implicit.csv` — enables E4 ICM penalty
- `<FORT_OUT>/equivalencias.csv` — enables E4 ICM penalty

---

## Output: `<FORT_OUT>/reporte_estrategia_migracion.csv`

One row per unit, sorted by `Prioridad_Num` ascending (most urgent first),
then by `IVC` descending within the same priority.

| Column | Description |
| :--- | :--- |
| `Prioridad_Num` | Numeric priority (1 = most urgent) |
| `Estrategia` | Recommended action (see below) |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `ICM` | Migration Complexity Index (base + E4 penalty) |
| `IVC` | Calculation Value Index (= `Pct_Calculo`) |
| `Pct_Calculo` | % calculation statements |
| `Pct_Control` | % control-flow statements |
| `Pct_Legacy` | % legacy statements |
| `Fan_In` | Number of callers |
| `Fan_Out` | Number of callees |
| `Estado_Alcanz` | Reachability status from `alcanzabilidad.py` (empty if CSV not present) |
| `Explicacion` | Human-readable reason for the strategy |

---

## Composite Indices

**IVC (Índice de Valor de Cálculo):** equals `Pct_Calculo`. Measures how much
of the unit is pure algorithmic computation.

**ICM (Índice de Complejidad de Migración):**
```
ICM_base = 0.15 × Pct_Control
         + 0.45 × min(Pct_Legacy × 4, 100)
         + 0.20 × min(Fan_Out × 5, 100)
         + 0.20 × min(Fan_In × 5, 100)

E4_penalty = 7.0 × (0.70 × sin_IMPLICIT_NONE + 0.30 × tiene_EQUIVALENCE)

ICM = ICM_base + E4_penalty
```

The E4 penalty is applied only when `simbolos_implicit.csv` and/or
`equivalencias.csv` are present. `sin_IMPLICIT_NONE` is 1 when the unit
does not have `IMPLICIT NONE`; `tiene_EQUIVALENCE` is 1 when the unit
has at least one EQUIVALENCE aliasing group. Maximum additive penalty: 7.0 points.

---

## Strategy Rule Engine

Rules are evaluated in order; the first match wins.

| Priority | Rule | Strategy | Condition |
| :---: | :--- | :--- | :--- |
| — | -1 | `ELIMINAR` | `Estado_Alcanz = NO_ALCANZABLE` — confirmed dead code (requires alcanzabilidad CSV) |
| 1 | 0 | `ANALIZAR_UTILIDAD` / `ELIMINAR` | Fan-In = 0 (proxy dead-code check when reachability not available) |
| 2 | 1 | `MIGRACION_DIRECTA` | IVC > 50 and ICM < 30 — pure algorithm, low coupling |
| 3 | 2 | `REEMPLAZAR_LIB` | Pct_IO > 30 or Pct_Decl > 40, and IVC < 20 — infrastructure/boilerplate |
| 4 | 3 | `REFACTORIZAR_CORE` | ICM > 25 and Fan-In > 5 — high-risk, high-dependency knot |
| 5 | 4 | `REESCRIBIR_AISLADO` | ICM > 20 — complex but low systemic impact |
| 6 | default | `MIGRACION_ESTANDAR` | All other connected units |

**Rule -1** fires before any other rule when `reporte_alcanzabilidad.csv` is
present. Units confirmed as `NO_ALCANZABLE` always receive `ELIMINAR`
regardless of Fan-In, ICM, or IVC values.

Units with type `PROGRAM`, `IMPLICIT-MAIN`, `MODULE`, or `BLOCK DATA` are
exempt from the Fan-In = 0 dead-code rule (Rule 0).
