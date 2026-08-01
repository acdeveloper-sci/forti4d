"""
pipeline.py
Executes the full static analysis pipeline in dependency order.

Usage:
  python pipeline.py                                      # run all steps
  python pipeline.py --list                               # show available steps
  python pipeline.py --project ../myproject --output out/ # set source and output dirs
  python pipeline.py --from complexity                    # start from a specific step
  python pipeline.py --only sloc consolidate              # run only these steps
  python pipeline.py --skip visual_graph                  # skip specific steps
  python pipeline.py --continue-on-error                  # don't stop on first failure
  python pipeline.py --quiet                              # only show step names and results

Library usage:
  import forti4d
  result = forti4d.run_pipeline(source_dir="...", results_dir="...")
  result.data["report_prioritization"]  # in-memory results of every step
"""

import argparse
import importlib
import io
import os
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path

from forti4d import config

# =============================================================================
# PIPELINE DEFINITION
# =============================================================================

# Each step: (name, module, description)
# Order reflects dependency constraints.
STEPS = [
    ("inventory", "forti4d.analyzers.inventory", "Build unit inventory from source files"),
    ("dependencies", "forti4d.analyzers.dependencies", "Build call graph and compute Fan-In/Fan-Out"),
    ("profiler", "forti4d.analyzers.profiler", "Classify statements and produce audit/ DEBUG files"),
    ("blocks", None, "Block topology analysis (one file per source, to output/)"),
    ("structure_analysis", "forti4d.analyzers.structure_analysis", "Classify files by architectural role"),
    ("cross_analysis", "forti4d.analyzers.cross_analysis", "Assign migration strategy per unit"),
    ("executive_summary", "forti4d.analyzers.executive_summary", "Generate executive summary"),
    ("complexity", "forti4d.analyzers.complexity", "Compute McCabe cyclomatic complexity"),
    ("common_blocks", "forti4d.analyzers.common_blocks", "Detect COMMON block coupling"),
    ("symbols", "forti4d.analyzers.symbols", "Extract variable/parameter/implicit symbols per unit"),
    ("derived_types", "forti4d.analyzers.derived_types", "Extract derived TYPE definitions and their components"),
    ("equivalences", "forti4d.analyzers.equivalences", "Detect EQUIVALENCE aliasing groups (union-find)"),
    ("reachability", "forti4d.analyzers.reachability", "Dead code detection from entry points"),
    ("sloc", "forti4d.analyzers.sloc", "Precise SLOC count per unit"),
    ("clones", "forti4d.analyzers.clones", "Detect identical/similar/diverged duplicate units"),
    ("consolidate", "forti4d.analyzers.consolidate", "Join all reports into report_consolidated.csv"),
    ("visual_graph", "forti4d.analyzers.visual_graph", "Generate call graph DOT files"),
    ("prioritization", "forti4d.analyzers.prioritization", "Compute composite risk score and rank units for migration"),
    ("html_report", "forti4d.analyzers.html_report", "Generate self-contained HTML report"),
]

STEP_NAMES = [s[0] for s in STEPS]


# =============================================================================
# RUN CONTEXT / RESULT
# =============================================================================


