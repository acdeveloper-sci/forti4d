"""
test_alcanzabilidad.py
Verifies reporte_alcanzabilidad.csv produced by alcanzabilidad.py.

Expected reachability for the fixtures corpus:
  ENTRADA       : 3  (solver_main, dead_test, implicit_run)
  ALCANZABLE    : 6  (SHARED_ROUTINE, validate_grid, compute_step,
                      check_convergence, model_types via USE, INTERFACE in model_types)
  NO_ALCANZABLE : 17 (ghost, legacy_calc, process_mesh, utils units incl. GENERIC_INTERFACE, etc.)
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def alcanzabilidad(pipeline_results):
    return read_csv(pipeline_results / "report_reachability.csv")


# ---------------------------------------------------------------------------
# Global counts
# ---------------------------------------------------------------------------

def test_entry_point_count(alcanzabilidad):
    entrada = [r for r in alcanzabilidad
               if r["Status"].strip().upper() == "ENTRY_POINT"]
    assert len(entrada) == 3


def test_reachable_count(alcanzabilidad):
    alcanzable = [r for r in alcanzabilidad
                  if r["Status"].strip().upper() == "REACHABLE"]
    assert len(alcanzable) == 6


def test_dead_code_count(alcanzabilidad):
    dead = [r for r in alcanzabilidad
            if r["Status"].strip().upper() == "UNREACHABLE"]
    assert len(dead) == 17


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------

def test_solver_main_is_entry(alcanzabilidad):
    rows = rows_by(alcanzabilidad, Unidad="SOLVER_MAIN", Status="ENTRY_POINT")
    assert len(rows) == 1


def test_dead_test_is_entry(alcanzabilidad):
    rows = rows_by(alcanzabilidad, Unidad="DEAD_TEST", Status="ENTRY_POINT")
    assert len(rows) == 1


def test_implicit_run_is_entry(alcanzabilidad):
    rows = rows_by(alcanzabilidad, Status="ENTRY_POINT")
    archivos = {r["Archivo"].strip() for r in rows}
    assert "implicit_run.f" in archivos


# ---------------------------------------------------------------------------
# Reachable units
# ---------------------------------------------------------------------------

def test_shared_routine_is_reachable(alcanzabilidad):
    """Called from both dead_test and implicit_run → ALCANZABLE."""
    rows = rows_by(alcanzabilidad, Unidad="SHARED_ROUTINE", Status="REACHABLE")
    assert len(rows) == 1


def test_validate_grid_is_reachable(alcanzabilidad):
    """Called from solver_main → ALCANZABLE."""
    rows = rows_by(alcanzabilidad, Unidad="VALIDATE_GRID", Status="REACHABLE")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Dead code (NO_ALCANZABLE)
# ---------------------------------------------------------------------------

def test_ghost_routine_is_dead(alcanzabilidad):
    """GHOST_ROUTINE is never called → NO_ALCANZABLE."""
    rows = rows_by(alcanzabilidad, Unidad="GHOST_ROUTINE", Status="UNREACHABLE")
    assert len(rows) == 1


def test_legacy_calc_is_dead(alcanzabilidad):
    """LEGACY_CALC has no callers in the corpus → NO_ALCANZABLE."""
    rows = rows_by(alcanzabilidad, Unidad="LEGACY_CALC", Status="UNREACHABLE")
    assert len(rows) == 1


def test_process_mesh_is_dead(alcanzabilidad):
    """process_mesh is never called from any entry point → NO_ALCANZABLE."""
    rows = rows_by(alcanzabilidad, Unidad="PROCESS_MESH", Status="UNREACHABLE")
    assert len(rows) == 1


def test_utils_units_are_dead(alcanzabilidad):
    """All utils_mod units (both files) are unreachable — no program uses them."""
    utils_units = [r for r in alcanzabilidad
                   if r["Archivo"].strip() in ("utils.f90", "utils_copy.f90")
                   and r["Status"].strip().upper() == "UNREACHABLE"]
    assert len(utils_units) == 13  # 7 units in utils.f90 (incl. GENERIC_INTERFACE) + 6 in utils_copy.f90
