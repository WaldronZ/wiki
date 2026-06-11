#!/usr/bin/env python3
"""Export research roadmap plans as Markdown, CSV, or project tasks."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

ROADMAP_FIELDS = [
    "id",
    "line",
    "owner",
    "team",
    "cadence",
    "risk",
    "score",
    "count",
    "first_year",
    "latest_year",
    "missing_roles",
    "top_topics",
    "top_methods",
    "top_action",
    "href",
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
    "risk",
    "score",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader research roadmaps.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing roadmap.json.",
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
        "--risk",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this roadmap risk. Can be repeated.",
    )
    parser.add_argument("--owner", action="append", help="Only include this owner. Can be repeated.")
    parser.add_argument("--line", action="append", help="Only include this research line or roadmap id. Can be repeated.")
    parser.add_argument("--role-gap", choices=["yes", "no"], help="Filter by whether the line has missing roles.")
    parser.add_argument("--min-count", type=int, default=0, help="Only include lines with at least this many papers.")
    parser.add_argument("--min-score", type=int, default=0, help="Only include lines with at least this roadmap score.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_roadmap(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "roadmap.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("roadmaps"), list):
        raise ValueError("roadmap.json has invalid 'roadmaps' payload")
    if not isinstance(payload.get("actions"), list):
        raise ValueError("roadmap.json has invalid 'actions' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def count_names(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    names = []
    for item in values:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            count = item.get("count")
            if name:
                names.append(f"{name} ({count})" if count is not None else name)
        elif str(item).strip():
            names.append(str(item).strip())
    return "; ".join(names)


def paper_titles(item: dict[str, Any]) -> str:
    titles = []
    for paper in item.get("representative_papers", []):
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or "").strip()
        role = str(paper.get("role") or "").strip()
        if title:
            titles.append(f"{title} [{role}]" if role else title)
    return "; ".join(titles)


def top_action(item: dict[str, Any]) -> dict[str, Any]:
    actions = item.get("actions") if isinstance(item.get("actions"), list) else []
    if actions:
        action = actions[0]
        return action if isinstance(action, dict) else {}
    return {
        "type": "maintain",
        "priority": 10,
        "label": "保持路线图维护",
        "href": item.get("href") or item.get("library_href") or "",
        "slugs": [],
    }


def filter_roadmaps(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    risks = set(args.risk or [])
    owners = {str(value).strip().lower() for value in (args.owner or []) if str(value).strip()}
    lines = {str(value).strip().lower() for value in (args.line or []) if str(value).strip()}
    rows = []
    for item in payload.get("roadmaps", []):
        if not isinstance(item, dict):
            continue
        if risks and item.get("risk") not in risks:
            continue
        owner = str(item.get("owner") or "").strip().lower()
        if owners and owner not in owners:
            continue
        identities = {str(item.get("id") or "").lower(), str(item.get("line") or "").lower()}
        if lines and not lines.intersection(identities):
            continue
        missing_roles = item.get("missing_roles") if isinstance(item.get("missing_roles"), list) else []
        if args.role_gap == "yes" and not missing_roles:
            continue
        if args.role_gap == "no" and missing_roles:
            continue
        if int(item.get("count") or 0) < args.min_count:
            continue
        if int(item.get("score") or 0) < args.min_score:
            continue
        rows.append(item)
    return sorted(rows, key=lambda item: (-int(item.get("score") or 0), str(item.get("line") or "").lower()))


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Research Roadmap",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Research lines: {payload.get('line_count', 0)}",
        f"- Exported roadmaps: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No roadmaps match the selected filters.", ""])
        return "\n".join(lines)

    for item in rows:
        action_items = [
            action
            for action in item.get("actions", [])
            if isinstance(action, dict)
        ]
        if not action_items:
            action_items = [top_action(item)]
        lines.extend(
            [
                f"## {item.get('line')} `{item.get('id')}`",
                "",
                f"- Owner: {item.get('owner') or 'unassigned'}",
                f"- Team: {item.get('team') or '-'}",
                f"- Cadence: {item.get('cadence') or '-'}",
                f"- Risk: {item.get('risk')} / score {item.get('score')}",
                f"- Papers: {item.get('count')} ({item.get('first_year') or '-'}-{item.get('latest_year') or '-'})",
                f"- Missing roles: {join_value(item.get('missing_roles')) or '-'}",
                f"- Representative papers: {paper_titles(item) or '-'}",
                "",
                "### Actions",
            ]
        )
        for action in action_items:
            href = str(action.get("href") or item.get("href") or "")
            label = str(action.get("label") or action.get("type") or "Maintain roadmap")
            link = f" ([open]({href}))" if href else ""
            lines.append(f"- [ ] {label}{link}")
        lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ROADMAP_FIELDS)
    writer.writeheader()
    for item in rows:
        action = top_action(item)
        writer.writerow(
            {
                "id": item.get("id"),
                "line": item.get("line"),
                "owner": item.get("owner"),
                "team": item.get("team"),
                "cadence": item.get("cadence"),
                "risk": item.get("risk"),
                "score": item.get("score"),
                "count": item.get("count"),
                "first_year": item.get("first_year"),
                "latest_year": item.get("latest_year"),
                "missing_roles": join_value(item.get("missing_roles")),
                "top_topics": count_names(item.get("top_topics")),
                "top_methods": count_names(item.get("top_methods")),
                "top_action": action.get("label"),
                "href": item.get("href"),
            }
        )
    return buffer.getvalue()


def priority_for(risk: str, score: int, action_priority: int) -> str:
    if risk == "high" or score >= 75 or action_priority >= 70:
        return "P1"
    if risk == "medium" or score >= 45 or action_priority >= 35:
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    task_index = 1
    for item in rows:
        actions = [
            action
            for action in item.get("actions", [])
            if isinstance(action, dict)
        ] or [top_action(item)]
        for action in actions:
            action_type = str(action.get("type") or "maintain")
            action_priority = int(action.get("priority") or 0)
            risk = str(item.get("risk") or "")
            score = int(item.get("score") or 0)
            slugs = action.get("slugs") if isinstance(action.get("slugs"), list) else []
            labels = "; ".join(label for label in ["roadmap", risk, action_type] if label)
            body_parts = [
                f"Line: {item.get('line')}",
                f"Owner: {item.get('owner') or 'unassigned'}",
                f"Missing roles: {join_value(item.get('missing_roles')) or '-'}",
                f"Representative papers: {paper_titles(item) or '-'}",
                f"View: {action.get('href') or item.get('href') or ''}",
            ]
            writer.writerow(
                {
                    "task_id": f"roadmap-{task_index:03d}",
                    "title": f"[{action_type}] {item.get('line')}: {action.get('label')}",
                    "status": args.task_status,
                    "priority": priority_for(risk, score, action_priority),
                    "assignee": args.assignee,
                    "due_date": args.due_date,
                    "labels": labels,
                    "line": item.get("line"),
                    "action_type": action_type,
                    "risk": risk,
                    "score": score,
                    "href": action.get("href") or item.get("href"),
                    "slugs": join_value(slugs),
                    "body": " | ".join(body_parts),
                }
            )
            task_index += 1
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
    print(f"Exported roadmap to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_roadmap(report_dir)
        rows = filter_roadmaps(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, args)
        else:
            text = render_markdown(payload, rows)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
