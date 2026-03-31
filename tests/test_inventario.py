"""
test_inventario.py
Verifies reporte_inventario.csv produced by inventario.py against the
synthetic fixtures corpus.

Expected corpus: 8 source files, 24 units total.
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def inventario(pipeline_results):
    return read_csv(pipeline_results / "inventory_report.csv")


# ---------------------------------------------------------------------------
# Total unit count
# ---------------------------------------------------------------------------

def test_total_units(inventario):
    assert len(inventario) == 26


# ---------------------------------------------------------------------------
# Unit types present
# ---------------------------------------------------------------------------

def test_unit_types_present(inventario):
    tipos = {r["Type"].strip().upper() for r in inventario}
    for expected in ("PROGRAM", "SUBROUTINE", "FUNCTION", "MODULE",
                     "BLOCK DATA", "INTERFACE", "IMPLICIT-MAIN"):
        assert expected in tipos, f"Unit type '{expected}' not found in inventory"


# ---------------------------------------------------------------------------
# Specific units
# ---------------------------------------------------------------------------

def test_program_solver_main(inventario):
    rows = rows_by(inventario, Name="SOLVER_MAIN", Type="PROGRAM")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "solver_main.f90"


def test_implicit_main_detected(inventario):
    rows = rows_by(inventario, Type="IMPLICIT-MAIN")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "implicit_run.f"


def test_block_data_detected(inventario):
    rows = rows_by(inventario, Name="INIT_DAT", Type="BLOCK DATA")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "legacy_data.f90"


def test_anon_interface_detected(inventario):
    """Anonymous INTERFACE block → type INTERFACE, in solver_main.f90."""
    rows = rows_by(inventario, Type="INTERFACE")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "solver_main.f90"


def test_named_interface_detected(inventario):
    """Named (generic) INTERFACE block → type GENERIC_INTERFACE, in utils.f90."""
    rows = rows_by(inventario, Type="GENERIC_INTERFACE")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "utils.f90"
    assert rows[0]["Name"].upper() == "MATH_GENERIC"


def test_derived_type_module(inventario):
    rows = rows_by(inventario, Name="MODEL_TYPES", Type="MODULE")
    assert len(rows) == 1


def test_contains_units_present(inventario):
    """validate_grid and compute_step are CONTAINS units of solver_main."""
    names = {r["Name"].strip().upper() for r in inventario}
    assert "VALIDATE_GRID" in names
    assert "COMPUTE_STEP" in names
    assert "CHECK_CONVERGENCE" in names


def test_ghost_routine_present(inventario):
    rows = rows_by(inventario, Name="GHOST_ROUTINE", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "dead_code.f90"


def test_legacy_calc_present(inventario):
    rows = rows_by(inventario, Name="LEGACY_CALC", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "kernel_legacy.f"


def test_process_mesh_present(inventario):
    rows = rows_by(inventario, Name="PROCESS_MESH", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["Archivo"] == "mesh_hybrid.f90"


def test_ambiguous_units_file(pipeline_results):
    """dep_00_ambiguities.csv must report exactly 6 ambiguous units."""
    rows = read_csv(pipeline_results / "dep_00_ambiguities.csv")
    assert len(rows) == 6


# ---------------------------------------------------------------------------
# File coverage
# ---------------------------------------------------------------------------

def test_all_source_files_represented(inventario):
    archivos = {r["Archivo"].strip() for r in inventario}
    expected_files = {
        "solver_main.f90", "kernel_legacy.f", "utils.f90",
        "utils_copy.f90", "dead_code.f90", "implicit_run.f",
        "mesh_hybrid.f90", "legacy_data.f90",
    }
    assert expected_files == archivos
