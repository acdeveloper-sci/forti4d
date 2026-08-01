"""
forti4d — Fortran static analysis toolkit (MI4D model).
"""

from loguru import logger

# Library-silent-by-default: nothing forti4d logs is emitted unless a
# consumer explicitly opts in — see forti4d.lib.logging_setup.configure_logging().
logger.disable("forti4d")

from forti4d.lib.logging_setup import configure_logging
from forti4d.pipeline import PipelineResult, RunContext, run_pipeline

__version__ = "0.7.0"

__all__ = ["run_pipeline", "RunContext", "PipelineResult", "configure_logging", "__version__"]
