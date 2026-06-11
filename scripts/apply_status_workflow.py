#!/usr/bin/env python3
"""Apply a status workflow JSON snippet to guides/taxonomy.json.

The command is dry-run by default. It accepts the JSON downloaded from
docs/taxonomy.html, or a single workflow object with name/status values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
WORKFLOW_FIELDS = ("status_values", "reading_stage_values", "review_stage_values")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a status workflow snippet to taxonomy.json.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing guides/taxonomy.json.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Workflow JSON path. Relative paths are resolved from the current directory, report_dir, then repo root.",
    )
    parser.add_argument(
        "--taxonomy-json",
        default="guides/taxonomy.json",
        help="taxonomy config path, absolute or relative to report_dir.",
    )
    parser.add_argument("--workflow", help="Workflow name to activate or use for a single-workflow input.")
    parser.add_argument(
        "--no-sync-root",
        action="store_true",
        help="Do not mirror the active workflow into root status_values/reading_stage_values/review_stage_values.",
    )
    parser.add_argument("--write", action="store_true", help="Write taxonomy.json instead of printing a dry-run preview.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def resolve_inside_report(report_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = report_dir / path
    return path.resolve()


def resolve_input_path(report_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    for candidate in (Path.cwd() / path, report_dir / path, ROOT / path):
        if candidate.exists():
            return candidate.resolve()
    return (Path.cwd() / path).resolve()


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def display_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def clean_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit(f"{label} must be a list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise SystemExit(f"{label}[{index}] must be a non-empty string")
        text = item.strip()
        if text in seen:
            raise SystemExit(f"{label} has duplicate value: {text}")
        seen.add(text)
        cleaned.append(text)
    if not cleaned:
        raise SystemExit(f"{label} must not be empty")
    return cleaned


def clean_workflow(value: Any, label: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be an object")
    unknown = sorted(set(value) - set(WORKFLOW_FIELDS))
    if unknown:
        raise SystemExit(f"{label} has unknown keys: {', '.join(unknown)}")
    missing = [field for field in WORKFLOW_FIELDS if field not in value]
    if missing:
        raise SystemExit(f"{label} is missing required keys: {', '.join(missing)}")
    return {field: clean_string_list(value[field], f"{label}.{field}") for field in WORKFLOW_FIELDS}


def parse_workflow_payload(payload: dict[str, Any], selected_name: str | None) -> tuple[str, dict[str, dict[str, list[str]]]]:
    if "status_workflows" in payload:
        unknown = sorted(set(payload) - {"active_status_workflow", "status_workflows"})
        if unknown:
            raise SystemExit(f"workflow payload has unknown keys: {', '.join(unknown)}")
        workflows_raw = payload.get("status_workflows")
        if not isinstance(workflows_raw, dict):
            raise SystemExit("workflow payload status_workflows must be an object")
        workflows: dict[str, dict[str, list[str]]] = {}
        for name, workflow in workflows_raw.items():
            workflow_name = str(name).strip()
            if not workflow_name:
                raise SystemExit("workflow names must be non-empty strings")
            workflows[workflow_name] = clean_workflow(workflow, f"status_workflows.{workflow_name}")
        active_name = str(selected_name or payload.get("active_status_workflow") or "").strip()
        if not active_name:
            raise SystemExit("active_status_workflow is required")
        if active_name not in workflows:
            raise SystemExit(f"active workflow '{active_name}' is not defined in status_workflows")
        return active_name, workflows

    workflow_name = str(selected_name or payload.get("name") or payload.get("active_status_workflow") or "").strip()
    if not workflow_name:
        raise SystemExit("single workflow input requires --workflow or a non-empty name")
    workflow_source = {field: payload[field] for field in WORKFLOW_FIELDS if field in payload}
    return workflow_name, {workflow_name: clean_workflow(workflow_source, workflow_name)}


def merge_workflows(
    taxonomy: dict[str, Any],
    active_name: str,
    incoming: dict[str, dict[str, list[str]]],
    sync_root: bool,
) -> tuple[dict[str, Any], list[str]]:
    existing_raw = taxonomy.get("status_workflows") or {}
    if not isinstance(existing_raw, dict):
        raise SystemExit("taxonomy.json status_workflows must be an object")

    merged = dict(taxonomy)
    workflows: dict[str, Any] = dict(existing_raw)
    changes: list[str] = []
    for name, workflow in incoming.items():
        previous = workflows.get(name)
        action = "ADD" if previous is None else ("OK" if previous == workflow else "UPDATE")
        changes.append(f"{action} workflow {name}")
        workflows[name] = workflow

    previous_active = str(merged.get("active_status_workflow") or "").strip()
    if previous_active != active_name:
        changes.append(f"SET active_status_workflow {previous_active or '<unset>'} -> {active_name}")
    else:
        changes.append(f"OK active_status_workflow {active_name}")
    merged["active_status_workflow"] = active_name
    merged["status_workflows"] = workflows

    if sync_root:
        active_workflow = workflows[active_name]
        for field in WORKFLOW_FIELDS:
            if merged.get(field) != active_workflow[field]:
                changes.append(f"SYNC {field} from {active_name}")
            else:
                changes.append(f"OK {field} already matches {active_name}")
            merged[field] = active_workflow[field]
    return merged, changes


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    input_path = resolve_input_path(report_dir, args.input)
    taxonomy_path = resolve_inside_report(report_dir, args.taxonomy_json)
    payload = load_json_object(input_path)
    taxonomy = load_json_object(taxonomy_path)
    active_name, workflows = parse_workflow_payload(payload, args.workflow)
    updated, changes = merge_workflows(taxonomy, active_name, workflows, not args.no_sync_root)

    print(f"input: {display_path(input_path, report_dir)}")
    print(f"taxonomy: {display_path(taxonomy_path, report_dir)}")
    for change in changes:
        print(f"{'WRITE' if args.write else 'DRY'}  {change}")

    if args.write:
        taxonomy_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {display_path(taxonomy_path, report_dir)}")
    else:
        print("Run again with --write to apply this workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
