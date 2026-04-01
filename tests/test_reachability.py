"""
test_reachability.py
Verifies report_reachability.csv produced by reachability.py.

Expected reachability for the fixtures corpus:
  ENTRADA       : 3  (solver_main, dead_test, implicit_run)
  REACHEABLE    : 6  (SHARED_ROUTINE, validate_grid, compute_step,
                      check_convergence, model_types via USE, INTERFACE in model_types)
  NO_REACHEABLE : 17 (ghost, legacy_calc, process_mesh, utils units incl. GENERIC_INTERFACE, etc.)
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def reachability(pipeline_results):
    return read_csv(pipeline_results / "report_reachability.csv")


# ---------------------------------------------------------------------------
# Global counts
# ---------------------------------------------------------------------------


def test_entry_point_count(reachability):
    entry = [r for r in reachability if r["Status"].strip().upper() == "ENTRY_POINT"]
    assert len(entry) == 3


def test_reachable_count(reachability):
    reachable = [r for r in reachability if r["Status"].strip().upper() == "REACHABLE"]
    assert len(reachable) == 6


def test_dead_code_count(reachability):
    dead = [r for r in reachability if r["Status"].strip().upper() == "UNREACHABLE"]
    assert len(dead) == 17


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def test_solver_main_is_entry(reachability):
    rows = rows_by(reachability, Unit="SOLVER_MAIN", Status="ENTRY_POINT")
    assert len(rows) == 1


def test_dead_test_is_entry(reachability):
    rows = rows_by(reachability, Unit="DEAD_TEST", Status="ENTRY_POINT")
    assert len(rows) == 1


def test_implicit_run_is_entry(reachability):
    rows = rows_by(reachability, Status="ENTRY_POINT")
    files = {r["File"].strip() for r in rows}
    assert "implicit_run.f" in files


# ---------------------------------------------------------------------------
# Reachable units
# ---------------------------------------------------------------------------


def test_shared_routine_is_reachable(reachability):
    """Called from both dead_test and implicit_run → REACHEABLE."""
    rows = rows_by(reachability, Unit="SHARED_ROUTINE", Status="REACHABLE")
    assert len(rows) == 1


def test_validate_grid_is_reachable(reachability):
    """Called from solver_main → REACHEABLE."""
    rows = rows_by(reachability, Unit="VALIDATE_GRID", Status="REACHABLE")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Dead code (NO_REACHEABLE)
# ---------------------------------------------------------------------------


def test_ghost_routine_is_dead(reachability):
    """GHOST_ROUTINE is never called → NO_REACHEABLE."""
    rows = rows_by(reachability, Unit="GHOST_ROUTINE", Status="UNREACHABLE")
    assert len(rows) == 1


def test_legacy_calc_is_dead(reachability):
    """LEGACY_CALC has no callers in the corpus → NO_REACHEABLE."""
    rows = rows_by(reachability, Unit="LEGACY_CALC", Status="UNREACHABLE")
    assert len(rows) == 1


def test_process_mesh_is_dead(reachability):
    """process_mesh is never called from any entry point → NO_REACHEABLE."""
    rows = rows_by(reachability, Unit="PROCESS_MESH", Status="UNREACHABLE")
    assert len(rows) == 1


def test_utils_units_are_dead(reachability):
    """All utils_mod units (both files) are unreachable — no program uses them."""
    utils_units = [
        r
        for r in reachability
        if r["File"].strip() in ("utils.f90", "utils_copy.f90") and r["Status"].strip().upper() == "UNREACHABLE"
    ]
    assert len(utils_units) == 13  # 7 units in utils.f90 (incl. GENERIC_INTERFACE) + 6 in utils_copy.f90
