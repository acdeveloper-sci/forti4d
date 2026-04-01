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
