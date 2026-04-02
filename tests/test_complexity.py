"""
test_complexity.py
Verifies report_complexity.csv produced by complexity.py.

Expected CC values for key units in the fixtures corpus.
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def complexity(pipeline_results):
    return read_csv(pipeline_results / "report_complexity.csv")


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


def test_all_units_have_cc(complexity):
    """Every inventory unit must have a CC value."""
    for row in complexity:
        assert row["CC"].strip() != "", f"Missing CC for {row.get('Name')}"


# ---------------------------------------------------------------------------
# Specific CC values
# ---------------------------------------------------------------------------


def test_process_mesh_cc(complexity):
    """process_mesh has 11 decision points → CC = 12."""
    rows = rows_by(complexity, Unit="PROCESS_MESH")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 12


def test_process_mesh_level(complexity):
    rows = rows_by(complexity, Unit="PROCESS_MESH")
    assert rows[0]["Level"].strip().upper() == "MEDIUM"


def test_validate_grid_cc(complexity):
    """validate_grid has ~6 decision points → CC = 6."""
    rows = rows_by(complexity, Unit="VALIDATE_GRID")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 6


def test_validate_grid_level(complexity):
    rows = rows_by(complexity, Unit="VALIDATE_GRID")
    assert rows[0]["Level"].strip().upper() == "LOW"


def test_check_convergence_cc(complexity):
    """check_convergence is purely sequential → CC = 1."""
    rows = rows_by(complexity, Unit="CHECK_CONVERGENCE")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 1


def test_ghost_routine_cc(complexity):
    """GHOST_ROUTINE has no branches → CC = 1."""
    rows = rows_by(complexity, Unit="GHOST_ROUTINE")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 1


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def test_media_tier_count(complexity):
    """Only process_mesh reaches MEDIA tier."""
    medium = [r for r in complexity if r["Level"].strip().upper() == "MEDIUM"]
    assert len(medium) == 1
    assert medium[0]["Unit"].strip().upper() == "PROCESS_MESH"


def test_no_critica_tier(complexity):
    """No unit in fixtures should reach CRITICAL (CC > 20)."""
    critical = [r for r in complexity if r["Level"].strip().upper() == "CRITICAL"]
    assert len(critical) == 0
