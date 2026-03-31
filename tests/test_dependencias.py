"""
test_dependencias.py
Verifies dependency CSV outputs produced by dependencias.py.

Covers:
  dep_00_ambiguities.csv   — units with same name in multiple files
  dep_03_impact_matrix.csv — fan-in / fan-out per unit
  dep_04_external_orphans.csv — unresolved external references
  dep_06_include_files.csv — INCLUDE directives with presence status
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# dep_00 — Ambiguous units (same name in multiple files)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ambiguedades(pipeline_results):
    return read_csv(pipeline_results / "dep_00_ambiguities.csv")


def test_ambiguous_unit_count(ambiguedades):
    """6 units share names across utils.f90 and utils_copy.f90."""
    assert len(ambiguedades) == 6


def test_utils_mod_is_ambiguous(ambiguedades):
    rows = rows_by(ambiguedades, Unit_Name="UTILS_MOD")
    assert len(rows) == 1
    assert int(rows[0]["Count"]) == 2


def test_ambiguous_units_are_from_utils_files(ambiguedades):
    for row in ambiguedades:
        archivos = row["File_List"]
        assert "utils.f90" in archivos or "utils_copy.f90" in archivos


# ---------------------------------------------------------------------------
# dep_03 — Fan-in / Fan-out
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def impacto(pipeline_results):
    return read_csv(pipeline_results / "dep_03_impact_matrix.csv")


def test_shared_routine_fan_in(impacto):
    """SHARED_ROUTINE is called from dead_test and implicit_run → fan-in = 2."""
    rows = rows_by(impacto, Unit="SHARED_ROUTINE")
    assert len(rows) == 1
    assert int(rows[0]["Fan_In"]) == 2


def test_solver_main_fan_out(impacto):
    """solver_main calls validate_grid, compute_step, check_convergence, export_vtk_mesh."""
    rows = rows_by(impacto, Unit="SOLVER_MAIN")
    assert len(rows) == 1
    assert int(rows[0]["Fan_Out"]) == 4


def test_validate_grid_fan_in(impacto):
    """validate_grid is called only from solver_main → fan-in = 1."""
    rows = rows_by(impacto, Unit="VALIDATE_GRID")
    assert len(rows) == 1
    assert int(rows[0]["Fan_In"]) == 1


def test_dead_test_fan_out(impacto):
    """dead_test calls SHARED_ROUTINE → fan-out = 1."""
    rows = rows_by(impacto, Unit="DEAD_TEST")
    assert len(rows) == 1
    assert int(rows[0]["Fan_Out"]) == 1


# ---------------------------------------------------------------------------
# dep_04 — External / orphan references
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def externos(pipeline_results):
    return read_csv(pipeline_results / "dep_04_external_orphans.csv")


def test_external_orphans_count(externos):
    """TIMER_C and EXPORT_VTK_MESH are called but not defined anywhere."""
    assert len(externos) == 2


def test_timer_c_is_external(externos):
    names = {r["Target_Unit"].strip().upper() for r in externos}
    assert "TIMER_C" in names


def test_export_vtk_mesh_is_external(externos):
    names = {r["Target_Unit"].strip().upper() for r in externos}
    assert "EXPORT_VTK_MESH" in names


# ---------------------------------------------------------------------------
# dep_06 — INCLUDE directives
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def includes(pipeline_results):
    return read_csv(pipeline_results / "dep_06_include_files.csv")


def test_include_count(includes):
    """Only one INCLUDE directive in the corpus (implicit_run.f → params.inc)."""
    assert len(includes) == 1


def test_params_inc_is_present(includes):
    row = includes[0]
    assert row["Included_File"].strip() == "params.inc"
    assert row["Status"].strip().upper() == "PRESENT"
    assert row["Source_File"].strip() == "implicit_run.f"
