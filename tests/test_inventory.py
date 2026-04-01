"""
test_inventory.py
Verifies inventory_report.csv produced by inventory.py against the
synthetic fixtures corpus.

Expected corpus: 8 source files, 24 units total.
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def inventory(pipeline_results):
    return read_csv(pipeline_results / "inventory_report.csv")


# ---------------------------------------------------------------------------
# Total unit count
# ---------------------------------------------------------------------------


def test_total_units(inventory):
    assert len(inventory) == 26


# ---------------------------------------------------------------------------
# Unit types present
# ---------------------------------------------------------------------------


def test_unit_types_present(inventory):
    tipos = {r["Type"].strip().upper() for r in inventory}
    for expected in ("PROGRAM", "SUBROUTINE", "FUNCTION", "MODULE", "BLOCK DATA", "INTERFACE", "IMPLICIT-MAIN"):
        assert expected in tipos, f"Unit type '{expected}' not found in inventory"


# ---------------------------------------------------------------------------
# Specific units
# ---------------------------------------------------------------------------


def test_program_solver_main(inventory):
    rows = rows_by(inventory, Name="SOLVER_MAIN", Type="PROGRAM")
    assert len(rows) == 1
    assert rows[0]["File"] == "solver_main.f90"


def test_implicit_main_detected(inventory):
    rows = rows_by(inventory, Type="IMPLICIT-MAIN")
    assert len(rows) == 1
    assert rows[0]["File"] == "implicit_run.f"


def test_block_data_detected(inventory):
    rows = rows_by(inventory, Name="INIT_DAT", Type="BLOCK DATA")
    assert len(rows) == 1
    assert rows[0]["File"] == "legacy_data.f90"


def test_anon_interface_detected(inventory):
    """Anonymous INTERFACE block → type INTERFACE, in solver_main.f90."""
    rows = rows_by(inventory, Type="INTERFACE")
    assert len(rows) == 1
    assert rows[0]["File"] == "solver_main.f90"


def test_named_interface_detected(inventory):
    """Named (generic) INTERFACE block → type GENERIC_INTERFACE, in utils.f90."""
    rows = rows_by(inventory, Type="GENERIC_INTERFACE")
    assert len(rows) == 1
    assert rows[0]["File"] == "utils.f90"
    assert rows[0]["Name"].upper() == "MATH_GENERIC"


def test_derived_type_module(inventory):
    rows = rows_by(inventory, Name="MODEL_TYPES", Type="MODULE")
    assert len(rows) == 1


def test_contains_units_present(inventory):
    """validate_grid and compute_step are CONTAINS units of solver_main."""
    names = {r["Name"].strip().upper() for r in inventory}
    assert "VALIDATE_GRID" in names
    assert "COMPUTE_STEP" in names
    assert "CHECK_CONVERGENCE" in names


def test_ghost_routine_present(inventory):
    rows = rows_by(inventory, Name="GHOST_ROUTINE", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["File"] == "dead_code.f90"


def test_legacy_calc_present(inventory):
    rows = rows_by(inventory, Name="LEGACY_CALC", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["File"] == "kernel_legacy.f"


def test_process_mesh_present(inventory):
    rows = rows_by(inventory, Name="PROCESS_MESH", Type="SUBROUTINE")
    assert len(rows) == 1
    assert rows[0]["File"] == "mesh_hybrid.f90"


def test_ambiguous_units_file(pipeline_results):
    """dep_00_ambiguities.csv must report exactly 6 ambiguous units."""
    rows = read_csv(pipeline_results / "dep_00_ambiguities.csv")
    assert len(rows) == 6


# ---------------------------------------------------------------------------
# File coverage
# ---------------------------------------------------------------------------


def test_all_source_files_represented(inventory):
    files = {r["File"].strip() for r in inventory}
    expected_files = {
        "solver_main.f90",
        "kernel_legacy.f",
        "utils.f90",
        "utils_copy.f90",
        "dead_code.f90",
        "implicit_run.f",
        "mesh_hybrid.f90",
        "legacy_data.f90",
    }
    assert expected_files == files
