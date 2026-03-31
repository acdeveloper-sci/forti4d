"""
test_simbolos.py
Verifies symbol-analysis CSVs: type_definitions, type_components,
symbol_implicit, equivalences.

Key corpus facts:
  - NODE_DATA derived type in solver_main.f90 / model_types (3 components)
  - LEGACY_CALC has non-NONE implicit rules (old F77 defaults)
  - EQUIVALENT groups: LEGACY_CALC has 1 group with 3 vars (A, B, C)
"""

import pytest
from tests.conftest import read_csv, rows_by


# ---------------------------------------------------------------------------
# Derived types — type_definitions.csv
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tipos_def(pipeline_results):
    return read_csv(pipeline_results / "type_definitions.csv")


@pytest.fixture(scope="module")
def tipos_comp(pipeline_results):
    return read_csv(pipeline_results / "type_components.csv")


def test_node_data_type_detected(tipos_def):
    """NODE_DATA is the only derived type in the fixtures corpus."""
    rows = rows_by(tipos_def, Type_Name="NODE_DATA")
    assert len(rows) == 1


def test_node_data_component_count(tipos_def):
    rows = rows_by(tipos_def, Type_Name="NODE_DATA")
    assert int(rows[0]["N_Components"]) == 3


def test_node_data_in_model_types(tipos_def):
    rows = rows_by(tipos_def, Type_Name="NODE_DATA")
    assert rows[0]["Unidad"].strip().upper() == "MODEL_TYPES"
    assert rows[0]["Archivo"].strip() == "solver_main.f90"


def test_node_data_components(tipos_comp):
    comps = [r for r in tipos_comp
             if r["Type_Name"].strip().upper() == "NODE_DATA"]
    names = {r["Comp_Name"].strip().upper() for r in comps}
    assert "TEMPERATURE" in names
    assert "STRESS_TENSOR_XX" in names
    assert "MATERIAL_ID" in names


# ---------------------------------------------------------------------------
# Implicit rules — symbol_implicit.csv
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def implicit(pipeline_results):
    return read_csv(pipeline_results / "symbol_implicit.csv")


def test_legacy_calc_has_implicit_rules(implicit):
    """LEGACY_CALC (F77) must have non-NONE implicit rules."""
    rows = [r for r in implicit
            if r["Unidad"].strip().upper() == "LEGACY_CALC"
            and r["Is_None"].strip().upper() == "NO"]
    assert len(rows) >= 1


def test_solver_main_is_implicit_none(implicit):
    rows = rows_by(implicit, Unidad="SOLVER_MAIN", Is_None="YES")
    assert len(rows) == 1


def test_dead_test_is_implicit_none(implicit):
    rows = rows_by(implicit, Unidad="DEAD_TEST", Is_None="YES")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# EQUIVALENCE groups — equivalences.csv
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def equivalencias(pipeline_results):
    return read_csv(pipeline_results / "equivalences.csv")


def test_legacy_calc_has_equivalence(equivalencias):
    rows = [r for r in equivalencias
            if r["Unidad"].strip().upper() == "LEGACY_CALC"]
    assert len(rows) >= 1


def test_equivalence_group_has_three_members(equivalencias):
    """LEGACY_CALC EQUIVALENCE group merges A, B, C."""
    rows = [r for r in equivalencias
            if r["Unidad"].strip().upper() == "LEGACY_CALC"]
    assert int(rows[0]["N_Members"]) == 3


def test_equivalence_var_names(equivalencias):
    rows = [r for r in equivalencias
            if r["Unidad"].strip().upper() == "LEGACY_CALC"]
    names = {r["Var_Name"].strip().upper() for r in rows}
    assert {"A", "B", "C"} == names
