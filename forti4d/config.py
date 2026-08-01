"""
config.py
Central configuration of the Fortran static analysis toolkit.

The default values ​​can be overridden with environment variables:
  FORT_SRC — path to the directory containing the Fortran source code to be analyzed
  FORT_OUT — directory where all reports and output files are written

Example of individual usage:
  FORT_SRC=/path/to/project FORT_OUT=results/ python3 inventory.py

When using pipeline.py, these values ​​are automatically propagated:
  python3 pipeline.py --project /path/to/project --output results/
"""

import os
from pathlib import Path

# Directory with the Fortran source code to be analyzed
CODE_PATH = Path(os.environ.get("FORT_SRC", "tests/fixtures/"))

# Root directory where all output files are written
RESULTS_PATH = Path(os.environ.get("FORT_OUT", "results/"))


def resolve_paths(source=None, results=None):
    """
    Resolve (source_dir, results_dir) at call time, not at import time.
    Priority: explicit argument > FORT_SRC/FORT_OUT env var > default.

    CODE_PATH/RESULTS_PATH above stay frozen at import — they only work
    correctly for a single project per process. This is the entry point
    for code that needs to run against different projects within the
    same process (library/orchestrator use).
    """
    src = Path(source) if source is not None else Path(os.environ.get("FORT_SRC", "tests/fixtures/"))
    out = Path(results) if results is not None else Path(os.environ.get("FORT_OUT", "results/"))
    return src, out
