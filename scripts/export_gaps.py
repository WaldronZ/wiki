#!/usr/bin/env python3
"""Export research gap actions as Markdown, CSV, or project tasks."""

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
    "line",
    "score",
    "priority",
    "type",
    "label",
    "latest_year",
    "href",
    "slugs",
    "missing_roles",
    "missing_taxonomy_slugs",
    "taxonomy_load_slugs",
    "no_review_slugs",
    "no_code_slugs",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "line",
    "action_type",
    "score",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader research gap actions.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing gaps.json.",
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
    parser.add_argument("--line", action="append", help="Only include this research line. Can be repeated.")
    parser.add_argument("--action-type", action="append", help="Only include this action type. Can be repeated.")
    parser.add_argument("--max-score", type=int, default=100, help="Only include lines at or below this health score.")
    parser.add_argument("--min-priority", type=int, default=0, help="Only include actions with at least this priority.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered actions.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_gaps(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "gaps.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("actions"), list):
        raise ValueError("gaps.json has invalid 'actions' payload")
    if not isinstance(payload.get("lines"), list):
        raise ValueError("gaps.json has invalid 'lines' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def line_score_map(payload: dict[str, Any]) -> dict[str, int]:
    return {
        str(item.get("line") or ""): int(item.get("score") or 0)
        for item in payload.get("lines", [])
        if isinstance(item, dict)
    }


def line_detail_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("line") or ""): item
        for item in payload.get("lines", [])
        if isinstance(item, dict)
    }


def filtered_actions(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    lines = {str(value).strip().lower() for value in (args.line or []) if str(value).strip()}
    action_types = {str(value).strip() for value in (args.action_type or []) if str(value).strip()}
    scores = line_score_map(payload)
    line_details = line_detail_map(payload)
    actions = []
    for action in payload.get("actions", []):
        if not isinstance(action, dict):
            continue
        line = str(action.get("line") or "")
        if lines and line.lower() not in lines:
            continue
        if action_types and str(action.get("type") or "") not in action_types:
            continue
        if int(action.get("priority") or 0) < args.min_priority:
            continue
        if scores.get(line, 100) > args.max_score:
            continue
        row = dict(action)
        row["score"] = scores.get(line, "")
        detail = line_details.get(line, {})
        for key in ("missing_roles", "missing_taxonomy_slugs", "taxonomy_load_slugs", "no_review_slugs", "no_code_slugs"):
            row[key] = detail.get(key) or []
        actions.append(row)
    actions = sorted(actions, key=lambda item: (-int(item.get("priority") or 0), str(item.get("line") or ""), str(item.get("label") or "")))
    if args.top > 0:
        actions = actions[: args.top]
    return actions


def project_priority(action: dict[str, Any]) -> str:
    priority = int(action.get("priority") or 0)
    score = int(action.get("score") or 100)
    if priority >= 70 or score < 50:
        return "P1"
    if priority >= 35 or score < 75:
        return "P2"
    return "P3"


def render_markdown(payload: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Research Gaps",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Research lines: {payload.get('line_count', 0)}",
        f"- Exported actions: {len(actions)}",
        "",
    ]
    if not actions:
        lines.extend(["No gap actions match the selected filters.", ""])
        return "\n".join(lines)
    for action in actions:
        lines.extend(
            [
                f"- [ ] {action.get('line')}: {action.get('label')}",
                f"  - Priority: {action.get('priority')} / score {action.get('score')}",
                f"  - Type: {action.get('type')}",
                f"  - Slugs: {join_value(action.get('slugs')) or '-'}",
                f"  - Missing roles: {join_value(action.get('missing_roles')) or '-'}",
                f"  - View: {action.get('href') or '-'}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_csv(actions: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    for action in actions:
        writer.writerow({field: join_value(action.get(field)) for field in FIELDS})
    return buffer.getvalue()


def render_project_csv(actions: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, action in enumerate(actions, start=1):
        labels = "; ".join(label for label in ["gap", str(action.get("type") or "")] if label)
        body = " | ".join(
            [
                f"Line: {action.get('line')}",
                f"Latest year: {action.get('latest_year') or 'unknown'}",
                f"Slugs: {join_value(action.get('slugs')) or '-'}",
                f"Missing roles: {join_value(action.get('missing_roles')) or '-'}",
                f"Missing taxonomy: {join_value(action.get('missing_taxonomy_slugs')) or '-'}",
                f"View: {action.get('href') or '-'}",
            ]
        )
        writer.writerow(
            {
                "task_id": f"gap-{index:03d}",
                "title": f"[{action.get('type')}] {action.get('line')}: {action.get('label')}",
                "status": args.task_status,
                "priority": project_priority(action),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "line": action.get("line"),
                "action_type": action.get("type"),
                "score": action.get("score"),
                "href": action.get("href"),
                "slugs": join_value(action.get("slugs")),
                "body": body,
            }
        )
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
    print(f"Exported gaps to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_gaps(report_dir)
        actions = filtered_actions(payload, args)
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
