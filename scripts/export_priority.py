#!/usr/bin/env python3
"""Export the paper priority queue as Markdown, CSV, project tasks, or review patches."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

PRIORITY_FIELDS = [
    "slug",
    "priority_score",
    "urgency",
    "category",
    "category_label",
    "recommended_action",
    "research_line",
    "line_role",
    "status",
    "reading_stage",
    "review_state",
    "next_review",
    "suggested_next_review",
    "reasons",
    "queue_hits",
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
    "slug",
    "urgency",
    "category",
    "priority_score",
    "research_line",
    "href",
    "body",
]

REVIEW_PATCH_FIELDS = ["slug", "next_review", "review_stage", "source_field", "source_value", "display_title", "href"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader paper priority queue.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing priority.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project", "review-patch"],
        default="markdown",
        help="Output format. Use review-patch to generate apply_library_metadata.py input.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument(
        "--urgency",
        choices=["high", "medium", "low", "watch"],
        action="append",
        help="Only include this urgency. Can be repeated.",
    )
    parser.add_argument("--category", action="append", help="Only include this priority category. Can be repeated.")
    parser.add_argument("--line", action="append", help="Only include this research line. Can be repeated.")
    parser.add_argument("--slug", action="append", help="Only include this paper slug. Can be repeated.")
    parser.add_argument("--min-score", type=int, default=0, help="Only include papers with at least this priority_score.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered papers after sorting.")
    parser.add_argument(
        "--needs-review-plan",
        action="store_true",
        help="Only include papers whose review_state is needs_plan.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_priority(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "priority.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("items"), list):
        raise ValueError("priority.json has invalid 'items' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(join_value(item) if isinstance(item, list) else str(item) for item in value)
    if isinstance(value, dict):
        label = value.get("label") or value.get("id") or value.get("href") or ""
        return str(label)
    return str(value)


def queue_labels(item: dict[str, Any]) -> str:
    return "; ".join(
        str(queue.get("label") or queue.get("id") or "")
        for queue in item.get("queue_hits", [])
        if isinstance(queue, dict) and (queue.get("label") or queue.get("id"))
    )


def filter_items(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    urgencies = set(args.urgency or [])
    categories = {str(value).strip() for value in (args.category or []) if str(value).strip()}
    lines = {str(value).strip() for value in (args.line or []) if str(value).strip()}
    slugs = {str(value).strip() for value in (args.slug or []) if str(value).strip()}
    rows = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        if urgencies and item.get("urgency") not in urgencies:
            continue
        if categories and str(item.get("category") or "") not in categories:
            continue
        if lines and str(item.get("research_line") or "") not in lines:
            continue
        if slugs and str(item.get("slug") or "") not in slugs:
            continue
        if int(item.get("priority_score") or 0) < args.min_score:
            continue
        if args.needs_review_plan and item.get("review_state") != "needs_plan":
            continue
        rows.append(item)
    urgency_rank = {"high": 0, "medium": 1, "low": 2, "watch": 3}
    rows = sorted(
        rows,
        key=lambda item: (
            urgency_rank.get(str(item.get("urgency") or ""), 9),
            -int(item.get("priority_score") or 0),
            str(item.get("research_line") or ""),
            str(item.get("title_zh") or item.get("title") or item.get("slug") or "").lower(),
        ),
    )
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# AutoPaperReader Priority Queue",
        "",
        f"- Papers: {payload.get('count', len(rows))}",
        f"- Exported papers: {len(rows)}",
        f"- Urgency: {', '.join(f'{key} {value}' for key, value in sorted((summary.get('urgency') or {}).items())) or 'none'}",
        f"- Categories: {', '.join(f'{key} {value}' for key, value in sorted((summary.get('categories') or {}).items())) or 'none'}",
        "",
    ]
    if not rows:
        lines.extend(["No priority items match the selected filters.", ""])
        return "\n".join(lines)
    current = ""
    for item in rows:
        group = f"{item.get('urgency', 'unknown')} / {item.get('category_label') or item.get('category') or 'unknown'}"
        if group != current:
            current = group
            lines.extend([f"## {group}", ""])
        title = str(item.get("title_zh") or item.get("title") or item.get("slug") or "")
        href = str(item.get("href") or "")
        label = f"[{title}]({href})" if href else title
        reasons = join_value(item.get("reasons")) or "-"
        queues = queue_labels(item) or "-"
        lines.append(f"- [ ] {label} `P{item.get('priority_score', 0)}`")
        lines.append(f"  - Action: {item.get('recommended_action') or '-'}")
        lines.append(f"  - Line: {item.get('research_line') or 'Unassigned'}")
        lines.append(f"  - Reasons: {reasons}")
        lines.append(f"  - Queues: {queues}")
    lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PRIORITY_FIELDS)
    writer.writeheader()
    for item in rows:
        row = {field: join_value(item.get(field)) for field in PRIORITY_FIELDS}
        row["queue_hits"] = queue_labels(item)
        writer.writerow(row)
    return buffer.getvalue()


def project_priority(item: dict[str, Any]) -> str:
    urgency = str(item.get("urgency") or "")
    if urgency == "high":
        return "P1"
    if urgency == "medium":
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(rows, start=1):
        labels = "; ".join(
            label
            for label in ["priority", str(item.get("urgency") or ""), str(item.get("category") or "")]
            if label
        )
        body_parts = [
            f"Recommended action: {item.get('recommended_action') or '-'}",
            f"Reasons: {join_value(item.get('reasons')) or '-'}",
            f"Queues: {queue_labels(item) or '-'}",
            f"View: {item.get('href') or '-'}",
        ]
        writer.writerow(
            {
                "task_id": f"prio-{index:03d}",
                "title": f"[priority] {item.get('title_zh') or item.get('title') or item.get('slug')}",
                "status": args.task_status,
                "priority": project_priority(item),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "slug": item.get("slug"),
                "urgency": item.get("urgency"),
                "category": item.get("category"),
                "priority_score": item.get("priority_score"),
                "research_line": item.get("research_line"),
                "href": item.get("href"),
                "body": " | ".join(body_parts),
            }
        )
    return buffer.getvalue()


def render_review_patch_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_PATCH_FIELDS)
    writer.writeheader()
    for item in rows:
        if item.get("review_state") != "needs_plan" or not item.get("suggested_next_review"):
            continue
        writer.writerow(
            {
                "slug": item.get("slug"),
                "next_review": item.get("suggested_next_review"),
                "review_stage": item.get("review_stage") or "fresh",
                "source_field": "review_state",
                "source_value": item.get("review_state") or "",
                "display_title": item.get("title_zh") or item.get("title") or item.get("slug"),
                "href": item.get("href") or "",
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
    print(f"Exported priority queue to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_priority(report_dir)
        rows = filter_items(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, args)
        elif args.format == "review-patch":
            text = render_review_patch_csv(rows)
        else:
            text = render_markdown(payload, rows)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
