"""Per-page resume: --skip-existing, stats v2, safe-reuse rules."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("paddleocr_vl_run_adapter", ADAPTER)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakePipeline:
    def __init__(self, *, fail_on=None, trace=None, **kwargs):
        self.fail_on = set(fail_on or [])
        self.trace = trace
        self.predicted = []

    def predict(self, image_path):
        name = Path(image_path).name
        self.predicted.append(name)
        if self.trace is not None:
            self.trace.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"boom {name}")
        return _Result(f"markdown for {name}\n")


class _Result:
    def __init__(self, text):
        self.markdown_text = text


@pytest.fixture()
def fake_module(monkeypatch):
    module = load_adapter()
    fake_pkg = type(sys)("paddleocr_vl_rocm")
    fake_pkg.PaddleOCRVLROCm = FakePipeline
    monkeypatch.setitem(sys.modules, "paddleocr_vl_rocm", fake_pkg)
    return module


def _image_dir(tmp_path, count=5, prefix="page"):
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    for i in range(count):
        (img_dir / f"{prefix}-{i:02d}.png").write_bytes(b"fake")
    return img_dir


def _run(fake_module, img_dir, out_dir, count=None, skip_existing=False):
    kwargs = dict(
        img_dir=img_dir,
        out_dir=out_dir,
        layout_model=str(out_dir / "layout"),
        server_url="http://127.0.0.1:8122/v1",
        api_model_name="model",
        vlm_backend="vllm-server",
    )
    if count is not None:
        kwargs["max_pages"] = count
    if skip_existing:
        kwargs["skip_existing"] = True
    return fake_module.run_lightweight_folder(**kwargs)


def test_first_run_writes_v2_stats_atomically(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 3)
    out_dir = tmp_path / "pred"
    summary = _run(fake_module, img_dir, out_dir)
    stats = json.loads((out_dir / "_run_stats.json").read_text(encoding="utf-8"))
    assert stats["schema_version"] == 2
    assert stats["selected_pages"] == 3
    assert stats["newly_processed"] == 3
    assert stats["skipped_existing"] == 0
    assert stats["count"] == 3
    assert stats["ok"] == 3
    assert len(stats["pages"]) == 3
    assert summary["newly_processed"] == 3
    assert summary["skipped_existing"] == 0


def test_resume_reuses_valid_predictions_without_rewriting(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 4)
    out_dir = tmp_path / "pred"
    trace = []
    fake_pipeline = FakePipeline(trace=trace)
    fake_module.__dict__["sys"].modules["paddleocr_vl_rocm"].PaddleOCRVLROCm = (
        lambda **kw: fake_pipeline
    )

    _run(fake_module, img_dir, out_dir, count=4)
    first_predicted = set(trace)
    assert first_predicted == {"page-00.png", "page-01.png", "page-02.png", "page-03.png"}
    mtimes = {}
    for path in out_dir.glob("*.md"):
        mtimes[path.name] = path.stat().st_mtime_ns

    trace.clear()
    summary = _run(fake_module, img_dir, out_dir, count=4, skip_existing=True)
    assert trace == [], "no page should be re-predicted on resume"
    assert summary["newly_processed"] == 0
    assert summary["skipped_existing"] == 4
    assert summary["ok"] == 4
    for name, mtime in mtimes.items():
        assert (out_dir / name).stat().st_mtime_ns == mtime, f"{name} was rewritten"


def test_resume_repairs_invalid_predictions(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 3)
    out_dir = tmp_path / "pred"
    _run(fake_module, img_dir, out_dir, count=3)
    (out_dir / "page-01.md").write_text("", encoding="utf-8")
    (out_dir / "page-02.md").write_bytes(b"\xff\xfe not utf8")
    summary = _run(fake_module, img_dir, out_dir, count=3, skip_existing=True)
    assert summary["newly_processed"] == 2
    assert summary["skipped_existing"] == 1
    assert summary["ok"] == 3
    assert (out_dir / "page-01.md").read_text(encoding="utf-8").strip() != ""
    assert (out_dir / "page-02.md").read_text(encoding="utf-8") == "markdown for page-02.png\n"


def test_resume_completes_missing_pages_after_partial_run(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 5)
    out_dir = tmp_path / "pred"
    first = _run(fake_module, img_dir, out_dir, count=2)
    assert first["newly_processed"] == 2
    second = _run(fake_module, img_dir, out_dir, count=5, skip_existing=True)
    assert second["newly_processed"] == 3
    assert second["skipped_existing"] == 2
    assert second["ok"] == 5
    stats = json.loads((out_dir / "_run_stats.json").read_text(encoding="utf-8"))
    assert stats["selected_pages"] == 5
    assert stats["newly_processed"] == 3
    assert stats["skipped_existing"] == 2
    assert len(stats["invocations"]) == 2
    assert stats["invocations"][0]["newly_processed"] == 2
    assert stats["invocations"][1]["newly_processed"] == 3
    assert stats["invocations"][1]["skipped_existing"] == 2


def test_failed_pages_are_retried_on_resume(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 3)
    out_dir = tmp_path / "pred"
    fake_pipeline = FakePipeline(fail_on={"page-01.png"})
    fake_module.__dict__["sys"].modules["paddleocr_vl_rocm"].PaddleOCRVLROCm = (
        lambda **kw: fake_pipeline
    )
    summary = _run(fake_module, img_dir, out_dir, count=3)
    assert summary["ok"] == 2
    assert summary["fail"] == 1
    assert (out_dir / "_errors.log").is_file()
    fake_pipeline.fail_on.clear()
    summary2 = _run(fake_module, img_dir, out_dir, count=3, skip_existing=True)
    assert summary2["ok"] == 3
    assert summary2["newly_processed"] == 1
    assert summary2["skipped_existing"] == 2
    assert summary2["failed_pages"] == []


def test_stats_v1_file_is_loaded_for_backward_compat(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 3)
    out_dir = tmp_path / "pred"
    out_dir.mkdir()
    (out_dir / "page-00.md").write_text("old content\n", encoding="utf-8")
    (out_dir / "_run_stats.json").write_text(
        json.dumps({"count": 3, "ok": 1, "fail": 2, "engine": "lightweight", "stats": []}),
        encoding="utf-8",
    )
    summary = _run(fake_module, img_dir, out_dir, count=3, skip_existing=True)
    assert summary["skipped_existing"] == 1
    assert summary["newly_processed"] == 2
    assert summary["ok"] == 3
    stats = json.loads((out_dir / "_run_stats.json").read_text(encoding="utf-8"))
    assert stats["schema_version"] == 2


def test_skip_existing_false_still_reprocesses_everything(tmp_path, fake_module):
    img_dir = _image_dir(tmp_path, 2)
    out_dir = tmp_path / "pred"
    _run(fake_module, img_dir, out_dir, count=2)
    summary = _run(fake_module, img_dir, out_dir, count=2, skip_existing=False)
    assert summary["newly_processed"] == 2
    assert summary["skipped_existing"] == 0
