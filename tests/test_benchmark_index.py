"""Benchmark registry: index/schema invariants and generated-table drift."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE = REPO_ROOT / "scripts" / "validate_benchmark_index.py"
RENDER = REPO_ROOT / "scripts" / "render_benchmark_tables.py"

START = "<!-- benchmark-table:start -->"
END = "<!-- benchmark-table:end -->"


def test_index_passes_validation():
    result = subprocess.run(
        [sys.executable, str(VALIDATE), "--root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BENCHMARK INDEX OK" in result.stdout


def test_index_has_no_clean_room_claims():
    entries = json.loads((REPO_ROOT / "benchmarks" / "index.json").read_text(encoding="utf-8"))
    for entry in entries:
        assert entry["run_type"] != "clean-room", (
            f"{entry['id']} claims clean-room without a fresh-checkout full run"
        )
        assert entry["run_type"] != "independent"
        assert "clean-room PASS" not in json.dumps(entry)


def test_2026_08_03_full_run_marked_validated_resumed():
    entries = json.loads((REPO_ROOT / "benchmarks" / "index.json").read_text(encoding="utf-8"))
    row = next(e for e in entries if e["id"] == "paddleocr-vl-rocm-full-1651-2026-08-03")
    assert row["run_type"] == "resumed"
    assert "clean-room" not in row["evidence_level"].lower().split(".")[0]


def test_generated_table_is_in_sync_with_index():
    """Rendering must be a no-op: the committed README tables equal the output
    of the renderer (this is the CI drift check, run locally too)."""
    entries = json.loads((REPO_ROOT / "benchmarks" / "index.json").read_text(encoding="utf-8"))
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_benchmark_tables", RENDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected_table = module.render_table(entries)
    for readme in ("README.md", "README.zh-CN.md"):
        text = (REPO_ROOT / readme).read_text(encoding="utf-8")
        assert START in text and END in text, f"{readme} missing table markers"
        block = text.split(START, 1)[1].split(END, 1)[0].strip()
        assert block == expected_table, f"{readme} benchmark table drifted from index.json"


def test_evidence_documents_exist():
    entries = json.loads((REPO_ROOT / "benchmarks" / "index.json").read_text(encoding="utf-8"))
    for entry in entries:
        doc = REPO_ROOT / entry["evidence_document"]
        assert doc.is_file(), f"{entry['id']} evidence missing: {doc}"
