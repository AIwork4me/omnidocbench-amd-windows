"""Render benchmark tables from benchmarks/index.json into the READMEs.

The README/README.zh-CN benchmark tables are generated from the single source
of truth (benchmarks/index.json); hand-edited numbers drift and are rejected
by CI (git diff --exit-code after rendering).

Markers
-------
<!-- benchmark-table:start --> ... <!-- benchmark-table:end -->
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

START = "<!-- benchmark-table:start -->"
END = "<!-- benchmark-table:end -->"


def render_table(entries: list[dict]) -> str:
    rows = []
    rows.append(
        "| Model | Backend | Run | Coverage | Text Edit-dist ↓ | Reading-order Edit-dist ↓ | Table TEDS ↑ | Formula CDM ↑ | Evidence |"
    )
    rows.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    for entry in sorted(entries, key=lambda e: e["date"], reverse=True):
        raw = entry["raw_metrics"]
        display = entry["display_metrics"]
        text = raw.get("text_edit_dist")
        ro = raw.get("reading_order_edit_dist")
        teds = display.get("table_teds")
        cdm = display.get("formula_cdm")
        fmt = lambda v: "—" if v is None else f"{v:.4f}"
        cov = entry.get("prediction_coverage")
        cov_s = "—" if cov is None else f"{cov:.4f}"
        run_label = {
            "resumed": "validated resumed",
            "clean-room": "clean-room",
            "independent": "independent",
            "smoke": "smoke",
        }[entry["run_type"]]
        model = f"{entry['model']} {entry['model_version']}"
        backend = entry["backend"]
        evidence = entry["evidence_document"]
        rows.append(
            f"| {model} | {backend} | {run_label} | {cov_s} | "
            f"{fmt(text)} | {fmt(ro)} | {fmt(teds)} | {fmt(cdm)} | [{evidence}]({evidence}) |"
        )
    return "\n".join(rows)


def replace_block(text: str, table: str) -> str:
    block = f"{START}\n{table}\n{END}"
    if START in text and END in text:
        head, _, tail = text.partition(START)
        _, _, tail = tail.partition(END)
        return head + block + tail
    return text + "\n\n" + block


def main() -> int:
    index_path = REPO_ROOT / "benchmarks" / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    table = render_table(entries)
    for readme in ("README.md", "README.zh-CN.md"):
        path = REPO_ROOT / readme
        text = path.read_text(encoding="utf-8")
        if "<!-- benchmark-table:start -->" not in text:
            # Seed the marker block after the first H1 section heading.
            lines = text.splitlines(keepends=True)
            insert_at = 0
            for i, line in enumerate(lines):
                if line.startswith("## "):
                    insert_at = i
                    break
            lines.insert(insert_at, f"{START}\n{table}\n{END}\n\n")
            text = "".join(lines)
        else:
            text = replace_block(text, table)
        path.write_text(text, encoding="utf-8")
        print(f"Rendered benchmark table into {readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
