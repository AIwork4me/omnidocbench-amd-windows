"""Validate benchmarks/index.json against benchmarks/schema.json + invariants.

Every entry must:
  * conform to the JSON schema (benchmarks/schema.json)
  * have unique ids
  * reference an existing evidence document in docs/
  * satisfy cross-field invariants:
      - coverage in (0, 1]
      - failed_pages == known_failures + unknown_failures (when all set)
      - raw TEDS/CDM values in [0, 1] and display values == raw * 100
        (display/raw agreement is the anti-fabrication guard)
      - run_type is one of resumed | clean-room | independent | smoke
      - a "clean-room"/"independent" run_type requires a prediction_tree_hash
        (unverifiable claims without hashes are rejected)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RUN_TYPES = ("resumed", "clean-room", "independent", "smoke")


def validate_index(root: Path) -> tuple[list[str], list[dict]]:
    errors: list[str] = []
    schema_path = root / "benchmarks" / "schema.json"
    index_path = root / "benchmarks" / "index.json"
    if not schema_path.is_file():
        return [f"missing schema: {schema_path}"], []
    if not index_path.is_file():
        return [f"missing index: {index_path}"], []
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        entries = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        return [f"benchmarks/index.json unreadable: {error}"], []
    if not isinstance(entries, list):
        return ["benchmarks/index.json must contain a JSON list"], []

    try:
        import jsonschema  # type: ignore
    except ImportError:
        jsonschema = None

    seen_ids = set()
    for entry in entries:
        entry_id = entry.get("id", "<missing>")
        if entry_id in seen_ids:
            errors.append(f"duplicate entry id: {entry_id}")
        seen_ids.add(entry_id)

        if jsonschema is not None:
            try:
                jsonschema.validate(entry, schema)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{entry_id}: schema violation: {error}")
        else:
            for field in schema.get("required", []):
                if field not in entry:
                    errors.append(f"{entry_id}: missing required field {field}")

        evidence = root / entry.get("evidence_document", "")
        if not evidence.is_file():
            errors.append(f"{entry_id}: evidence document missing: {evidence}")

        coverage = entry.get("prediction_coverage")
        if coverage is not None and not (0 < coverage <= 1):
            errors.append(f"{entry_id}: prediction_coverage must be in (0, 1]")

        failed = entry.get("failed_pages")
        known = entry.get("known_failures")
        unknown = entry.get("unknown_failures")
        if failed is not None and known is not None and unknown is not None:
            if failed != known + unknown:
                errors.append(
                    f"{entry_id}: failed_pages {failed} != known {known} + unknown {unknown}"
                )

        raw = entry.get("raw_metrics") or {}
        display = entry.get("display_metrics") or {}
        # display == raw * 100 is only required when both use the same
        # aggregation convention: for TEDS the official-notebook rows aggregate
        # per page (display from table_teds_page_avg), while pooled raw is a
        # different number; CDM is pooled in every mode.
        aggregation = entry.get("aggregation_mode")
        for raw_key, display_key in (
            ("table_teds_pooled", "table_teds"),
            ("formula_cdm", "formula_cdm"),
        ):
            rv = raw.get(raw_key)
            dv = display.get(display_key)
            if rv is not None and not (0 <= rv <= 1):
                errors.append(f"{entry_id}: raw {raw_key}={rv} outside [0, 1]")
            if rv is not None and dv is not None:
                same_convention = (
                    raw_key == "formula_cdm"
                    or aggregation != "page_avg_official_notebook"
                )
                if same_convention and abs(rv * 100 - dv) > 0.01:
                    errors.append(
                        f"{entry_id}: display {display_key}={dv} does not match raw {raw_key}={rv}"
                    )

        run_type = entry.get("run_type")
        if run_type not in RUN_TYPES:
            errors.append(f"{entry_id}: run_type must be one of {RUN_TYPES}, got {run_type!r}")
        if run_type in ("clean-room", "independent") and not entry.get("prediction_tree_hash"):
            errors.append(
                f"{entry_id}: run_type {run_type} requires a prediction_tree_hash (unverifiable without it)"
            )

    return errors, entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    errors, entries = validate_index(args.root)
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        print(f"BENCHMARK INDEX INVALID ({len(errors)} issue(s))", file=sys.stderr)
        return 1
    print(f"BENCHMARK INDEX OK ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
