"""
test_logging_behavior.py
Bloque 3 Fase 4: end-to-end behavior tests for the logging semantics
introduced in this block. Everything runs via subprocess (not caplog,
which targets stdlib logging) — loguru is a process-global singleton, so
isolating each scenario in its own process avoids cross-test sink
contamination.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _run_cli(output_dir, *extra_args):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "forti4d.pipeline",
            "--project",
            str(FIXTURES_DIR),
            "--output",
            str(output_dir),
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )


def test_library_is_silent_by_default(tmp_path):
    """run_pipeline() without configure_logging() must not write a log
    file or emit anything to stderr — library callers stay silent by
    default (forti4d/__init__.py disables the "forti4d" logger namespace
    on import)."""
    script = (
        "import forti4d\n"
        f"forti4d.run_pipeline(source_dir={str(FIXTURES_DIR)!r}, results_dir={str(tmp_path)!r}, only=['inventory'])\n"
    )
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (tmp_path / "forti4d.log").exists()
    assert proc.stderr == ""


def test_cli_configures_logging_by_default(tmp_path):
    """The CLI always calls configure_logging() — forti4d.log must exist
    and contain both INFO and DEBUG lines (the file sink always gets full
    detail, regardless of console level)."""
    proc = _run_cli(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    log_path = tmp_path / "forti4d.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "| INFO     |" in content
    assert "| DEBUG    |" in content


def test_quiet_raises_console_level_but_not_file_level(tmp_path):
    """--quiet's redefined meaning: console only shows WARNING+, but the
    log file is unaffected — still gets full DEBUG+ either way."""
    normal_dir = tmp_path / "normal"
    quiet_dir = tmp_path / "quiet"

    normal = _run_cli(normal_dir)
    quiet = _run_cli(quiet_dir, "--quiet")
    assert normal.returncode == 0, normal.stdout + normal.stderr
    assert quiet.returncode == 0, quiet.stdout + quiet.stderr

    assert "SUCCESS" in normal.stderr
    assert "SUCCESS" not in quiet.stderr

    normal_log = (normal_dir / "forti4d.log").read_text(encoding="utf-8")
    quiet_log = (quiet_dir / "forti4d.log").read_text(encoding="utf-8")
    assert "| DEBUG    |" in normal_log
    assert "| DEBUG    |" in quiet_log


def test_log_file_override_path(tmp_path):
    """--log-file overrides the default <output>/forti4d.log location."""
    custom_log = tmp_path / "custom" / "run.log"
    out_dir = tmp_path / "out"
    proc = _run_cli(out_dir, "--log-file", str(custom_log))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert custom_log.exists()
    assert not (out_dir / "forti4d.log").exists()


def test_no_log_file_disables_file_sink(tmp_path):
    """--no-log-file skips the file sink entirely — no log file anywhere,
    console output unaffected."""
    proc = _run_cli(tmp_path, "--no-log-file")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (tmp_path / "forti4d.log").exists()
    assert "SUCCESS" in proc.stderr
