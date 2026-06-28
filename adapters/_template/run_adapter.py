"""Adapter template -- implement this for your model.

Interface contract:
  Input:  img_dir -- directory of page images (jpg/png)
  Output: out_dir/<image_stem>.md -- one Markdown per image

The eval-infra reads these .md files. Your adapter just needs to produce them.

How to use this template
------------------------
1. Copy this whole ``_template/`` directory to ``adapters/<your-model>/``.
2. Edit ``run_adapter.py``:
   - Replace the body of ``run_adapter`` with your model's inference.
   - Keep the signature: ``run_adapter(img_dir, out_dir, server_url)``.
   - Keep the output convention: write ``out_dir/<image_stem>.md`` (UTF-8).
3. Drop in any model-specific provisioning scripts (e.g. ``01-vlm-server/``,
   ``02-layout-model/``) -- mirror the structure of the
   ``paddleocr-vl-1.6/`` reference adapter.
4. Update ``README.md`` to describe your model.
5. Run your adapter against the dataset, then point the scoring module at
   ``predictions/<your-model>/``.

The eval-infra never imports your adapter; it only consumes the ``.md`` files
your adapter writes. Per-page failures should be caught and recorded so one
bad page does not abort the whole run (a missing page simply scores zero).
"""
from __future__ import annotations

from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def run_adapter(img_dir: Path, out_dir: Path, server_url: str = "") -> dict:
    """Run inference over every image in ``img_dir``; write ``<stem>.md`` per page.

    Returns a summary dict. The eval-infra ignores the return value; it exists
    for human/CLI inspection.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXT)
    for img in images:
        # TODO: replace with your model's inference.
        # On failure, log and continue -- do NOT raise (a missing page
        # scores zero in the harness, which is the desired degraded mode).
        markdown_text = f"# {img.name}\n\n(Your model's output here)\n"
        (out_dir / f"{img.stem}.md").write_text(markdown_text, encoding="utf-8")
    return {"count": len(images)}


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Model adapter: images -> .md predictions")
    p.add_argument("--img-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--server-url", default="")
    args = p.parse_args()
    print(run_adapter(Path(args.img_dir), Path(args.out_dir), args.server_url))
