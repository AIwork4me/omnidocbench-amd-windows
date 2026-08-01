# Text Edit-distance Regression Probe: Official vs Lightweight

Date: 2026-07-09

## Question

Investigate the pages driving the Text Edit-distance regression when switching
from the previous lightweight PaddleOCR-VL path to the current official
`PaddleOCRVL` doc_parser path. The goal is root cause, not a guessed score fix.

## Probe Setup

- Source pages: top 9 full-set Text Edit-distance regressions.
- Current VLM server: `http://127.0.0.1:8111/v1/models` verified healthy.
- Rerun outputs:
  - `predictions/probe_text_regression_lightweight_2026-07-09`
  - `predictions/probe_text_regression_official_2026-07-09`
  - `predictions/probe_text_regression_official_htmlnorm_2026-07-09`
  - `predictions/probe_text_regression_official_prettyfalse_2026-07-09`
- Scoring configs:
  - `eval-infra/01-omnidocbench/configs/v16-text-regression-probe-lightweight.yaml`
  - `eval-infra/01-omnidocbench/configs/v16-text-regression-probe-official.yaml`
  - `eval-infra/01-omnidocbench/configs/v16-text-regression-probe-official-htmlnorm.yaml`
  - `eval-infra/01-omnidocbench/configs/v16-text-regression-probe-official-prettyfalse.yaml`

## Result Summary

The raw official probe is much worse than lightweight on the selected pages:

| Run | Text Edit-distance |
|---|---:|
| lightweight probe | 0.178384 |
| official probe | 0.430483 |
| official after HTML-wrapper normalization | 0.183316 |
| official `_to_markdown(pretty=False)` | 0.183316 |

HTML-wrapper normalization recovers `0.247166` absolute Text Edit-distance on
this subset, or about `98.0%` of the observed `official - lightweight` subset
gap. Calling PaddleOCRVL's own `_to_markdown(pretty=False)` produces the same
score as post-hoc HTML-wrapper normalization, so the immediate root cause is
the default `pretty=True` export mode.

## Per-page Evidence

| image | lightweight | official | official htmlnorm | official-light | recovered |
|---|---:|---:|---:|---:|---:|
| newspaper_The Times UK_0801@magazinesclubnew_page_031.png | 1.000000 | 1.000000 | 1.000000 | 0.000000 | 0.000000 |
| docstructbench_llm-raw-scihub-o.O-j.snb.2004.06.022.pdf_2.jpg | 0.000000 | 0.490956 | 0.000000 | 0.490956 | 0.490956 |
| docstructbench_dianzishu_zhongwenzaixian-o.O-63710614.pdf_149.jpg | 0.000000 | 0.481013 | 0.000000 | 0.481013 | 0.481013 |
| PPT_ch7_page_053.png | 0.000000 | 0.363636 | 0.006452 | 0.363636 | 0.357185 |
| page-87866578-c897-404e-b751-51fd444f59b2.png | 0.135802 | 0.160494 | 0.160494 | 0.024691 | 0.000000 |
| PPT_fundamental_theorem_of_calculus___page_002.png | 0.000000 | 0.343434 | 0.000000 | 0.343434 | 0.343434 |
| yanbaor2_yanbaoPPT_2108.jpg | 0.003086 | 0.209756 | 0.003086 | 0.206670 | 0.206670 |
| PPT_BaharMartonosi_page_005.png | 0.000000 | 0.345238 | 0.000000 | 0.345238 | 0.345238 |
| jiaocaineedrop_jiaocai_needrop_en_349.jpg | 0.466565 | 0.479815 | 0.479815 | 0.013250 | 0.000000 |

Machine-readable evidence:

- `docs/non-cdm-text-regression-probe-summary-2026-07-09.json`
- `docs/non-cdm-text-regression-full-vs-probe-2026-07-09.json`
- `docs/non-cdm-text-regression-htmlnorm-comparison-2026-07-09.json`
- `docs/non-cdm-text-regression-prettyfalse-comparison-2026-07-09.json`

## Root Cause

Primary root cause: official `PaddleOCRVL` doc_parser emits centered images and
captions as HTML wrappers when Markdown is exported with its default
`pretty=True` mode:

```html
<div style="text-align: center;"><img src="imgs/..." alt="Image" width="45%" /></div>
<div style="text-align: center;">Fig. 1. ...</div>
```

OmniDocBench's Markdown parser/scorer is better aligned with the lightweight
shape, which PaddleOCRVL also emits when calling `_to_markdown(pretty=False)`:

```markdown
![](imgs/...)

Fig. 1. ...
```

On the regression pages, the official HTML wrappers change the parsed text
candidates and matching behavior. Examples observed:

- `docstructbench_llm-raw-scihub-o.O-j.snb.2004.06.022.pdf_2.jpg`: official
  raw score `0.490956`; after wrapper normalization `0.000000`.
- `docstructbench_dianzishu_zhongwenzaixian-o.O-63710614.pdf_149.jpg`:
  official raw score `0.481013`; after wrapper normalization `0.000000`.
- `PPT_BaharMartonosi_page_005.png`: official raw score `0.345238`; after
  wrapper normalization `0.000000`.

Secondary findings:

- `newspaper_The Times UK_0801@magazinesclubnew_page_031.png` is not a valid
  official-vs-lightweight quality comparison in the current probe: both paths
  hit VLM 500 and produce no fresh `.md`. The previous full lightweight score
  was from an existing stale prediction file while `_run_stats.json` recorded a
  page failure.
- `jiaocaineedrop_jiaocai_needrop_en_349.jpg` is mostly not explained by HTML
  wrappers. It remains a hard text/matching page and shows run-to-run output
  variation.
- `page-87866578-c897-404e-b751-51fd444f59b2.png` has a small residual
  official gap after normalization, indicating real output difference rather
  than wrapper incompatibility.

## Fix Applied

The official adapter now prefers PaddleOCRVL's evaluation-oriented export before
writing the `.md` file:

- if a result exposes `_to_markdown`, call `_to_markdown(pretty=False)`
- fall back to existing Markdown fields for older/alternate result objects
- retain HTML-wrapper normalization as a defensive fallback for any remaining
  pretty HTML output

The fallback normalization still converts:

- centered HTML image wrappers become `![](imgs/...)`
- centered caption/text wrappers become plain Markdown text
- excessive blank lines are collapsed

This is intentionally done at the adapter output boundary; it does not alter
the VLM prompt, model, retry behavior, or scorer.

## Verification

- RED test observed:
  `tests/test_paddleocr_vl_adapter.py::test_official_markdown_normalizes_centered_html_wrappers`
  failed with missing function before implementation.
- GREEN:
  `.\.venv\Scripts\python.exe -m pytest tests\test_paddleocr_vl_adapter.py -q`
  passed: `11 passed`.
- Direct PaddleOCRVL probe:
  default `markdown` and `_to_markdown(pretty=True)` produced `divs=7`,
  `html_imgs=4`, `md_imgs=0`, and `text_all_count=9`; `_to_markdown(pretty=False)`
  produced `divs=0`, `html_imgs=0`, `md_imgs=4`, and `text_all_count=5`.
- Real official rerun after the fix:
  `probe_text_regression_official_prettyfalse_2026-07-09_quick_match` scored
  Text Edit-distance `0.183316`, matching the HTML-normalized diagnostic run.
