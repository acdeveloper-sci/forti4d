"""
priorizacion.py
Computes a composite risk/effort score for each unit and ranks them
for migration planning.

Score (0-100) weighted across five signals:
  CC           30%  — cyclomatic complexity (normalized by corpus max)
  Fan_In       30%  — call-graph criticality (normalized by corpus max)
  Pct_Legacy   20%  — legacy construct density
  Clone        15%  — penalty for being part of a diverged/similar duplicate group
  E4_Risk      5%   — E4 scope risk: no IMPLICIT NONE and/or EQUIVALENCE aliasing

Units with Estado = NO_ALCANZABLE (dead code) are separated into a
DEAD_CODE priority tier and placed at the bottom of the list.

Output: reporte_priorizacion.csv
"""

import csv
from collections import defaultdict
from pathlib import Path

from forti4d.config import RUTA_RESULTADOS

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
CONSOLIDADO  = RUTA_RESULTADOS / "reporte_consolidado.csv"
CLONES_CSV   = RUTA_RESULTADOS / "report_clones.csv"
ESTRATEGIA   = RUTA_RESULTADOS / "reporte_estrategia_migracion.csv"
SALIDA_CSV   = RUTA_RESULTADOS / "reporte_priorizacion.csv"

# Score weights (must sum to 1.0)
W_CC        = 0.30
W_FAN_IN    = 0.30
W_LEGACY    = 0.20
W_CLONE     = 0.15
W_E4        = 0.05

# E4_Risk sub-weights (must sum to 1.0)
# No IMPLICIT NONE: harder to infer types, higher migration risk.
# EQUIVALENCE: memory aliasing, incompatible with safe refactoring.
W_E4_IMPL   = 0.70   # no IMPLICIT NONE
W_E4_EQUIV  = 0.30   # has EQUIVALENCE aliasing

# Clone penalty per worst state
CLONE_PENALTY = {
    "DIVERGED":  1.0,
    "SIMILAR":   0.5,
    "IDENTICAL": 0.25,
}

# Priority thresholds (applied to score 0-100).
# In practice the maximum achievable score is ~50-60 since no unit
# simultaneously maxes out all four signals.
UMBRAL_CRITICA = 40
UMBRAL_ALTA    = 25
UMBRAL_MEDIA   = 12


