#!/usr/bin/env python3
"""Export collection views as Markdown, CSV, or project tasks."""

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
    "type",
    "title",
    "href",
    "count",
    "note",
    "slugs",
    "sample_titles",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "collection_type",
    "collection_id",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader collection views.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing collections.json.",
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
        "--type",
        choices=["shared", "smart", "research_line"],
        action="append",
        help="Only include this collection type. Can be repeated.",
    )
    parser.add_argument(
        "--collection",
        action="append",
        help="Only include collections whose id, title, or name matches this value. Can be repeated.",
    )
    parser.add_argument("--min-count", type=int, default=0, help="Only include collections with at least this many papers.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_collections(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "collections.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("shared_views", "smart_collections", "research_lines"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"collections.json has invalid {key!r} payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def sample_titles(item: dict[str, Any]) -> list[str]:
    titles = []
    for paper in item.get("sample_papers", []):
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or "").strip()
        if title:
            titles.append(title)
    return titles


def normalized_collections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("shared_views", []):
        rows.append(
            {
                "id": str(item.get("name") or ""),
                "type": "shared",
                "title": str(item.get("name") or ""),
                "href": str(item.get("href") or ""),
                "count": int(item.get("count") or 0),
                "note": json.dumps(item.get("state") or {}, ensure_ascii=False, sort_keys=True),
                "slugs": item.get("slugs") or [],
                "sample_titles": sample_titles(item),
            }
        )
    for item in payload.get("smart_collections", []):
        rows.append(
            {
                "id": str(item.get("id") or ""),
                "type": "smart",
                "title": str(item.get("title") or item.get("id") or ""),
                "href": str(item.get("href") or ""),
                "count": int(item.get("count") or 0),
                "note": str(item.get("note") or ""),
                "slugs": item.get("slugs") or [],
                "sample_titles": sample_titles(item),
            }
        )
    for item in payload.get("research_lines", []):
        rows.append(
            {
                "id": str(item.get("name") or ""),
                "type": "research_line",
                "title": str(item.get("name") or ""),
                "href": str(item.get("href") or item.get("library_href") or ""),
                "count": int(item.get("count") or 0),
                "note": f"high_importance={item.get('high_importance', 0)}; needs_review_plan={item.get('needs_review_plan', 0)}",
                "slugs": item.get("slugs") or [],
                "sample_titles": sample_titles(item),
            }
        )
    return sorted(rows, key=lambda item: (str(item["type"]), -int(item["count"]), str(item["title"]).lower()))


def filter_collections(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    types = set(args.type or [])
    selected = {str(value).strip().lower() for value in (args.collection or []) if str(value).strip()}
    filtered = []
    for item in rows:
        if types and item["type"] not in types:
            continue
        if int(item["count"] or 0) < args.min_count:
            continue
        identity = {str(item.get("id") or "").lower(), str(item.get("title") or "").lower()}
        if selected and not selected.intersection(identity):
            continue
        filtered.append(item)
    return filtered


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Collections",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Shared views: {payload.get('shared_view_count', 0)}",
        f"- Smart collections: {payload.get('smart_collection_count', 0)}",
        f"- Research lines: {payload.get('research_line_count', 0)}",
        f"- Exported collections: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No collections match the selected filters.", ""])
        return "\n".join(lines)

    current_type = ""
    for item in rows:
        if item["type"] != current_type:
            current_type = item["type"]
            lines.extend([f"## {current_type}", ""])
        title = str(item["title"])
        identity = str(item.get("id") or "").strip()
        href = str(item.get("href") or "")
        label = f"[{title}]({href})" if href else title
        id_suffix = f" `{identity}`" if identity and identity != title else ""
        slugs = join_value(item.get("slugs"))
        samples = join_value(item.get("sample_titles"))
        lines.append(f"- [ ] {label} ({item['count']} papers){id_suffix}")
        if item.get("note"):
            lines.append(f"  - Note: {item['note']}")
        if slugs:
            lines.append(f"  - Slugs: {slugs}")
        if samples:
            lines.append(f"  - Samples: {samples}")
    lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    for item in rows:
        row = {field: join_value(item.get(field)) for field in FIELDS}
        writer.writerow(row)
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    count = int(item.get("count") or 0)
    if item.get("type") == "smart" and count:
        return "P1"
    if count >= 10:
        return "P1"
    if count >= 3:
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(rows, start=1):
        labels = "; ".join(label for label in ["collection", str(item.get("type") or "")] if label)
        body_parts = [
            str(item.get("note") or ""),
            f"View: {item.get('href')}" if item.get("href") else "",
            f"Slugs: {join_value(item.get('slugs'))}" if item.get("slugs") else "",
            f"Samples: {join_value(item.get('sample_titles'))}" if item.get("sample_titles") else "",
        ]
        writer.writerow(
            {
                "task_id": f"col-{index:03d}",
                "title": f"[{item.get('type')}] {item.get('title')}",
                "status": args.task_status,
                "priority": priority_for(item),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "collection_type": item.get("type"),
                "collection_id": item.get("id"),
                "href": item.get("href"),
                "slugs": join_value(item.get("slugs")),
                "body": " | ".join(part for part in body_parts if part),
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
    print(f"Exported collections to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_collections(report_dir)
        rows = filter_collections(normalized_collections(payload), args)
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
