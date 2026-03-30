"""
conftest.py
Session-scoped fixture that runs the full forti4d pipeline once against
the synthetic Fortran corpus in tests/fixtures/, writing results to
tests/results/. All individual test modules share this single run.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RESULTS_DIR  = Path(__file__).parent / "results"


@pytest.fixture(scope="session", autouse=True)
def pipeline_results():
    """Run the full pipeline once; yield the results directory path."""
    RESULTS_DIR.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            sys.executable, "-m", "forti4d.pipeline",
            "--project", str(FIXTURES_DIR),
            "--output", str(RESULTS_DIR),
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Pipeline failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    yield RESULTS_DIR


# ---------------------------------------------------------------------------
# Helpers available to all test modules
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    """Read a CSV file and return a list of row dicts (UTF-8 with BOM)."""
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def rows_by(rows: list[dict], **filters) -> list[dict]:
    """Filter rows where all key=value conditions match (case-insensitive values)."""
    result = rows
    for key, val in filters.items():
        result = [r for r in result if r.get(key, "").strip().upper() == str(val).upper()]
    return result
