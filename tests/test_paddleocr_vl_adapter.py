from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py"


def load_adapter():
    spec = importlib.util.spec_from_file_location("paddleocr_vl_run_adapter", ADAPTER)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_engine_is_lightweight(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "pred"
    img_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")
    calls = []

    def fake_lightweight(**kwargs):
        calls.append(kwargs)
        return {"count": 1, "ok": 1, "fail": 0, "engine": "lightweight"}

    monkeypatch.setattr(adapter, "run_lightweight_folder", fake_lightweight)

    result = adapter.run_adapter(img_dir, out_dir, server_url="http://127.0.0.1:8111/v1")

    assert result["engine"] == "lightweight"
    assert calls[0]["img_dir"] == img_dir
    assert calls[0]["out_dir"] == out_dir


def test_official_engine_is_explicit(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "pred"
    img_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")
    calls = []

    def fake_official(**kwargs):
        calls.append(kwargs)
        return {"count": 1, "ok": 1, "fail": 0, "engine": "official"}

    monkeypatch.setattr(adapter, "run_official_folder", fake_official)

    result = adapter.run_adapter(
        img_dir,
        out_dir,
        server_url="http://127.0.0.1:8111/v1",
        engine="official",
    )

    assert result["engine"] == "official"
    assert calls[0]["img_dir"] == img_dir
    assert calls[0]["out_dir"] == out_dir


def test_expected_md_name_preserves_stem():
    adapter = load_adapter()

    assert adapter.expected_md_name("scan.JPG") == "scan.md"
    assert adapter.expected_md_name("abc.page-01.png") == "abc.page-01.md"


def test_official_result_to_markdown_reads_markdown_attribute():
    adapter = load_adapter()

    class Result:
        markdown = "# title\n"

    assert adapter._official_result_to_markdown(Result()) == "# title\n"
