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
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# =============================================================================
# PIPELINE DEFINITION
# =============================================================================

# Each step: (name, script, description)
# Order reflects dependency constraints.
_HERE = Path(__file__).parent

STEPS = [
    ("inventory", "analyzers/inventory.py", "Build unit inventory from source files"),
    ("dependencies", "analyzers/dependencies.py", "Build call graph and compute Fan-In/Fan-Out"),
    ("profiler", "analyzers/profiler.py", "Classify statements and produce audit/ DEBUG files"),
    ("blocks", None, "Block topology analysis (one file per source, to output/)"),
    ("structure_analysis", "analyzers/structure_analysis.py", "Classify files by architectural role"),
    ("cross_analysis", "analyzers/cross_analysis.py", "Assign migration strategy per unit"),
    ("executive_summary", "analyzers/executive_summary.py", "Generate executive summary"),
    ("complexity", "analyzers/complexity.py", "Compute McCabe cyclomatic complexity"),
    ("common_blocks", "analyzers/common_blocks.py", "Detect COMMON block coupling"),
    ("symbols", "analyzers/symbols.py", "Extract variable/parameter/implicit symbols per unit"),
    ("derived_types", "analyzers/derived_types.py", "Extract derived TYPE definitions and their components"),
    ("equivalences", "analyzers/equivalences.py", "Detect EQUIVALENCE aliasing groups (union-find)"),
    ("reachability", "analyzers/reachability.py", "Dead code detection from entry points"),
    ("sloc", "analyzers/sloc.py", "Precise SLOC count per unit"),
    ("clones", "analyzers/clones.py", "Detect identical/similar/diverged duplicate units"),
    ("consolidate", "analyzers/consolidate.py", "Join all reports into report_consolidated.csv"),
    ("visual_graph", "analyzers/visual_graph.py", "Generate call graph DOT files"),
    ("prioritization", "analyzers/prioritization.py", "Compute composite risk score and rank units for migration"),
    ("html_report", "analyzers/html_report.py", "Generate self-contained HTML report"),
]

STEP_NAMES = [s[0] for s in STEPS]


# =============================================================================
# STEP RUNNERS
# =============================================================================


def run_script(script: str, quiet: bool, env: dict) -> tuple:
    """
    Runs a Python script as a subprocess.
    Returns (success: bool, elapsed: float, output: str).
    """
    cmd = [sys.executable, str(_HERE / script)]
    t0 = time.time()

    if quiet:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        output = result.stdout + result.stderr
    else:
        result = subprocess.run(cmd, env=env)
        output = ""

    elapsed = time.time() - t0
    return result.returncode == 0, elapsed, output


