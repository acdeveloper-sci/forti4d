"""
pipeline.py
Executes the full static analysis pipeline in dependency order.

Usage:
  python pipeline.py                        # run all steps
  python pipeline.py --list                 # show available steps
  python pipeline.py --from complejidad     # start from a specific step
  python pipeline.py --only sloc consolidar # run only these steps
  python pipeline.py --skip grafo_visual    # skip specific steps
  python pipeline.py --continue-on-error    # don't stop on first failure
  python pipeline.py --quiet                # only show step names and results
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# =============================================================================
# PIPELINE DEFINITION
# =============================================================================

# Each step: (name, script, description)
# Order reflects dependency constraints.
STEPS = [
    ("inventario",          "inventario.py",          "Build unit inventory from source files"),
    ("dependencias",        "dependencias.py",         "Build call graph and compute Fan-In/Fan-Out"),
    ("perfilador",          "perfilador.py",           "Classify statements and produce audit/ DEBUG files"),
    ("bloques",             None,                      "Block topology analysis (one file per source, to audit/)"),
    ("analisis_estructura", "analisis_estructura.py",  "Classify files by architectural role"),
    ("analisis_cruzado",    "analisis_cruzado.py",     "Assign migration strategy per unit"),
    ("resumen_ejecutivo",   "resumen_ejecutivo.py",    "Generate executive summary"),
    ("complejidad",         "complejidad.py",          "Compute McCabe cyclomatic complexity"),
    ("common_blocks",       "common_blocks.py",        "Detect COMMON block coupling"),
    ("alcanzabilidad",      "alcanzabilidad.py",       "Dead code detection from entry points"),
    ("sloc",                "sloc.py",                 "Precise SLOC count per unit"),
    ("consolidar",          "consolidar.py",           "Join all reports into reporte_consolidado.csv"),
    ("grafo_visual",        "grafo_visual.py",         "Generate call graph DOT files"),
]

STEP_NAMES = [s[0] for s in STEPS]

# audit/ directory — written by perfilador, read by bloques/complejidad/common_blocks
RUTA_AUDIT = Path("audit")


# =============================================================================
# STEP RUNNERS
# =============================================================================

def run_script(script: str, quiet: bool) -> tuple:
    """
    Runs a Python script as a subprocess.
    Returns (success: bool, elapsed: float, output: str).
    """
    cmd = [sys.executable, script]
    t0  = time.time()

    if quiet:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + result.stderr
    else:
        result = subprocess.run(cmd)
        output = ""

    elapsed = time.time() - t0
    return result.returncode == 0, elapsed, output


def run_bloques(quiet: bool) -> tuple:
    """
    Batch-runs analisis_bloques_v8.py for every *_DEBUG.csv in audit/.
    Output is written to bloques/<name>_bloques.txt.
    """
    if not RUTA_AUDIT.exists():
        return False, 0.0, f"audit/ directory not found — run 'perfilador' first"

    debug_files = sorted(RUTA_AUDIT.glob("*_DEBUG.csv"))
    if not debug_files:
        return False, 0.0, "No *_DEBUG.csv files found in audit/"

    bloques_dir = Path("bloques")
    bloques_dir.mkdir(exist_ok=True)

    t0      = time.time()
    errores = []

    for debug_file in debug_files:
        nombre = debug_file.name.replace("_DEBUG.csv", "")
        salida = bloques_dir / f"{nombre}_bloques.txt"

        cmd = [sys.executable, "analisis_bloques_v8.py", str(debug_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            salida.write_text(result.stdout, encoding="utf-8")
        else:
            errores.append(f"{debug_file.name}: {result.stderr.strip()[:80]}")

    elapsed = time.time() - t0
    n       = len(debug_files)
    e       = len(errores)

    if not quiet:
        print(f"  Processed {n} files → bloques/  ({e} errors)")

    if errores:
        return False, elapsed, "\n".join(errores)
    return True, elapsed, f"{n} files processed"


# =============================================================================
# HELPERS
# =============================================================================

RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
BOLD   = "\033[1m"
DIM    = "\033[2m"


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
    icon   = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
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
    parser = argparse.ArgumentParser(
        description="Run the Fortran static analysis pipeline."
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available steps and exit."
    )
    parser.add_argument(
        "--from", dest="from_step", metavar="STEP",
        help="Start execution from this step (inclusive)."
    )
    parser.add_argument(
        "--only", nargs="+", metavar="STEP",
        help="Run only these steps."
    )
    parser.add_argument(
        "--skip", nargs="+", metavar="STEP",
        help="Skip these steps."
    )
    parser.add_argument(
        "--continue-on-error", action="store_true",
        help="Continue to next step even if a step fails."
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress script output — show only step names and results."
    )
    args = parser.parse_args()

    # --list
    if args.list:
        print(f"\n{'Step':<22} {'Script':<28} Description")
        print("─" * 78)
        for name, script, desc in STEPS:
            s = script if script else "analisis_bloques_v8.py (batch)"
            print(f"  {name:<20} {s:<28} {desc}")
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
    print(f"\n{BOLD}=== Fortran Static Analysis Pipeline ==={RESET}")
    print(f"Steps to run: {len(steps_to_run)}")
    print()

    # Execute
    total    = len(steps_to_run)
    results  = []   # (name, success, elapsed)
    t_global = time.time()

    for i, (name, script, desc) in enumerate(steps_to_run, 1):
        print_step_header(i, total, name, desc, args.quiet)

        if script is None:
            # Special step: bloques batch
            success, elapsed, msg = run_bloques(args.quiet)
            if not args.quiet and msg:
                print(f"  {msg}")
        else:
            if not Path(script).exists():
                print(f"{RED}  Script not found: {script}{RESET}")
                success, elapsed = False, 0.0
            else:
                success, elapsed, output = run_script(script, args.quiet)
                if not success and args.quiet and output:
                    # Show captured error output even in quiet mode
                    for line in output.strip().splitlines()[-10:]:
                        print(f"    {RED}{line}{RESET}")

        print_step_result(success, elapsed, args.quiet)
        results.append((name, success, elapsed))

        if not success and not args.continue_on_error:
            print(f"\n{RED}Pipeline stopped at '{name}'. "
                  f"Use --continue-on-error to proceed past failures.{RESET}\n")
            break

    # Summary
    total_time = time.time() - t_global
    n_ok   = sum(1 for _, s, _ in results if s)
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
