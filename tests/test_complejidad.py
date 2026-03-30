"""
test_complejidad.py
Verifies reporte_complejidad.csv produced by complejidad.py.

Expected CC values for key units in the fixtures corpus.
"""

from pathlib import Path
import pytest
from tests.conftest import read_csv, rows_by

RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="module")
def complejidad(pipeline_results):
    return read_csv(pipeline_results / "reporte_complejidad.csv")


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def test_all_units_have_cc(complejidad):
    """Every inventory unit must have a CC value."""
    for row in complejidad:
        assert row["CC"].strip() != "", f"Missing CC for {row.get('Nombre')}"


# ---------------------------------------------------------------------------
# Specific CC values
# ---------------------------------------------------------------------------

def test_process_mesh_cc(complejidad):
    """process_mesh has 11 decision points → CC = 12."""
    rows = rows_by(complejidad, Unidad="PROCESS_MESH")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 12


def test_process_mesh_nivel(complejidad):
    rows = rows_by(complejidad, Unidad="PROCESS_MESH")
    assert rows[0]["Interpretacion"].strip().upper() == "MEDIA"


def test_validate_grid_cc(complejidad):
    """validate_grid has ~6 decision points → CC = 6."""
    rows = rows_by(complejidad, Unidad="VALIDATE_GRID")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 6


def test_validate_grid_nivel(complejidad):
    rows = rows_by(complejidad, Unidad="VALIDATE_GRID")
    assert rows[0]["Interpretacion"].strip().upper() == "BAJA"


def test_check_convergence_cc(complejidad):
    """check_convergence is purely sequential → CC = 1."""
    rows = rows_by(complejidad, Unidad="CHECK_CONVERGENCE")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 1


def test_ghost_routine_cc(complejidad):
    """GHOST_ROUTINE has no branches → CC = 1."""
    rows = rows_by(complejidad, Unidad="GHOST_ROUTINE")
    assert len(rows) == 1
    assert int(rows[0]["CC"]) == 1


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

def test_media_tier_count(complejidad):
    """Only process_mesh reaches MEDIA tier."""
    media = [r for r in complejidad if r["Interpretacion"].strip().upper() == "MEDIA"]
    assert len(media) == 1
    assert media[0]["Unidad"].strip().upper() == "PROCESS_MESH"


def test_no_critica_tier(complejidad):
    """No unit in fixtures should reach CRITICA (CC > 20)."""
    critica = [r for r in complejidad if r["Interpretacion"].strip().upper() == "CRITICA"]
    assert len(critica) == 0
