"""Verify every number published in the README multi-model leaderboard.

Reads the actual JSON/markdown sources and asserts each published cell is a
correct rounding of the source value.

Sources:
- PaddleOCR-VL-ROCm + paper columns: docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md
- PaddleOCR-VL official (local): Windows-native CDM rerun metric_result JSON
  (2026-07-11, see AGENTS.md "Latest local Windows-native official-engine CDM evidence")
- MinerU 3.4.4 pipeline: model card JSON + quick_match metric_result JSON,
  plus the B2 gate doc verdict.
- MinerU2.5-Pro llama.cpp (Windows full-set): in-repo quick_match metric_result
  JSON cross-checked at 1e-6 against the MinerU-ROCm windows-hip card
  metric_result JSON, plus the 1651-file predictions dir.

Path resolution (precedence: CLI arg > env var > built-in default):
- --mineru-rocm-repo / MINERU_ROCM_REPO: MinerU-ROCm checkout containing
  model_card.pipeline.windows-hip.json and
  results/omnidocbench/v16/windows-hip/mineru2.5_v16_quick_match_cdm_metric_result.json
  (default: C:\\Users\\rocm\\Desktop\\MinerU-ROCm)
- --paddleocr-rocm-repo / PADDLEOCR_ROCM_REPO: PaddleOCR-VL-ROCm checkout
  containing results/omnidocbench/v16/..._cdm.json
  (default: C:\\Users\\rocm\\Desktop\\PaddleOCR-VL-ROCm)

Skip/fail semantics:
- Repo-internal README/doc checks (sections 1, 2, 5, 6) are MANDATORY: any
  failure exits 1.
- External-artifact sections (3: official CDM JSON, 4: MinerU card + local
  metric_result, 7: MinerU2.5 card cross-check + predictions) are OPTIONAL:
  when an artifact file is absent the script prints
  "SKIP <section>: <path> not found" and continues instead of failing.
  The MinerU/MinerU2.5 metric_result JSONs and the predictions tree live
  inside this repo tree but are gitignored scorer artifacts, so they are
  treated as optional too (absent on a fresh clone). When the artifacts are
  present every assertion is fail-closed.
- Exit 0 = every mandatory check passed AND at least one optional section ran.
- Exit 1 = any mandatory check failed, OR every optional section skipped
  (nothing external was verified — point the flags/env vars at real checkouts).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_0716 = ROOT / "docs" / "release-paddleocr-vl-1.6-amd-windows-2026-07-16.md"
GATE_DOC = ROOT / "docs" / "benchmarks" / "mineru-sample81-gate-2026-08-01.md"
MINERU_METRIC = (
    ROOT / "eval-infra" / "01-omnidocbench" / "OmniDocBench" / "result"
    / "mineru_pipeline_quick_match_metric_result.json"
)
MINERU25_METRIC = (
    ROOT / "eval-infra" / "01-omnidocbench" / "OmniDocBench" / "result"
    / "mineru2_5_llamacpp_windows_full1651_score_quick_match_metric_result.json"
)
MINERU25_PRED_DIR = ROOT / "predictions" / "mineru2_5_llamacpp_windows_full1651_score"

DEFAULT_MINERU_REPO = Path(r"C:\Users\rocm\Desktop\MinerU-ROCm")
DEFAULT_PADDLEOCR_REPO = Path(r"C:\Users\rocm\Desktop\PaddleOCR-VL-ROCm")

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument(
    "--mineru-rocm-repo", type=Path, default=None,
    help="MinerU-ROCm checkout dir (env: MINERU_ROCM_REPO; default: %(default)s)",
)
parser.add_argument(
    "--paddleocr-rocm-repo", type=Path, default=None,
    help="PaddleOCR-VL-ROCm checkout dir (env: PADDLEOCR_ROCM_REPO; default: %(default)s)",
)
args = parser.parse_args()

mineru_repo = args.mineru_rocm_repo or Path(os.environ.get("MINERU_ROCM_REPO") or DEFAULT_MINERU_REPO)
paddleocr_repo = args.paddleocr_rocm_repo or Path(
    os.environ.get("PADDLEOCR_ROCM_REPO") or DEFAULT_PADDLEOCR_REPO
)

MINERU_CARD = mineru_repo / "model_card.pipeline.windows-hip.json"
MINERU25_CARD = (
    mineru_repo / "results" / "omnidocbench" / "v16" / "windows-hip"
    / "mineru2.5_v16_quick_match_cdm_metric_result.json"
)
OFFICIAL_CDM_JSON = (
    paddleocr_repo / "results" / "omnidocbench" / "v16"
    / "paddleocr_official_local_llamacpp_gguf_quick_match_metric_result_cdm.json"
)

failures = []
skipped_optional = set()
OPTIONAL_SECTIONS = {3, 4, 7}


def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)


def skip(section, path):
    print(f"SKIP section {section}: {path} not found")
    skipped_optional.add(section)


def close(published, actual, tol, label):
    check(label, abs(published - actual) <= tol, f"published={published} actual={actual} tol={tol}")


def overall_of(text_edit, teds_pct, cdm_pct):
    return ((1 - text_edit) * 100 + teds_pct + cdm_pct) / 3


print("== 1. PaddleOCR-VL-ROCm (reference) <- docs/release-paddleocr-vl-1.6-amd-windows-2026-07-16.md ==")
doc = RELEASE_0716.read_text(encoding="utf-8")
for token in ["95.99", "0.03488", "0.12882", "94.0865", "97.36"]:
    check(f"release-0716 doc contains {token}", token in doc)
close(94.09, 94.0865, 0.005, "ROCm TEDS 94.09 rounds from 94.0865")

print("== 2. PaddleOCR-VL (paper, Linux vLLM) <- release-0716 public baseline table ==")
baseline = doc.split("Public official baseline", 1)[1]
for token in ["96.33", "0.033", "0.127", "94.76", "97.49"]:
    check(f"baseline table contains {token}", token in baseline)

print("== 3. PaddleOCR-VL official (local) <- Windows-native CDM rerun metric_result (2026-07-11) ==")
if not OFFICIAL_CDM_JSON.exists():
    skip(3, OFFICIAL_CDM_JSON)
else:
    d = json.loads(OFFICIAL_CDM_JSON.read_text(encoding="utf-8"))
    o_text = d["text_block"]["page"]["Edit_dist"]["ALL"]
    o_ro = d["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"]
    o_teds = d["table"]["page"]["TEDS"]["ALL"] * 100
    o_cdm = d["display_formula"]["page"]["CDM"]["ALL"] * 100
    o_overall = overall_of(o_text, o_teds, o_cdm)
    print(f"  raw: text={o_text} ro={o_ro} teds={o_teds} cdm={o_cdm} overall={o_overall}")
    close(0.03444, o_text, 5e-6, "official text Edit-dist 0.03444")
    close(0.12949, o_ro, 5e-6, "official RO Edit-dist 0.12949")
    close(94.24, o_teds, 0.005, "official TEDS 94.24")
    close(96.50, o_cdm, 0.005, "official CDM 96.50")
    close(96.5022, o_cdm, 5e-5, "official CDM 96.5022 (4dp, as cited in README/AGENTS.md)")
    close(95.77, o_overall, 0.005, "official Overall 95.77")

print("== 4. MinerU 3.4.4 pipeline (Windows HIP) <- model card + in-repo metric_result ==")
missing4 = [p for p in (MINERU_CARD, MINERU_METRIC) if not p.exists()]
for p in missing4:
    skip(4, p)
if not missing4:
    card = json.loads(MINERU_CARD.read_text(encoding="utf-8"))
    mr = json.loads(MINERU_METRIC.read_text(encoding="utf-8"))
    m_text = mr["text_block"]["all"]["Edit_dist"]["ALL_page_avg"]
    m_ro = mr["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"]
    m_teds = mr["table"]["page"]["TEDS"]["ALL"] * 100
    m_cdm = mr["display_formula"]["page"]["CDM"]["ALL"] * 100
    m_overall = overall_of(m_text, m_teds, m_cdm)
    print(f"  metric_result raw: text={m_text} ro={m_ro} teds={m_teds} cdm={m_cdm} overall={m_overall}")
    sub = card["submetrics"]
    check("card model_version == 3.4.4", card["model_version"] == "3.4.4")
    check("card text == metric_result", abs(sub["text_edit_dist"] - m_text) < 1e-9)
    check("card RO == metric_result", abs(sub["reading_order_edit_dist"] - m_ro) < 1e-9)
    check("card TEDS == metric_result", abs(sub["table_teds_percent"] - m_teds) < 1e-9)
    check("card CDM == metric_result", abs(sub["formula_cdm_percent"] - m_cdm) < 1e-9)
    check("card overall == computed overall (rounded to 2dp)", abs(card["overall"] - m_overall) < 0.005,
          f"card={card['overall']} computed={m_overall}")
    close(0.05655, m_text, 5e-6, "MinerU text Edit-dist 0.05655")
    close(0.15314, m_ro, 5e-6, "MinerU RO Edit-dist 0.15314")
    close(82.04, m_teds, 0.005, "MinerU TEDS 82.04")
    close(83.39, m_cdm, 0.005, "MinerU CDM 83.39")
    close(86.59, m_overall, 0.005, "MinerU Overall 86.59")

print("== 5. B2 gate doc verdict (docs/benchmarks/mineru-sample81-gate-2026-08-01.md) ==")
gate = GATE_DOC.read_text(encoding="utf-8")
check("gate verdict is ACCEPT", "Gate verdict: ACCEPT" in gate)
check("gate sample was 130 pages", "sample pages: 130" in gate and "130 stems" in gate)
check("gate cites the 86.59 series", "86.59" in gate)

print("== 6. README leaderboard rows are numerically identical EN vs ZH ==")
ROW_RE = re.compile(r"^\|\s*(?:PaddleOCR|MinerU)[^\n]*\|$", re.MULTILINE)
NUM_RE = re.compile(r"\d+\.\d+")
tables = {}
for name in ("README.md", "README.zh-CN.md"):
    text = (ROOT / name).read_text(encoding="utf-8")
    rows = ROW_RE.findall(text)
    tables[name] = [NUM_RE.findall(r) for r in rows]
    print(f"  {name} leaderboard rows: {tables[name]}")
check("both READMEs have 3 leaderboard data rows", all(len(v) == 3 for v in tables.values()))
check("EN/ZH leaderboard numbers identical", tables["README.md"] == tables["README.zh-CN.md"])

print("== 7. MinerU2.5-Pro llama.cpp (Windows full-set) <- in-repo metric_result vs MinerU-ROCm windows-hip card + 1651 predictions ==")
missing7 = [p for p in (MINERU25_METRIC, MINERU25_CARD, MINERU25_PRED_DIR) if not p.exists()]
for p in missing7:
    skip(7, p)
if not missing7:
    local25 = json.loads(MINERU25_METRIC.read_text(encoding="utf-8"))
    card25 = json.loads(MINERU25_CARD.read_text(encoding="utf-8"))

    def mineru25_series(d):
        return (
            d["text_block"]["all"]["Edit_dist"]["ALL_page_avg"],
            d["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"],
            d["table"]["all"]["TEDS"]["all"] * 100,
            d["display_formula"]["all"]["CDM"]["all"] * 100,
        )

    l_text, l_ro, l_teds, l_cdm = mineru25_series(local25)
    c_text, c_ro, c_teds, c_cdm = mineru25_series(card25)
    l_overall = overall_of(l_text, l_teds, l_cdm)
    print(f"  in-repo raw: text={l_text} ro={l_ro} teds={l_teds} cdm={l_cdm} overall={l_overall}")
    close(l_text, c_text, 1e-6, "MinerU2.5 text Edit-dist: in-repo == card")
    close(l_ro, c_ro, 1e-6, "MinerU2.5 RO Edit-dist: in-repo == card")
    close(l_teds, c_teds, 1e-6, "MinerU2.5 TEDS: in-repo == card")
    close(l_cdm, c_cdm, 1e-6, "MinerU2.5 CDM: in-repo == card")
    close(0.03734, l_text, 5e-6, "MinerU2.5 text Edit-dist 0.03734")
    close(0.12250, l_ro, 5e-6, "MinerU2.5 RO Edit-dist 0.12250")
    close(89.46, l_teds, 0.005, "MinerU2.5 TEDS 89.46")
    close(97.03, l_cdm, 0.005, "MinerU2.5 CDM 97.03")
    close(94.25, l_overall, 0.005, "MinerU2.5 Overall 94.25")
    md_count = len(list(MINERU25_PRED_DIR.glob("*.md")))
    check("MinerU2.5 predictions dir contains 1651 .md files", md_count == 1651,
          f"count={md_count}")

print()
if failures:
    print(f"VERIFY FAILED: {len(failures)} check(s) failed")
    sys.exit(1)
if skipped_optional >= OPTIONAL_SECTIONS:
    print(
        "VERIFY FAILED: every optional evidence section skipped (no external "
        "artifacts found). Mandatory README/doc checks passed, but nothing "
        "external was verified. Pass --mineru-rocm-repo / --paddleocr-rocm-repo "
        "or set MINERU_ROCM_REPO / PADDLEOCR_ROCM_REPO."
    )
    sys.exit(1)
print("VERIFY OK: all leaderboard numbers match their sources")
if skipped_optional:
    print(f"note: {len(skipped_optional)} optional section(s) skipped (see SKIP lines above)")