def run_blocks(quiet: bool, env: dict) -> tuple:
    """
    Batch-runs block_analysis.py for every *_DEBUG.csv in <output>/audit/.
    Output is written to <output>/blocks/<name>_blocks.txt.
    """
    audit_path = Path(env.get("FORT_OUT", "results/")) / "audit"
    blocks_dir = Path(env.get("FORT_OUT", "results/")) / "blocks"

    if not audit_path.exists():
        return False, 0.0, f"{audit_path} not found — run 'profiler' first"

    debug_files = sorted(audit_path.glob("*_DEBUG.csv"))
    if not debug_files:
        return False, 0.0, f"No *_DEBUG.csv files found in {audit_path}"

    blocks_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    errors = []

    for debug_file in debug_files:
        name = debug_file.name.replace("_DEBUG.csv", "")
        output = blocks_dir / f"{name}_blocks.txt"

        cmd = [sys.executable, str(_HERE / "analyzers/block_analysis.py"), str(debug_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode == 0:
            output.write_text(result.stdout, encoding="utf-8")
        else:
            errors.append(f"{debug_file.name}: {result.stderr.strip()[:80]}")

    elapsed = time.time() - t0
    n = len(debug_files)
    e = len(errors)

    if not quiet:
        print(f"  Processed {n} files → {blocks_dir}  ({e} errors)")

    if errors:
        return False, elapsed, "\n".join(errors)
    return True, elapsed, f"{n} files processed"


# =============================================================================
# HELPERS
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
# MAIN
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

    # Build subprocess environment — inherit current env, then override
    env = os.environ.copy()
    if args.project:
        env["FORT_SRC"] = str(Path(args.project).resolve())
    if args.output:
        env["FORT_OUT"] = str(Path(args.output))

    # Validate source path (skip for --list)
    if not args.list:
        src_path = Path(env.get("FORT_SRC", "tests/fixtures/")).resolve()
        if not src_path.exists():
            print(f"\nERROR: Source directory not found: {src_path}")
            print("  Set --project <DIR> or the FORT_SRC environment variable.")
            sys.exit(1)
        if not src_path.is_dir():
            print(f"\nERROR: Source path is not a directory: {src_path}")
            sys.exit(1)
        env["FORT_SRC"] = str(src_path)

    # --list
    if args.list:
        fort_src = env.get("FORT_SRC", "tests/fixtures/")
        fort_out = env.get("FORT_OUT", "results/")
        print(f"\n{'Step':<22} {'Script':<28} Description")
        print("─" * 78)
        for name, script, desc in STEPS:
            s = script if script else "block_analysis.py (batch)"
            print(f"  {name:<20} {s:<28} {desc}")
        print()
        print(f"  FORT_SRC  →  {fort_src}")
        print(f"  FORT_OUT  →  {fort_out}")
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

    # Build the list of steps to execute
    steps_to_run = STEPS[:]

    if args.from_step:
        idx = STEP_NAMES.index(args.from_step)
        steps_to_run = steps_to_run[idx:]

    if args.only:
        steps_to_run = [s for s in steps_to_run if s[0] in args.only]

    if args.skip:
        steps_to_run = [s for s in steps_to_run if s[0] not in args.skip]

    if not steps_to_run:
        print("No steps to run after applying filters.")
        return

    # Header
    fort_src = env.get("FORT_SRC", "../athys/mercedes/")
    fort_out = env.get("FORT_OUT", "results/")
    print(f"\n{BOLD}=== Fortran Static Analysis Pipeline ==={RESET}")
    print(f"Project : {fort_src}")
    print(f"Output  : {fort_out}")
    print(f"Steps   : {len(steps_to_run)}")
    print()

    # Execute
    total = len(steps_to_run)
    results = []  # (name, success, elapsed)
    t_global = time.time()

    for i, (name, script, desc) in enumerate(steps_to_run, 1):
        print_step_header(i, total, name, desc, args.quiet)

        if script is None:
            # Special step: bloques batch
            success, elapsed, msg = run_blocks(args.quiet, env)
            if not args.quiet and msg:
                print(f"  {msg}")
        else:
            if not (_HERE / script).exists():
                print(f"{RED}  Script not found: {script}{RESET}")
                success, elapsed = False, 0.0
            else:
                success, elapsed, output = run_script(script, args.quiet, env)
                if not success and args.quiet and output:
                    # Show captured error output even in quiet mode
                    for line in output.strip().splitlines()[-10:]:
                        print(f"    {RED}{line}{RESET}")

        print_step_result(success, elapsed, args.quiet)
        results.append((name, success, elapsed))

        if not success and not args.continue_on_error:
            print(
                f"\n{RED}Pipeline stopped at '{name}'. " f"Use --continue-on-error to proceed past failures.{RESET}\n"
            )
            break

    # Summary
    total_time = time.time() - t_global
    n_ok = sum(1 for _, s, _ in results if s)
    n_fail = sum(1 for _, s, _ in results if not s)

    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}Summary{RESET}  —  {fmt_time(total_time)} total")
    print(f"{'─' * 60}")

    for name, success, elapsed in results:
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
