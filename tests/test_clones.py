"""
test_clones.py
Verifies reporte_clones.csv produced by clones.py.

Expected clone pairs from utils.f90 vs utils_copy.f90:
  IDENTICO  : MATH_UTIL_A, COMPUTE_LOAD            (2 pairs)
  SIMILAR   : MATH_UTIL_B, CALC_GROWTH, UTILS_MOD  (3 pairs)
  DIVERGIDO : CALC_METRICS                          (1 pair)
"""

import pytest
from tests.conftest import read_csv, rows_by


@pytest.fixture(scope="module")
def clones(pipeline_results):
    return read_csv(pipeline_results / "report_clones.csv")


# ---------------------------------------------------------------------------
# Total counts
# ---------------------------------------------------------------------------

def test_total_clone_pairs(clones):
    """6 clone pairs total across utils.f90 / utils_copy.f90."""
    assert len(clones) == 6


def test_identico_count(clones):
    identicos = [r for r in clones if r["Status"].strip().upper() == "IDENTICAL"]
    assert len(identicos) == 2


def test_similar_count(clones):
    similares = [r for r in clones if r["Status"].strip().upper() == "SIMILAR"]
    assert len(similares) == 3


def test_divergido_count(clones):
    divergidos = [r for r in clones if r["Status"].strip().upper() == "DIVERGED"]
    assert len(divergidos) == 1


# ---------------------------------------------------------------------------
# Specific pairs
# ---------------------------------------------------------------------------

def test_math_util_a_is_identico(clones):
    rows = rows_by(clones, Unit="MATH_UTIL_A", Status="IDENTICAL")
    assert len(rows) == 1
    assert float(rows[0]["Similitud_Pct"]) == 100.0


def test_compute_load_is_identico(clones):
    rows = rows_by(clones, Unit="COMPUTE_LOAD", Status="IDENTICAL")
    assert len(rows) == 1
    assert float(rows[0]["Similitud_Pct"]) == 100.0


def test_math_util_b_is_similar(clones):
    rows = rows_by(clones, Unit="MATH_UTIL_B", Status="SIMILAR")
    assert len(rows) == 1
    assert float(rows[0]["Similitud_Pct"]) >= 75.0


def test_calc_growth_is_similar(clones):
    rows = rows_by(clones, Unit="CALC_GROWTH", Status="SIMILAR")
    assert len(rows) == 1
    assert float(rows[0]["Similitud_Pct"]) >= 75.0


def test_calc_metrics_is_divergido(clones):
    rows = rows_by(clones, Unit="CALC_METRICS", Status="DIVERGED")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# File pair integrity
# ---------------------------------------------------------------------------

def test_all_pairs_involve_utils_files(clones):
    """All clone pairs must involve utils.f90 and utils_copy.f90."""
    for row in clones:
        archivos = {row["Archivo_A"].strip(), row["Archivo_B"].strip()}
        assert archivos == {"utils.f90", "utils_copy.f90"}
