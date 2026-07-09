from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "run_adapter.py"
VLM_SETUP = REPO_ROOT / "adapters" / "paddleocr-vl-1.6" / "01-vlm-server" / "setup.ps1"


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


def test_official_result_to_markdown_reads_paddlex_markdown_dict():
    adapter = load_adapter()

    class Result:
        markdown = {"markdown_texts": "# title\n"}

    assert adapter._official_result_to_markdown(Result()) == "# title\n"


def test_official_result_to_markdown_prefers_pretty_false_export():
    adapter = load_adapter()
    calls = []

    class Result:
        markdown = {"markdown_texts": '<div style="text-align: center;">pretty</div>\n'}

        def _to_markdown(self, pretty=True, show_formula_number=False):
            calls.append(pretty)
            return {"markdown_texts": "plain\n"}

    assert adapter._official_result_to_markdown(Result()) == "plain\n"
    assert calls == [False]


def test_official_markdown_normalizes_centered_html_wrappers():
    adapter = load_adapter()

    markdown = (
        '<div style="text-align: center;"><img src="imgs/fig.jpg" '
        'alt="Image" width="45%" /></div>\n\n'
        '<div style="text-align: center;">Fig. 1. Caption &amp; note.</div>\n\n'
        "Body text.\n"
    )

    assert adapter._normalize_official_markdown_for_omnidocbench(markdown) == (
        "![](imgs/fig.jpg)\n\n"
        "Fig. 1. Caption & note.\n\n"
        "Body text.\n"
    )


def test_official_folder_retries_page_before_marking_failed(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "pred"
    img_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")
    calls = []

    class Result:
        markdown = "# recovered\n"

    class Pipeline:
        def predict(self, image_path):
            calls.append(Path(image_path).name)
            if len(calls) == 1:
                raise RuntimeError("transient vlm 500")
            return Result()

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PaddleOCRVL=lambda **kwargs: Pipeline()),
    )

    result = adapter.run_official_folder(
        img_dir=img_dir,
        out_dir=out_dir,
        server_url="http://127.0.0.1:8111/v1",
        api_model_name="model.gguf",
        page_retries=1,
    )

    assert calls == ["page.png", "page.png"]
    assert result["ok"] == 1
    assert result["fail"] == 0
    assert result["stats"][0]["attempts"] == 2
    assert (out_dir / "page.md").read_text(encoding="utf-8") == "# recovered\n"


def test_official_folder_can_copy_explicit_fallback_prediction(tmp_path, monkeypatch):
    adapter = load_adapter()
    img_dir = tmp_path / "images"
    out_dir = tmp_path / "pred"
    fallback_dir = tmp_path / "fallback"
    img_dir.mkdir()
    fallback_dir.mkdir()
    (img_dir / "page.png").write_bytes(b"fake")
    (fallback_dir / "page.md").write_text("# fallback\n", encoding="utf-8")

    class Pipeline:
        def predict(self, image_path):
            raise RuntimeError("persistent vlm 500")

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PaddleOCRVL=lambda **kwargs: Pipeline()),
    )

    result = adapter.run_official_folder(
        img_dir=img_dir,
        out_dir=out_dir,
        server_url="http://127.0.0.1:8111/v1",
        api_model_name="model.gguf",
        page_retries=0,
        fallback_pred_dir=fallback_dir,
    )

    assert result["ok"] == 1
    assert result["fail"] == 0
    assert result["fallback"] == 1
    assert result["stats"][0]["status"].startswith("fallback:")
    assert (out_dir / "page.md").read_text(encoding="utf-8") == "# fallback\n"


def test_vlm_setup_checks_llama_server_full_name():
    text = VLM_SETUP.read_text(encoding="utf-8")

    assert "Test-Path -LiteralPath $serverExe.FullName" in text


def test_vlm_setup_uses_served_gguf_path_as_api_model_id():
    text = VLM_SETUP.read_text(encoding="utf-8")

    assert "VL_REC_API_MODEL_NAME = $mainGguf" in text
