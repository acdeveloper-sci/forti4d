"""
test_parallel_parity.py
Parity test for Bloque 2 (concurrency): running with workers>1 must
produce byte-identical output to the sequential default (workers=1), for
the three parallelized steps (inventory, profiler, blocks) in isolation
and for the full 19-step pipeline (confirms ctx.data["audit"] still feeds
the 5 downstream in-memory consumers correctly when profiler runs parallel).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import forti4d
from forti4d.analyzers.inventory import analyze_inventory
from forti4d.analyzers.profiler import analyze_density

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _hash_tree(root: Path) -> dict[str, str]:
    manifest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            manifest[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def test_parallel_matches_sequential_scoped(tmp_path):
    seq_dir, par_dir = tmp_path / "seq", tmp_path / "par"

    seq = forti4d.run_pipeline(
        source_dir=FIXTURES_DIR, results_dir=seq_dir, only=["inventory", "profiler", "blocks"], workers=1, quiet=True
    )
    par = forti4d.run_pipeline(
        source_dir=FIXTURES_DIR, results_dir=par_dir, only=["inventory", "profiler", "blocks"], workers=2, quiet=True
    )
    assert all(success for _, success, _, _ in seq.steps), seq.steps
    assert all(success for _, success, _, _ in par.steps), par.steps

    assert _hash_tree(seq_dir) == _hash_tree(par_dir)


def test_parallel_matches_sequential_full_pipeline(tmp_path):
    seq_dir, par_dir = tmp_path / "seq", tmp_path / "par"

    seq = forti4d.run_pipeline(source_dir=FIXTURES_DIR, results_dir=seq_dir, workers=1, quiet=True)
    par = forti4d.run_pipeline(source_dir=FIXTURES_DIR, results_dir=par_dir, workers=2, quiet=True)
    assert all(success for _, success, _, _ in seq.steps), seq.steps
    assert all(success for _, success, _, _ in par.steps), par.steps

    seq_manifest = _hash_tree(seq_dir)
    par_manifest = _hash_tree(par_dir)

    # report.html embeds a generation timestamp — exclude from strict comparison.
    seq_manifest.pop("report.html", None)
    par_manifest.pop("report.html", None)

    assert seq_manifest == par_manifest

    # The 5 analyzers migrated in Bloque 1 that consume ctx.data["audit"] in
    # memory must have received identical data whether profiler ran
    # sequentially or in parallel.
    for key in ("report_complexity", "common_usage", "symbol_variables", "type_definitions", "equivalences"):
        assert seq.data[key] == par.data[key], key


def test_inventory_workers_parity():
    assert analyze_inventory(FIXTURES_DIR, workers=1) == analyze_inventory(FIXTURES_DIR, workers=2)


def test_profiler_workers_parity(tmp_path):
    # profiler needs inventory_report.csv on disk (or in-memory rows) first.
    inv_rows = analyze_inventory(FIXTURES_DIR, workers=1)
    results_dir_seq = tmp_path / "seq"
    results_dir_par = tmp_path / "par"

    data_seq = analyze_density(FIXTURES_DIR, results_dir_seq, inputs={"inventory_report": inv_rows}, workers=1)
    data_par = analyze_density(FIXTURES_DIR, results_dir_par, inputs={"inventory_report": inv_rows}, workers=2)

    assert data_seq["report_density"] == data_par["report_density"]
    assert data_seq["audit"] == data_par["audit"]
