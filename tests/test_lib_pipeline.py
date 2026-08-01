"""
test_lib_pipeline.py
Parity test: forti4d.run_pipeline() (in-process library call) must produce
the exact same output tree as the CLI (subprocess), for the same corpus.
This is the definitive proof that "library mode == CLI mode".
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import forti4d

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _hash_tree(root: Path) -> dict[str, str]:
    manifest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            manifest[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def test_library_matches_cli(tmp_path):
    lib_dir = tmp_path / "lib"
    cli_dir = tmp_path / "cli"

    result = forti4d.run_pipeline(source_dir=FIXTURES_DIR, results_dir=lib_dir, quiet=True)
    assert all(success for _, success, _, _ in result.steps), result.steps

    proc = subprocess.run(
        [sys.executable, "-m", "forti4d.pipeline", "--project", str(FIXTURES_DIR), "--output", str(cli_dir), "--quiet"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    lib_manifest = _hash_tree(lib_dir)
    cli_manifest = _hash_tree(cli_dir)

    # report.html embeds a generation timestamp — exclude from strict comparison.
    lib_manifest.pop("report.html", None)
    cli_manifest.pop("report.html", None)

    assert lib_manifest == cli_manifest
