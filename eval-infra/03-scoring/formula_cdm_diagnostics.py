from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


FAILURE_CLASSES = (
    "evaluator_gt_compat",
    "pred_latex_unrenderable",
    "normalization_or_matching",
    "extraction_or_matching",
    "lightweight_adapter_or_llama",
    "model_or_dataset_gap",
    "pending",
)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def metric_value(sample: dict[str, Any], name: str) -> float | None:
    metric = sample.get("metric")
    if isinstance(metric, dict) and metric.get(name) is not None:
        return _safe_float(metric.get(name))
    if name == "Edit_dist" and sample.get("edit") is not None:
        return _safe_float(sample.get("edit"))
    if sample.get(name) is not None:
        return _safe_float(sample.get(name))
    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_list_value(value: Any) -> Any:
    if isinstance(value, list) and value:
        return value[0]
    return value


def _case_index(sample: dict[str, Any], source_idx: int) -> int:
    for key in ("idx", "sample_idx"):
        value = sample.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    gt_idx = _first_list_value(sample.get("gt_idx"))
    if gt_idx is not None:
        try:
            return int(gt_idx)
        except (TypeError, ValueError):
            pass
    return source_idx


def selection_reason(sample: dict[str, Any]) -> str | None:
    pred = str(sample.get("pred") or "").strip()
    cdm = metric_value(sample, "CDM")
    edit = metric_value(sample, "Edit_dist")

    if not pred:
        return "prediction_empty"
    if cdm is None:
        return None
    if cdm == 0.0:
        return "cdm_zero"
    if edit is not None and cdm < 0.5 and edit <= 0.15:
        return "cdm_low_edit_close"
    if cdm >= 0.99:
        return "control_high_cdm"
    return None


def _case_from_sample(sample: dict[str, Any], source_idx: int, reason: str) -> dict[str, Any]:
    img_id = sample.get("img_id") or sample.get("image_name")
    image_name = sample.get("image_name") or sample.get("img_id")
    return {
        "case_id": "",
        "idx": _case_index(sample, source_idx),
        "img_id": img_id,
        "image_name": image_name,
        "gt_idx": sample.get("gt_idx"),
        "pred_idx": sample.get("pred_idx"),
        "gt": sample.get("gt"),
        "pred": sample.get("pred"),
        "edit": metric_value(sample, "Edit_dist"),
        "cdm": metric_value(sample, "CDM"),
        "gt_cdm": sample.get("gt_cdm"),
        "pred_cdm": sample.get("pred_cdm"),
        "pred_cdm_alt": sample.get("pred_cdm_alt"),
        "selection_reason": reason,
        "failure_class": "pending",
    }


def select_hard_cases(samples: list[dict[str, Any]], limit: int = 50) -> list[dict[str, Any]]:
    candidates: list[tuple[int, str, dict[str, Any]]] = []
    controls: list[tuple[int, str, dict[str, Any]]] = []

    for source_idx, sample in enumerate(samples):
        reason = selection_reason(sample)
        if reason is None:
            continue
        row = (source_idx, reason, sample)
        if reason == "control_high_cdm":
            controls.append(row)
        else:
            candidates.append(row)

    selected_rows = controls[: min(5, limit)] + candidates
    cases: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()
    for source_idx, reason, sample in selected_rows:
        key = (sample.get("img_id") or sample.get("image_name"), tuple(sample.get("gt_idx") or []), tuple(sample.get("pred_idx") or []))
        if key in seen:
            continue
        seen.add(key)
        case = _case_from_sample(sample, source_idx, reason)
        case["case_id"] = f"cdm-{len(cases) + 1:04d}"
        cases.append(case)
        if len(cases) >= limit:
            break
    return cases