@dataclass
class RunContext:
    """State threaded through an in-process pipeline run."""

    source_dir: Path
    results_dir: Path
    data: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Outcome of a run_pipeline() call."""

    steps: list  # [(name, success, elapsed, error), ...]
    data: dict  # ctx.data at the end of the run — in-memory results of every step


# =============================================================================
# STEP RUNNERS
# =============================================================================


def _default_step_runner(module_path: str):
    def _run(ctx: RunContext) -> dict:
        mod = importlib.import_module(module_path)
        return mod.main(ctx.source_dir, ctx.results_dir, inputs=ctx.data)

    return _run


def _run_blocks_step(ctx: RunContext) -> dict:
    """In-process equivalent of the old subprocess-per-file block generation."""
    from forti4d.analyzers import block_analysis

    audit_path = ctx.results_dir / "audit"
    blocks_dir = ctx.results_dir / "blocks"

    if not audit_path.exists():
        raise RuntimeError(f"{audit_path} not found — run 'profiler' first")

    debug_files = sorted(audit_path.glob("*_DEBUG.csv"))
    if not debug_files:
        raise RuntimeError(f"No *_DEBUG.csv files found in {audit_path}")

    blocks_dir.mkdir(parents=True, exist_ok=True)

    errors = []
    for debug_file in debug_files:
        name = debug_file.name.replace("_DEBUG.csv", "")
        output = blocks_dir / f"{name}_blocks.txt"
        try:
            report = block_analysis.analyze_blocks_file(str(debug_file), results_dir=ctx.results_dir)
            if report is not None:
                output.write_text(report, encoding="utf-8")
        except Exception as exc:
            errors.append(f"{debug_file.name}: {str(exc)[:80]}")

    if errors:
        raise RuntimeError("; ".join(errors))

    return {}


def _run_visual_graph_step(ctx: RunContext) -> dict:
    """
    visual_graph.py keeps its argparse-based main() for standalone CLI use
    (--entry/--list/--use); the pipeline uses run()+write_graphs() instead
    (see visual_graph.py's migration notes).
    """
    from forti4d.analyzers import visual_graph

    data = visual_graph.run(ctx.source_dir, ctx.results_dir, inputs=ctx.data)
    visual_graph.write_graphs(ctx.results_dir, data)
    return data


_SPECIAL_RUNNERS = {
    "blocks": _run_blocks_step,
    "visual_graph": _run_visual_graph_step,
}


def run_step(name: str, module_path, ctx: RunContext, *, capture_output: bool = False) -> tuple:
    """
    Executes one step in-process. Returns (success, elapsed, error_repr, output).
    `output` is the captured stdout text if capture_output=True, else "".

    The try/except here replaces the fault isolation that subprocess used to
    provide — it's what makes --continue-on-error work without separate
    processes. Catches SystemExit too: several analyzers call sys.exit(1) on
    a missing required input, which used to just end the child process —
    in-process it must be caught here instead of unwinding the orchestrator.
    """
    t0 = time.time()
    runner = _SPECIAL_RUNNERS.get(name) or _default_step_runner(module_path)
    buf = io.StringIO() if capture_output else None

    try:
        if capture_output:
            with redirect_stdout(buf):
                result = runner(ctx)
        else:
            result = runner(ctx)
        if result:
            ctx.data.update(result)
        return True, time.time() - t0, "", (buf.getvalue() if buf else "")
    except (Exception, SystemExit) as exc:
        return False, time.time() - t0, f"{type(exc).__name__}: {exc}", (buf.getvalue() if buf else "")


# =============================================================================
# LIBRARY ENTRY POINT
# =============================================================================


def _filter_steps(from_step=None, only=None, skip=None) -> list:
    steps_to_run = STEPS[:]
    if from_step:
        idx = STEP_NAMES.index(from_step)
        steps_to_run = steps_to_run[idx:]
    if only:
        steps_to_run = [s for s in steps_to_run if s[0] in only]
    if skip:
        steps_to_run = [s for s in steps_to_run if s[0] not in skip]
    return steps_to_run


def run_pipeline(
    source_dir,
    results_dir,
    *,
    from_step=None,
    only=None,
    skip=None,
    continue_on_error=False,
    quiet=False,
    on_step_start=None,
    on_step_end=None,
) -> PipelineResult:
    """
    Runs the pipeline in-process — no subprocess, no print() calls of its
    own. Progress is only reported via the optional callbacks:
      on_step_start(name, description)
      on_step_end(name, success, elapsed, error, output)
    `quiet=True` captures each step's own stdout (passed to on_step_end as
    `output`) instead of letting it print live — same idea as the CLI's
    --quiet flag, useful for library callers that want to suppress the
    analyzers' own print() noise until Bloque 3 replaces it with logging.
    """
    ctx = RunContext(source_dir=Path(source_dir), results_dir=Path(results_dir))
    ctx.results_dir.mkdir(parents=True, exist_ok=True)

    steps_to_run = _filter_steps(from_step, only, skip)
    results = []

    for name, module_path, desc in steps_to_run:
        if on_step_start:
            on_step_start(name, desc)

        success, elapsed, error, output = run_step(name, module_path, ctx, capture_output=quiet)
        results.append((name, success, elapsed, error))

        if on_step_end:
            on_step_end(name, success, elapsed, error, output)

        if not success and not continue_on_error:
            break

    return PipelineResult(steps=results, data=ctx.data)


# =============================================================================
# CLI HELPERS
# =============================================================================

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
DIM = "\033[2m"


def fmt_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m {seconds % 60:.0f}s"


def print_step_header(idx: int, total: int, name: str, desc: str, quiet: bool):
    label = f"[{idx}/{total}] {name}"
    if quiet:
        print(f"{BOLD}{label}{RESET}  {DIM}{desc}{RESET}", end="  ", flush=True)
    else:
        print(f"\n{BOLD}{'─' * 60}{RESET}")
        print(f"{BOLD}{label}{RESET}  —  {desc}")
        print(f"{'─' * 60}")


def print_step_result(success: bool, elapsed: float, quiet: bool):
    icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    timing = f"{DIM}{fmt_time(elapsed)}{RESET}"
    if quiet:
        print(f"{icon} {timing}")
    else:
        status = f"{GREEN}OK{RESET}" if success else f"{RED}FAILED{RESET}"
        print(f"\n  {icon} {status}  {timing}")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Run the Fortran static analysis pipeline.")
    parser.add_argument("--list", action="store_true", help="List available steps and exit.")
    parser.add_argument(
        "--project", metavar="DIR", help="Path to the Fortran source directory to analyze (sets FORT_SRC)."
    )
    parser.add_argument(
        "--output", metavar="DIR", help="Directory where all output files will be written (sets FORT_OUT)."
    )
    parser.add_argument("--from", dest="from_step", metavar="STEP", help="Start execution from this step (inclusive).")
    parser.add_argument("--only", nargs="+", metavar="STEP", help="Run only these steps.")
    parser.add_argument("--skip", nargs="+", metavar="STEP", help="Skip these steps.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue to next step even if a step fails.")
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress script output — show only step names and results."
    )
    args = parser.parse_args()

    # Resolve source/results dirs (flag > env var > default) and mirror them
    # into os.environ for any code that still reads FORT_SRC/FORT_OUT directly.
    source_dir, results_dir = config.resolve_paths(args.project, args.output)
    os.environ["FORT_SRC"] = str(source_dir)
    os.environ["FORT_OUT"] = str(results_dir)

    # Validate source path (skip for --list)
    if not args.list:
        source_dir = source_dir.resolve()
        if not source_dir.exists():
            print(f"\nERROR: Source directory not found: {source_dir}")
            print("  Set --project <DIR> or the FORT_SRC environment variable.")
            sys.exit(1)
        if not source_dir.is_dir():
            print(f"\nERROR: Source path is not a directory: {source_dir}")
            sys.exit(1)
        os.environ["FORT_SRC"] = str(source_dir)

    # --list
    if args.list:
        print(f"\n{'Step':<22} {'Module':<38} Description")
        print("─" * 90)
        for name, module_path, desc in STEPS:
            m = module_path if module_path else "block_analysis (in-process, batch)"
            print(f"  {name:<20} {m:<38} {desc}")
        print()
        print(f"  FORT_SRC  →  {source_dir}")
        print(f"  FORT_OUT  →  {results_dir}")
        print()
        return

    # Validate --from
    if args.from_step and args.from_step not in STEP_NAMES:
        print(f"ERROR: Unknown step '{args.from_step}'. Use --list to see available steps.")
        sys.exit(1)

    # Validate --only / --skip
    for name in (args.only or []) + (args.skip or []):
        if name not in STEP_NAMES:
            print(f"ERROR: Unknown step '{name}'. Use --list to see available steps.")
            sys.exit(1)

    steps_to_run = _filter_steps(args.from_step, args.only, args.skip)
    if not steps_to_run:
        print("No steps to run after applying filters.")
        return

    # Header
    print(f"\n{BOLD}=== Fortran Static Analysis Pipeline ==={RESET}")
    print(f"Project : {source_dir}")
    print(f"Output  : {results_dir}")
    print(f"Steps   : {len(steps_to_run)}")
    print()

    total = len(steps_to_run)
    counter = {"i": 0}

    def on_step_start(name, desc):
        counter["i"] += 1
        print_step_header(counter["i"], total, name, desc, args.quiet)

    def on_step_end(name, success, elapsed, error, output):
        if not success and args.quiet and output:
            for line in output.strip().splitlines()[-10:]:
                print(f"    {RED}{line}{RESET}")
        print_step_result(success, elapsed, args.quiet)
        if not success and not args.continue_on_error:
            print(
                f"\n{RED}Pipeline stopped at '{name}'. " f"Use --continue-on-error to proceed past failures.{RESET}\n"
            )

    t_global = time.time()
    result = run_pipeline(
        source_dir,
        results_dir,
        from_step=args.from_step,
        only=args.only,
        skip=args.skip,
        continue_on_error=args.continue_on_error,
        quiet=args.quiet,
        on_step_start=on_step_start,
        on_step_end=on_step_end,
    )
    total_time = time.time() - t_global

    # Summary
    n_ok = sum(1 for _, s, _, _ in result.steps if s)
    n_fail = sum(1 for _, s, _, _ in result.steps if not s)

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}Summary{RESET}  —  {fmt_time(total_time)} total")
    print(f"{'─' * 60}")

    for name, success, elapsed, _ in result.steps:
        icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
        print(f"  {icon}  {name:<22} {DIM}{fmt_time(elapsed)}{RESET}")

    print()
    if n_fail == 0:
        print(f"{GREEN}{BOLD}All {n_ok} steps completed successfully.{RESET}")
    else:
        print(f"{RED}{BOLD}{n_fail} step(s) failed.{RESET}  {n_ok} succeeded.")
    print()


if __name__ == "__main__":
    main()
