#!/usr/bin/env python3
"""Export taxonomy action queue as Markdown or CSV."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

FIELDS = [
    "severity",
    "action",
    "field",
    "field_label",
    "value",
    "count",
    "share",
    "href",
    "sample_slugs",
    "recommendation",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "severity",
    "action",
    "field",
    "value",
    "count",
    "href",
    "sample_slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader taxonomy governance actions.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing taxonomy_actions.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project"],
        default="markdown",
        help="Output format. Use 'project' for a task CSV suitable for project trackers.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include actions with this severity. Can be repeated.",
    )
    parser.add_argument(
        "--action",
        choices=["split_candidate", "merge_candidate", "unused_config", "watch"],
        action="append",
        help="Only include this action type. Can be repeated.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_actions(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "taxonomy_actions.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("taxonomy_actions.json has invalid 'actions' payload")
    return payload


def filter_actions(actions: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    severities = set(args.severity or [])
    action_types = set(args.action or [])
    filtered = []
    for item in actions:
        if severities and item.get("severity") not in severities:
            continue
        if action_types and item.get("action") not in action_types:
            continue
        filtered.append(item)
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(
        filtered,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or ""), 9),
            str(item.get("action") or ""),
            str(item.get("field") or ""),
            -int(item.get("count") or 0),
            str(item.get("value") or "").lower(),
        ),
    )


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def render_markdown(payload: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Taxonomy Action Queue",
        "",
        f"- Paper count: {payload.get('paper_count', 0)}",
        f"- Exported actions: {len(actions)}",
        f"- Split candidates: {summary.get('split_candidate', 0)}",
        f"- Merge candidates: {summary.get('merge_candidate', 0)}",
        f"- Unused config values: {summary.get('unused_config', 0)}",
        f"- Watch items: {summary.get('watch', 0)}",
        "",
    ]
    if not actions:
        lines.extend(["No taxonomy actions match the selected filters.", ""])
        return "\n".join(lines)

    current_group = ""
    for item in actions:
        group = f"{item.get('severity', 'unknown')} / {item.get('action', 'unknown')}"
        if group != current_group:
            current_group = group
            lines.extend([f"## {group}", ""])
        value = str(item.get("value") or "")
        href = str(item.get("href") or "")
        label = f"[{value}]({href})" if href else value
        samples = join_value(item.get("sample_slugs"))
        lines.append(
            f"- [ ] `{item.get('field')}` {label} "
            f"({item.get('count', 0)} papers, {round(float(item.get('share') or 0) * 100)}%)"
        )
        lines.append(f"  - Recommendation: {item.get('recommendation', '')}")
        if samples:
            lines.append(f"  - Samples: {samples}")
    lines.append("")
    return "\n".join(lines)


def render_csv(actions: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in actions:
        row = {field: join_value(item.get(field)) for field in FIELDS}
        writer.writerow(row)
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "")
    return {"high": "P1", "medium": "P2", "low": "P3"}.get(severity, "P3")


def task_title(item: dict[str, Any]) -> str:
    action_label = {
        "split_candidate": "Split taxonomy value",
        "merge_candidate": "Merge taxonomy value",
        "unused_config": "Review unused config",
        "watch": "Watch taxonomy value",
    }.get(str(item.get("action") or ""), str(item.get("action") or "Taxonomy task"))
    field = str(item.get("field") or "taxonomy")
    value = str(item.get("value") or "")
    return f"{action_label}: {field} / {value}".strip()


def task_body(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("recommendation") or ""),
        f"Count: {item.get('count', 0)}",
        f"Share: {round(float(item.get('share') or 0) * 100)}%",
    ]
    href = str(item.get("href") or "")
    if href:
        parts.append(f"View: {href}")
    samples = join_value(item.get("sample_slugs"))
    if samples:
        parts.append(f"Samples: {samples}")
    return " | ".join(part for part in parts if part)


def render_project_csv(actions: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(actions, start=1):
        action = str(item.get("action") or "")
        field = str(item.get("field") or "")
        severity = str(item.get("severity") or "")
        labels = "; ".join(label for label in ["taxonomy", action, field, severity] if label)
        row = {
            "task_id": f"tax-{index:03d}",
            "title": task_title(item),
            "status": args.task_status,
            "priority": priority_for(item),
            "assignee": args.assignee,
            "due_date": args.due_date,
            "labels": labels,
            "severity": severity,
            "action": action,
            "field": field,
            "value": join_value(item.get("value")),
            "count": join_value(item.get("count")),
            "href": join_value(item.get("href")),
            "sample_slugs": join_value(item.get("sample_slugs")),
            "body": task_body(item),
        }
        writer.writerow(row)
    return buffer.getvalue()


def write_output(text: str, output_path: str | None, report_dir: Path, stream: TextIO) -> None:
    if not output_path:
        stream.write(text)
        return
    path = Path(output_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix == ".md" and path.parent.resolve() == report_dir:
        raise ValueError(
            "Refusing to write a Markdown export into the report root; "
            "use a subdirectory such as docs/exports/ so build_wiki does not treat it as a paper."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"Exported taxonomy actions to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_actions(report_dir)
        actions = filter_actions(payload.get("actions", []), args)
        if args.format == "csv":
            text = render_csv(actions)
        elif args.format == "project":
            text = render_project_csv(actions, args)
        else:
            text = render_markdown(payload, actions)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
