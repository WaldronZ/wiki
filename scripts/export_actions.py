#!/usr/bin/env python3
"""Export the unified action queue as Markdown or CSV."""

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
    "id",
    "group",
    "severity",
    "priority",
    "title",
    "detail",
    "href",
    "source",
    "slugs",
    "command",
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
    "group",
    "source",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader unified action queue.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing actions.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project"],
        default="markdown",
        help="Output format. Use 'project' for task trackers.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument(
        "--group",
        action="append",
        help="Only include this action group, such as review, quality, taxonomy, dedupe, or inbox. Can be repeated.",
    )
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low", "none"],
        action="append",
        help="Only include actions with this severity. Can be repeated.",
    )
    parser.add_argument(
        "--source",
        action="append",
        help="Only include this source file, such as review.json or taxonomy_actions.json. Can be repeated.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_actions(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "actions.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        raise ValueError("actions.json has invalid 'actions' payload")
    return payload


def filter_actions(actions: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    groups = {str(group).strip() for group in (args.group or []) if str(group).strip()}
    severities = set(args.severity or [])
    sources = {str(source).strip() for source in (args.source or []) if str(source).strip()}
    filtered = []
    for item in actions:
        if groups and item.get("group") not in groups:
            continue
        if severities and item.get("severity") not in severities:
            continue
        if sources and item.get("source") not in sources:
            continue
        filtered.append(item)
    severity_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    return sorted(
        filtered,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or ""), 9),
            -int(item.get("priority") or 0),
            str(item.get("group") or ""),
            str(item.get("title") or "").lower(),
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
    groups = summary.get("groups") or {}
    severities = summary.get("severity") or {}
    lines = [
        "# AutoPaperReader Action Queue",
        "",
        f"- Total actions: {payload.get('count', len(actions))}",
        f"- Exported actions: {len(actions)}",
        f"- Groups: {', '.join(f'{key} {value}' for key, value in sorted(groups.items())) or 'none'}",
        f"- Severity: {', '.join(f'{key} {value}' for key, value in sorted(severities.items())) or 'none'}",
        "",
    ]
    if not actions:
        lines.extend(["No actions match the selected filters.", ""])
        return "\n".join(lines)

    current_group = ""
    for item in actions:
        group = f"{item.get('severity', 'unknown')} / {item.get('group', 'unknown')}"
        if group != current_group:
            current_group = group
            lines.extend([f"## {group}", ""])
        title = str(item.get("title") or "")
        href = str(item.get("href") or "")
        label = f"[{title}]({href})" if href else title
        source = str(item.get("source") or "")
        slugs = join_value(item.get("slugs"))
        command = str(item.get("command") or "")
        lines.append(f"- [ ] {label} `P{item.get('priority', 0)}`")
        lines.append(f"  - Detail: {item.get('detail', '')}")
        if source:
            lines.append(f"  - Source: {source}")
        if slugs:
            lines.append(f"  - Slugs: {slugs}")
        if command:
            lines.append(f"  - Command: `{command}`")
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
    if severity in {"high", "medium", "low"}:
        return {"high": "P1", "medium": "P2", "low": "P3"}[severity]
    priority = int(item.get("priority") or 0)
    if priority >= 80:
        return "P1"
    if priority >= 50:
        return "P2"
    return "P3"


def task_title(item: dict[str, Any]) -> str:
    group = str(item.get("group") or "action")
    title = str(item.get("title") or "Untitled action")
    return f"[{group}] {title}"


def task_body(item: dict[str, Any]) -> str:
    parts = [str(item.get("detail") or "")]
    href = str(item.get("href") or "")
    if href:
        parts.append(f"View: {href}")
    source = str(item.get("source") or "")
    if source:
        parts.append(f"Source: {source}")
    slugs = join_value(item.get("slugs"))
    if slugs:
        parts.append(f"Slugs: {slugs}")
    command = str(item.get("command") or "")
    if command:
        parts.append(f"Command: {command}")
    return " | ".join(part for part in parts if part)


def render_project_csv(actions: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(actions, start=1):
        group = str(item.get("group") or "")
        severity = str(item.get("severity") or "")
        source = str(item.get("source") or "")
        labels = "; ".join(label for label in ["action_center", group, severity, source] if label)
        row = {
            "task_id": f"act-{index:03d}",
            "title": task_title(item),
            "status": args.task_status,
            "priority": priority_for(item),
            "assignee": args.assignee,
            "due_date": args.due_date,
            "labels": labels,
            "severity": severity,
            "group": group,
            "source": source,
            "href": join_value(item.get("href")),
            "slugs": join_value(item.get("slugs")),
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
    print(f"Exported unified actions to {path}")


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
