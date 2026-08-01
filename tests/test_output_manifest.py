"""
test_output_manifest.py
Byte-for-byte regression gate for the in-process library refactor
(feature/v1.0.0-library-api). Hashes every file under tests/results/ and
compares against tests/output_manifest.json, generated once against the
pre-refactor pipeline. Complements the semantic CSV assertions in the other
test modules, which only check partial content, not the full output tree.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent / "output_manifest.json"

# html_report.py embeds datetime.now() in report.html — normalize it so the
# hash reflects content, not generation time.
_TIMESTAMP_RE = re.compile(rb"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


def compute_manifest(results_dir: Path) -> dict[str, str]:
    manifest = {}
    for path in sorted(results_dir.rglob("*")):
        if path.is_file():
            rel = path.relative_to(results_dir).as_posix()
            if rel == "forti4d.log":
                # Every line carries a non-reproducible timestamp — unlike
                # report.html's single datetime.now(), not worth normalizing.
                continue
            content = path.read_bytes()
            if rel == "report.html":
                content = _TIMESTAMP_RE.sub(b"TIMESTAMP", content)
            manifest[rel] = hashlib.sha256(content).hexdigest()
    return manifest


def test_output_matches_manifest(pipeline_results):
    actual = compute_manifest(pipeline_results)
    expected = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert actual == expected
