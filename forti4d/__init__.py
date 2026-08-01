"""
forti4d — Fortran static analysis toolkit (MI4D model).
"""

from forti4d.pipeline import PipelineResult, RunContext, run_pipeline

__version__ = "0.7.0"

__all__ = ["run_pipeline", "RunContext", "PipelineResult", "__version__"]
