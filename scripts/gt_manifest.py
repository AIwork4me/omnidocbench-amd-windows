"""Ground-truth emptiness helper shared by validators and the adapter.

OmniDocBench v1.6 contains pages whose GT text is genuinely empty (e.g. pages
whose layout_dets are only figures plus text_mask regions with empty ``text``).
For such pages an empty prediction is CORRECT and must be counted as valid --
both by the prediction validators and by the adapter's per-page resume logic.
"""
from __future__ import annotations

import json
from pathlib import Path


def page_has_empty_gt(page: dict) -> bool:
    """True when a manifest page's GT contributes no text or html content.

    A page is "empty GT" iff none of its non-ignored layout dets carry
    non-whitespace ``text``, ``html``, ``latex`` or ``content``. Figures and
    empty text-masks do not contribute to the text metrics' ground truth; the
    scorer also consumes ``latex`` (equation_isolated) and preprocessed
    ``content``, so those fields count too. A page with NO ``layout_dets`` key
    at all is treated as non-empty (unknown/malformed: only explicitly-empty
    annotations count).
    """
    if "layout_dets" not in page:
        return False
    for det in page.get("layout_dets") or []:
        if det.get("ignore"):
            continue
        for field in ("text", "html", "latex", "content"):
            if str(det.get(field, "") or "").strip():
                return False
    return True


def empty_gt_stems(manifest_pages: list[dict]) -> set[str]:
    """Image stems (without extension) whose GT is empty, per the manifest."""
    stems = set()
    for page in manifest_pages:
        image_path = page.get("page_info", {}).get("image_path")
        if isinstance(image_path, str) and image_path and page_has_empty_gt(page):
            stems.add(Path(image_path).stem)
    return stems


def load_empty_gt_stems(manifest_path: Path) -> set[str]:
    """Read a manifest JSON file and return the empty-GT stems it declares."""
    pages = json.loads(manifest_path.read_text(encoding="utf-8"))
    return empty_gt_stems(pages)
