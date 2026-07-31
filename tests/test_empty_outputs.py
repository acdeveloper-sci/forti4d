"""
test_empty_outputs.py
Tests that the pipeline writes empty CSVs (headers only) for a pure-library
corpus: no PROGRAM units, no duplicate unit names across files.

Covers the code paths fixed in v0.7.2 and v0.7.3:
  - dep_00_ambiguities.csv  — empty when no units share names across files
  - report_clones.csv       — empty when dep_00_ambiguities.csv is empty
  - report_reachability.csv — empty when no PROGRAM or IMPLICIT-MAIN units exist
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import read_csv

_FIXTURES = Path(__file__).parent / "fixtures_lib_only"
_RESULTS = Path(__file__).parent / "results_lib_only"


@pytest.fixture(scope="module")
def lib_results():
    _RESULTS.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forti4d.pipeline",
            "--project",
            str(_FIXTURES),
            "--output",
            str(_RESULTS),
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Pipeline failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    yield _RESULTS


def test_ambiguities_csv_is_empty(lib_results):
    rows = read_csv(lib_results / "dep_00_ambiguities.csv")
    assert rows == []


def test_clones_csv_is_empty(lib_results):
    rows = read_csv(lib_results / "report_clones.csv")
    assert rows == []


def test_reachability_csv_is_empty(lib_results):
    rows = read_csv(lib_results / "report_reachability.csv")
    assert rows == []