def _manifest_image_names(page: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("img_id", "image_name", "page_id"):
        value = page.get(key)
        if value:
            names.add(str(value))
            names.add(Path(str(value)).name)
    page_info = page.get("page_info")
    if isinstance(page_info, dict):
        for key in ("image_path", "img_path", "image"):
            value = page_info.get(key)
            if value:
                names.add(str(value))
                names.add(Path(str(value)).name)
    return names


def write_page_manifest(full_manifest: list[dict[str, Any]], cases: list[dict[str, Any]], out_path: str | Path) -> int:
    wanted = {
        str(value)
        for case in cases
        for value in (case.get("img_id"), case.get("image_name"))
        if value
    }
    wanted |= {Path(name).name for name in list(wanted)}
    filtered = [page for page in full_manifest if _manifest_image_names(page) & wanted]
    write_json(out_path, filtered)
    return len(filtered)


def classify_probe(case: dict[str, Any], probe: dict[str, Any]) -> str:
    gt_self = probe.get("gt_self") or {}
    pred_self = probe.get("pred_self") or {}
    gt_pred = probe.get("gt_pred") or {}
    pred = str(case.get("pred") or "").strip()
    edit = _safe_float(case.get("edit"))

    if _safe_float(gt_self.get("F1_score")) == 0.0 or int(gt_self.get("gt_tokens") or 0) == 0:
        return "evaluator_gt_compat"
    if not pred:
        return "extraction_or_matching"
    pred_self_f1 = _safe_float(pred_self.get("F1_score"))
    pred_tokens = max(int(pred_self.get("gt_tokens") or 0), int(pred_self.get("pred_tokens") or 0))
    if pred_self_f1 == 0.0 or pred_tokens == 0:
        return "pred_latex_unrenderable"
    gt_pred_f1 = _safe_float(gt_pred.get("F1_score"))
    if gt_pred_f1 is not None and gt_pred_f1 < 0.5 and edit is not None and edit <= 0.15:
        return "normalization_or_matching"
    if gt_pred_f1 is not None and gt_pred_f1 < 0.5:
        return "model_or_dataset_gap"
    return "pending"


def copy_prediction_subset(cases: list[dict[str, Any]], source_dir: str | Path, out_dir: str | Path) -> int:
    source = Path(source_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in sorted({case.get("image_name") or case.get("img_id") for case in cases if case.get("image_name") or case.get("img_id")}):
        md_name = f"{Path(str(name)).stem}.md"
        src = source / md_name
        if src.exists():
            shutil.copy2(src, out / md_name)
            copied += 1
    return copied


def _formula_for_gt(case: dict[str, Any]) -> str:
    return str(case.get("gt_cdm") or case.get("gt") or "")


def _formula_for_pred(case: dict[str, Any]) -> str:
    return str(case.get("pred_cdm_alt") or case.get("pred_cdm") or case.get("pred") or "")


def _zero_cdm(error: Exception | None = None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "recall": 0.0,
        "precision": 0.0,
        "F1_score": 0.0,
        "tp": 0,
        "gt_tokens": 0,
        "pred_tokens": 0,
    }
    if error is not None:
        metrics["cdm_eval_error"] = f"{type(error).__name__}: {error}"
    return metrics


def run_pair_probe(cases: list[dict[str, Any]], tmp_dir: str | Path) -> list[dict[str, Any]]:
    from src.metrics.cdm.cdm import cdm_metrics

    results: list[dict[str, Any]] = []
    for case in cases:
        gt = _formula_for_gt(case)
        pred = _formula_for_pred(case)

        def probe_one(left: str, right: str) -> dict[str, Any]:
            try:
                if not left or not right:
                    return _zero_cdm()
                return cdm_metrics(left, right, save_vis=False, tmp_dir=str(tmp_dir))
            except Exception as exc:  # noqa: BLE001 - diagnostics must record per-case failures.
                return _zero_cdm(exc)

        probe = {
            "gt_self": probe_one(gt, gt),
            "pred_self": probe_one(pred, pred),
            "gt_pred": probe_one(gt, pred),
        }
        failure_class = classify_probe(case, probe)
        updated = dict(case)
        updated["failure_class"] = failure_class
        updated["probe"] = probe
        results.append(updated)
    return results


def _load_run_summary(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return read_json(p)


def _metric_lines(summary: dict[str, Any]) -> list[str]:
    notebook = summary.get("notebook_metric_summary") or summary
    metrics = notebook.get("metrics") or {}
    lines = []
    overall = notebook.get("overall_notebook")
    if overall is not None:
        lines.append(f"- Overall notebook: {overall}")
    for name in ("text_block_Edit_dist", "display_formula_CDM", "table_TEDS", "reading_order_Edit_dist"):
        value = (metrics.get(name) or {}).get("notebook_value")
        if value is not None:
            lines.append(f"- {name}: {value}")
    return lines


def build_report(
    cases: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    run_summary: dict[str, Any],
    prediction_stats: dict[str, Any],
) -> str:
    by_case = {case["case_id"]: dict(case) for case in cases}
    for probe_case in probes:
        by_case.setdefault(probe_case["case_id"], {}).update(probe_case)
    merged = list(by_case.values())
    counts = Counter(case.get("failure_class") or "pending" for case in merged)

    lines = [
        "# Formula CDM Root-Cause Report",
        "",
        "Generated from the repository diagnostics CLI.",
        "",
        "## Full-Run Metrics",
        "",
    ]
    metric_lines = _metric_lines(run_summary)
    lines.extend(metric_lines or ["- Run summary not provided."])
    lines.extend(["", "## Prediction Stats", ""])
    if prediction_stats:
        lines.append(f"- Pages: {prediction_stats.get('count')}")
        lines.append(f"- Successful pages: {prediction_stats.get('ok')}")
        failed = prediction_stats.get("fail")
        if failed is None and isinstance(prediction_stats.get("stats"), list):
            failed = sum(1 for item in prediction_stats["stats"] if item.get("status") != "ok")
        lines.append(f"- Failed pages: {failed}")
    else:
        lines.append("- Prediction stats not provided.")

    lines.extend(["", "## Hard-Case Attribution", ""])
    for cls in FAILURE_CLASSES:
        if counts.get(cls):
            lines.append(f"- {cls}: {counts[cls]}")
    if not counts:
        lines.append("- No cases available.")

    lines.extend(["", "## Top Cases", ""])
    for case in merged[:20]:
        lines.append(
            f"- {case.get('case_id')} idx={case.get('idx')} cdm={case.get('cdm')} "
            f"edit={case.get('edit')} class={case.get('failure_class')} "
            f"reason={case.get('selection_reason')} img={case.get('img_id')}"
        )

    lines.extend(["", "## Recommended Next Action", ""])
    if counts.get("evaluator_gt_compat", 0) > 0:
        lines.append("Prioritize scorer compatibility fixes for GT self-CDM failures.")
    elif counts.get("normalization_or_matching", 0) > 0:
        lines.append("Investigate normalization and formula matching on close Edit-distance cases.")
    elif counts.get("pred_latex_unrenderable", 0) > 0:
        lines.append("Inspect adapter post-processing for invalid prediction LaTeX.")
    elif counts.get("model_or_dataset_gap", 0) > 0:
        lines.append("Treat remaining low cases as adapter/model/dataset candidates and compare official doc_parser output.")
    else:
        lines.append("Run pair-probe and subset adapter comparison to replace pending classifications.")
    lines.append("")
    return "\n".join(lines)


def cmd_make_hard_cases(args: argparse.Namespace) -> int:
    samples = read_json(args.display_result)
    if not isinstance(samples, list):
        raise SystemExit("display result must be a JSON list")
    cases = select_hard_cases(samples, limit=args.limit)
    write_json(args.cases_out, cases)
    manifest_count = 0
    copied_count = 0
    if args.full_manifest and args.manifest_out:
        manifest = read_json(args.full_manifest)
        if not isinstance(manifest, list):
            raise SystemExit("full manifest must be a JSON list")
        manifest_count = write_page_manifest(manifest, cases, args.manifest_out)
    if args.source_predictions and args.prediction_out:
        copied_count = copy_prediction_subset(cases, args.source_predictions, args.prediction_out)
    print(f"cases={len(cases)} manifest_pages={manifest_count} predictions_copied={copied_count}")
    return 0


def cmd_pair_probe(args: argparse.Namespace) -> int:
    cases = read_json(args.cases)
    if not isinstance(cases, list):
        raise SystemExit("cases must be a JSON list")
    results = run_pair_probe(cases, args.tmp_dir)
    write_json(args.probe_out, results)
    print(f"probed={len(results)}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cases = read_json(args.cases)
    probes = read_json(args.probe) if args.probe and Path(args.probe).exists() else []
    run_summary = _load_run_summary(args.run_summary)
    prediction_stats = read_json(args.prediction_stats) if args.prediction_stats and Path(args.prediction_stats).exists() else {}
    report = build_report(cases, probes, run_summary, prediction_stats)
    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"report={out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Formula CDM hard-case diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("make-hard-cases")
    make.add_argument("--display-result", required=True)
    make.add_argument("--full-manifest")
    make.add_argument("--source-predictions")
    make.add_argument("--cases-out", required=True)
    make.add_argument("--manifest-out")
    make.add_argument("--prediction-out")
    make.add_argument("--limit", type=int, default=50)
    make.set_defaults(func=cmd_make_hard_cases)

    pair = sub.add_parser("pair-probe")
    pair.add_argument("--cases", required=True)
    pair.add_argument("--probe-out", required=True)
    pair.add_argument("--tmp-dir", default="/tmp/formula_cdm_probe")
    pair.set_defaults(func=cmd_pair_probe)

    report = sub.add_parser("report")
    report.add_argument("--cases", required=True)
    report.add_argument("--probe")
    report.add_argument("--run-summary")
    report.add_argument("--prediction-stats")
    report.add_argument("--report-out", required=True)
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
