#!/usr/bin/env python3
"""Export operational queues as Markdown, CSV, project tasks, or metadata patches."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

LIST_FIELDS = {"authors", "domains", "tracks", "problems", "topics", "methods"}

QUEUE_FIELDS = [
    "id",
    "label",
    "severity",
    "preset",
    "description",
    "recommended_fields",
    "count",
    "share",
    "href",
    "slugs",
    "sample_slugs",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "queue_id",
    "severity",
    "preset",
    "paper_count",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader operational queues.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing queues.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project", "patch"],
        default="markdown",
        help="Output format. Use 'patch' to generate apply_library_metadata.py input.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument("--queue", action="append", help="Only include this queue id. Can be repeated.")
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this severity. Can be repeated.",
    )
    parser.add_argument("--preset", action="append", help="Only include this preset id. Use manual for empty presets.")
    parser.add_argument("--min-count", type=int, default=0, help="Only include queues with at least this many papers.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered queues after sorting.")
    parser.add_argument("--field", help="Metadata field for --format patch.")
    parser.add_argument("--set-value", help="Metadata value for --format patch.")
    parser.add_argument(
        "--list-mode",
        choices=["replace", "append", "remove"],
        default="replace",
        help="List mode column used by --format patch for list metadata fields.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_queues(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "queues.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("queues"), list):
        raise ValueError("queues.json has invalid 'queues' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def queue_preset(item: dict[str, Any]) -> str:
    return str(item.get("preset") or "manual")


def sample_slugs(item: dict[str, Any]) -> list[str]:
    samples = item.get("sample_papers") or []
    if not isinstance(samples, list):
        return []
    return [
        str(sample.get("slug") or "").strip()
        for sample in samples
        if isinstance(sample, dict) and str(sample.get("slug") or "").strip()
    ]


def filter_queues(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    queue_ids = {str(value).strip() for value in (args.queue or []) if str(value).strip()}
    severities = set(args.severity or [])
    presets = {str(value).strip() for value in (args.preset or []) if str(value).strip()}
    rows = []
    for item in payload.get("queues", []):
        if not isinstance(item, dict):
            continue
        if queue_ids and str(item.get("id") or "") not in queue_ids:
            continue
        if severities and item.get("severity") not in severities:
            continue
        if presets and queue_preset(item) not in presets:
            continue
        if int(item.get("count") or 0) < args.min_count:
            continue
        rows.append(item)
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(
        rows,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or ""), 9),
            -int(item.get("count") or 0),
            str(item.get("label") or "").lower(),
        ),
    )
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Operational Queues",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Total queues: {payload.get('queue_count', 0)}",
        f"- Non-empty queues: {payload.get('non_empty_queue_count', 0)}",
        f"- Exported queues: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No queues match the selected filters.", ""])
        return "\n".join(lines)
    for item in rows:
        lines.extend(
            [
                f"## {item.get('label')} `{item.get('id')}`",
                "",
                f"- Severity: {item.get('severity')}",
                f"- Preset: {queue_preset(item)}",
                f"- Papers: {item.get('count')}",
                f"- Fields: {join_value(item.get('recommended_fields')) or '-'}",
                f"- View: {item.get('href') or '-'}",
                f"- Slugs: {join_value(item.get('slugs')) or '-'}",
                f"- Samples: {join_value(sample_slugs(item)) or '-'}",
                f"- Description: {item.get('description') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=QUEUE_FIELDS)
    writer.writeheader()
    for item in rows:
        writer.writerow(
            {
                field: join_value(sample_slugs(item)) if field == "sample_slugs" else join_value(item.get(field))
                for field in QUEUE_FIELDS
            }
        )
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "")
    if severity == "high":
        return "P1"
    if severity == "medium":
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
            for label in ["queue", str(item.get("severity") or ""), queue_preset(item)]
            if label
        )
        body_parts = [
            f"Description: {item.get('description') or '-'}",
            f"Recommended fields: {join_value(item.get('recommended_fields')) or '-'}",
            f"Samples: {join_value(sample_slugs(item)) or '-'}",
            f"View: {item.get('href') or '-'}",
        ]
        writer.writerow(
            {
                "task_id": f"queue-{index:03d}",
                "title": f"[queue] {item.get('label')} ({item.get('count')} papers)",
                "status": args.task_status,
                "priority": priority_for(item),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "queue_id": item.get("id"),
                "severity": item.get("severity"),
                "preset": queue_preset(item),
                "paper_count": item.get("count"),
                "href": item.get("href"),
                "slugs": join_value(item.get("slugs")),
                "body": " | ".join(body_parts),
            }
        )
    return buffer.getvalue()


def render_patch_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    if not args.field or args.set_value is None:
        raise ValueError("--format patch requires --field and --set-value")
    from io import StringIO

    slugs: list[str] = []
    seen: set[str] = set()
    for item in rows:
        for slug in item.get("slugs", []):
            text = str(slug).strip()
            if text and text not in seen:
                seen.add(text)
                slugs.append(text)
    field = str(args.field)
    fieldnames = ["slug", field, "_list_mode"] if field in LIST_FIELDS else ["slug", field]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for slug in slugs:
        row = {"slug": slug, field: args.set_value}
        if field in LIST_FIELDS:
            row["_list_mode"] = args.list_mode
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
    print(f"Exported queues to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_queues(report_dir)
        rows = filter_queues(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, args)
        elif args.format == "patch":
            text = render_patch_csv(rows, args)
        else:
            text = render_markdown(payload, rows)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
