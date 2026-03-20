# priorizacion.py

## Purpose

Computes a composite risk/effort score for each program unit and ranks them
for migration planning. Combines four signals — complexity, criticality,
legacy density, and clone status — into a single ordered list.

---

## Configuration

All paths are resolved under `RUTA_RESULTADOS`. See `config.py`.

| Constant | Default | Description |
| :--- | :--- | :--- |
| `CONSOLIDADO` | `RUTA_RESULTADOS / "reporte_consolidado.csv"` | Input: per-unit metrics |
| `CLONES_CSV` | `RUTA_RESULTADOS / "reporte_clones.csv"` | Input: clone state per pair |
| `ESTRATEGIA` | `RUTA_RESULTADOS / "reporte_estrategia_migracion.csv"` | Input: migration strategy |
| `SALIDA_CSV` | `RUTA_RESULTADOS / "reporte_priorizacion.csv"` | Output |
| `W_CC` | `0.30` | Weight for cyclomatic complexity component |
| `W_FAN_IN` | `0.30` | Weight for Fan-In (criticality) component |
| `W_LEGACY` | `0.20` | Weight for legacy construct density component |
| `W_CLONE` | `0.20` | Weight for clone penalty component |
| `UMBRAL_CRITICA` | `40` | Score threshold for `CRITICA` priority |
| `UMBRAL_ALTA` | `25` | Score threshold for `ALTA` priority |
| `UMBRAL_MEDIA` | `12` | Score threshold for `MEDIA` priority |

---

## Inputs

- `<FORT_OUT>/reporte_consolidado.csv`
- `<FORT_OUT>/reporte_clones.csv`
- `<FORT_OUT>/reporte_estrategia_migracion.csv` (optional)

---

## Output: `<FORT_OUT>/reporte_priorizacion.csv`

One row per program unit, sorted by priority tier then by score descending.
Dead code units appear last.

| Column | Description |
| :--- | :--- |
| `Prioridad` | `CRITICA`, `ALTA`, `MEDIA`, `BAJA`, or `DEAD_CODE` |
| `Score` | Composite score 0–100 |
| `Archivo` | Source file name |
| `Unidad` | Unit name |
| `Tipo` | Unit type |
| `CC` | McCabe cyclomatic complexity |
| `Fan_In` | Number of units that call this one |
| `Pct_Legacy` | Percentage of legacy statements |
| `Estado_Alcanz` | `ALCANZABLE`, `NO_ALCANZABLE`, or `ENTRADA` |
| `Estado_Clon` | Worst clone state for this unit: `DIVERGIDO`, `SIMILAR`, `IDENTICO`, or blank |
| `Estrategia` | Migration strategy recommendation |
| `Score_CC` | CC component contribution (0–30) |
| `Score_FanIn` | Fan-In component contribution (0–30) |
| `Score_Legacy` | Legacy component contribution (0–20) |
| `Score_Clon` | Clone component contribution (0–20) |

---

## Scoring

**Score = (W_CC × CC_norm + W_FAN_IN × FanIn_norm + W_LEGACY × Legacy_norm + W_CLONE × Clone_norm) × 100**

Each component is normalized to 0–1:

| Component | Normalization |
| :--- | :--- |
| CC | `min(CC / P95_CC, 1.0)` — 95th percentile of CC among reachable units |
| Fan_In | `min(Fan_In / P95_FanIn, 1.0)` — 95th percentile of Fan_In |
| Pct_Legacy | `Pct_Legacy / 100` |
| Clone | `1.0` if DIVERGIDO, `0.5` if SIMILAR, `0.25` if IDENTICO, `0.0` if no clones |

The 95th percentile is used as the normalization reference (instead of the
maximum) to prevent a single outlier — such as an IMPLICIT-MAIN unit with
very high CC — from compressing the entire scale.

---

## Priority Levels

| Level | Score | Meaning |
| :--- | :--- | :--- |
| `CRITICA` | ≥ 40 | High complexity or criticality, requires early planning |
| `ALTA` | ≥ 25 | Significant risk in at least one dimension |
| `MEDIA` | ≥ 12 | Moderate — plan but not urgent |
| `BAJA` | < 12 | Low risk, straightforward migration |
| `DEAD_CODE` | — | `NO_ALCANZABLE` — evaluate for deletion before migrating |

Thresholds are calibrated for the practical score ceiling (~50–60), since
no unit simultaneously maximizes all four signals. Adjust `UMBRAL_*` constants
if the distribution is too concentrated in one tier.

---

## Notes

- Normalization is computed only over reachable units (`Estado ≠ NO_ALCANZABLE`)
  so that dead code does not skew the reference values.
- `Estado_Clon` reflects the **worst** clone state among all pairs involving
  that unit. A unit that is IDENTICAL to one copy but DIVERGED from another
  is classified as DIVERGIDO.
- The component score columns (`Score_CC`, `Score_FanIn`, etc.) are included
  to help diagnose why a unit received its score and to calibrate weights.