# =============================================================================
# HELPERS
# =============================================================================

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def percentil(values: list, pct: float) -> float:
    """Returns the pct-th percentile of values (0-100 scale)."""
    s = sorted(v for v in values if v > 0)
    if not s:
        return 1.0
    k = (len(s) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def clasificar_prioridad(score: float) -> str:
    if score >= UMBRAL_CRITICA:
        return "CRITICA"
    if score >= UMBRAL_ALTA:
        return "ALTA"
    if score >= UMBRAL_MEDIA:
        return "MEDIA"
    return "BAJA"


def _orden_prioridad(p: str) -> int:
    return {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "BAJA": 3, "DEAD_CODE": 4}[p]


# =============================================================================
# CARGA DE FUENTES
# =============================================================================

def cargar_consolidado() -> list:
    if not CONSOLIDADO.exists():
        print(f"ERROR: {CONSOLIDADO} no encontrado. Ejecuta consolidar.py primero.")
        return []
    with open(CONSOLIDADO, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def cargar_estrategia() -> dict:
    """Returns dict: (archivo, unidad_upper) → Estrategia string."""
    result = {}
    if not ESTRATEGIA.exists():
        return result
    with open(ESTRATEGIA, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = row.get("Archivo", "").strip()
            u = row.get("Unidad",  "").strip().upper()
            if a and u:
                result[(a, u)] = row.get("Estrategia", "").strip()
    return result


def cargar_peor_estado_clon() -> dict:
    """
    Returns dict: (archivo, unidad_upper) → worst clone Estado for that unit.
    A unit appears in clones as Archivo_A or Archivo_B.
    """
    _rank = {"DIVERGED": 3, "SIMILAR": 2, "IDENTICAL": 1}
    peor = {}

    if not CLONES_CSV.exists():
        return peor

    with open(CLONES_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            nombre = row.get("Unit", "").strip().upper()
            estado = row.get("Status", "").strip()
            arch_a = row.get("Archivo_A", "").strip()
            arch_b = row.get("Archivo_B", "").strip()

            for arch in (arch_a, arch_b):
                key = (arch, nombre)
                rank_actual = _rank.get(peor.get(key, ""), 0)
                rank_nuevo  = _rank.get(estado, 0)
                if rank_nuevo > rank_actual:
                    peor[key] = estado

    return peor


# =============================================================================
# SCORING
# =============================================================================

def calcular_scores(filas: list, clones: dict, estrategia: dict) -> list:
    # Normalization reference: 95th percentile among reachable units.
    # Using percentile instead of max prevents a single outlier (e.g. an
    # IMPLICIT-MAIN with CC in the thousands) from compressing the entire scale.
    # Values above the reference are capped at 1.0.
    vivos = [r for r in filas if r.get("Status", "") != "UNREACHABLE"]

    ref_cc    = percentil([safe_float(r.get("CC"))     for r in vivos], 95) or 1.0
    ref_fanin = percentil([safe_float(r.get("Fan_In")) for r in vivos], 95) or 1.0

    resultado = []
    for row in filas:
        archivo = row.get("Archivo", "").strip()
        unidad  = row.get("Unidad",  "").strip()
        estado  = row.get("Status",  "").strip()

        cc      = safe_float(row.get("CC"))
        fan_in  = safe_float(row.get("Fan_In"))
        legacy  = safe_float(row.get("Pct_Legacy"))

        # Normalized components (0-1), capped at 1.0
        s_cc    = min(cc     / ref_cc,    1.0)
        s_fanin = min(fan_in / ref_fanin, 1.0)
        s_legacy = legacy / 100.0

        # Clone component
        estado_clon = clones.get((archivo, unidad.upper()), "")
        s_clone = CLONE_PENALTY.get(estado_clon, 0.0)

        # E4 Risk component
        sin_impl_none = row.get("Implicit_None", "") != "YES"
        tiene_equiv   = row.get("Tiene_Equiv",   "") == "YES"
        s_e4 = min(W_E4_IMPL * (1.0 if sin_impl_none else 0.0) +
                   W_E4_EQUIV * (1.0 if tiene_equiv   else 0.0), 1.0)

        # Weighted score (0-100)
        score = (W_CC * s_cc + W_FAN_IN * s_fanin +
                 W_LEGACY * s_legacy + W_CLONE * s_clone +
                 W_E4 * s_e4) * 100

        if estado == "UNREACHABLE":
            prioridad = "DEAD_CODE"
        else:
            prioridad = clasificar_prioridad(score)

        estrategia_unit = estrategia.get((archivo, unidad.upper()), "")

        resultado.append({
            "Prioridad":    prioridad,
            "Score":        round(score, 1),
            "Archivo":      archivo,
            "Unidad":       unidad,
            "Type":         row.get("Type", ""),
            "CC":           row.get("CC", ""),
            "Fan_In":       row.get("Fan_In", ""),
            "Pct_Legacy":   row.get("Pct_Legacy", ""),
            "Reachability_Status":estado,
            "Clone_Status":  estado_clon,
            "Estrategia":   estrategia_unit,
            "Implicit_None": row.get("Implicit_None", ""),
            "Tiene_Equiv":   row.get("Tiene_Equiv", ""),
            "Score_CC":     round(s_cc * W_CC * 100, 1),
            "Score_FanIn":  round(s_fanin * W_FAN_IN * 100, 1),
            "Score_Legacy": round(s_legacy * W_LEGACY * 100, 1),
            "Score_Clon":   round(s_clone * W_CLONE * 100, 1),
            "Score_E4":     round(s_e4 * W_E4 * 100, 1),
        })

    # Sort: by priority tier first, then by score descending
    resultado.sort(key=lambda r: (_orden_prioridad(r["Prioridad"]), -r["Score"]))
    return resultado


# =============================================================================
# MAIN
# =============================================================================

def main():
    RUTA_RESULTADOS.mkdir(parents=True, exist_ok=True)

    filas = cargar_consolidado()
    if not filas:
        return

    clones    = cargar_peor_estado_clon()
    estrategia = cargar_estrategia()

    resultado = calcular_scores(filas, clones, estrategia)

    campos = [
        "Prioridad", "Score",
        "Archivo", "Unidad", "Type",
        "CC", "Fan_In", "Pct_Legacy",
        "Reachability_Status", "Clone_Status", "Estrategia",
        "Implicit_None", "Tiene_Equiv",
        "Score_CC", "Score_FanIn", "Score_Legacy", "Score_Clon", "Score_E4",
    ]

    with open(SALIDA_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(resultado)

    # Summary
    conteo = {"CRITICA": 0, "ALTA": 0, "MEDIA": 0, "BAJA": 0, "DEAD_CODE": 0}
    for r in resultado:
        conteo[r["Prioridad"]] += 1

    print(f"\n{len(resultado)} unidades priorizadas")
    print(f"  CRITICA   : {conteo['CRITICA']}")
    print(f"  ALTA      : {conteo['ALTA']}")
    print(f"  MEDIA     : {conteo['MEDIA']}")
    print(f"  BAJA      : {conteo['BAJA']}")
    print(f"  DEAD_CODE : {conteo['DEAD_CODE']}")
    print(f"\nTop 10:")
    for r in resultado[:10]:
        print(f"  [{r['Prioridad']:<9}] {r['Score']:>5}  {r['Unidad']:<25} CC={r['CC']}  FanIn={r['Fan_In']}")
    print(f"\nGenerado: {SALIDA_CSV}")


if __name__ == "__main__":
    main()
