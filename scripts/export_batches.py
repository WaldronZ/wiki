#!/usr/bin/env python3
"""Export paper batches as Markdown, CSV, project tasks, or metadata patches."""

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

BATCH_FIELDS = [
    "id",
    "dimension",
    "dimension_label",
    "value",
    "severity",
    "priority",
    "count",
    "latest_year",
    "high_importance",
    "missing_review",
    "due_review",
    "missing_taxonomy",
    "no_code",
    "recommended_action",
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
    "batch_id",
    "dimension",
    "value",
    "severity",
    "paper_count",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader paper batches.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing batch.json.",
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
    parser.add_argument("--batch", action="append", help="Only include this batch id. Can be repeated.")
    parser.add_argument("--dimension", action="append", help="Only include this dimension key. Can be repeated.")
    parser.add_argument("--value", action="append", help="Only include this batch value. Can be repeated.")
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this severity. Can be repeated.",
    )
    parser.add_argument(
        "--gap",
        choices=["review", "due_review", "taxonomy", "code"],
        action="append",
        help="Only include batches with this non-zero gap. Can be repeated.",
    )
    parser.add_argument("--min-count", type=int, default=0, help="Only include batches with at least this many papers.")
    parser.add_argument("--min-priority", type=int, default=0, help="Only include batches with at least this priority.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered batches after sorting.")
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


def load_batches(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "batch.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("batches"), list):
        raise ValueError("batch.json has invalid 'batches' payload")
    if not isinstance(payload.get("dimensions"), list):
        raise ValueError("batch.json has invalid 'dimensions' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def gap_value(item: dict[str, Any], gap: str) -> int:
    key = {
        "review": "missing_review",
        "due_review": "due_review",
        "taxonomy": "missing_taxonomy",
        "code": "no_code",
    }[gap]
    return int(item.get(key) or 0)


def filter_batches(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    batch_ids = {str(value).strip() for value in (args.batch or []) if str(value).strip()}
    dimensions = {str(value).strip() for value in (args.dimension or []) if str(value).strip()}
    values = {str(value).strip().lower() for value in (args.value or []) if str(value).strip()}
    severities = set(args.severity or [])
    gaps = list(args.gap or [])
    rows = []
    for item in payload.get("batches", []):
        if not isinstance(item, dict):
            continue
        if batch_ids and str(item.get("id") or "") not in batch_ids:
            continue
        if dimensions and str(item.get("dimension") or "") not in dimensions:
            continue
        if values and str(item.get("value") or "").lower() not in values:
            continue
        if severities and item.get("severity") not in severities:
            continue
        if int(item.get("count") or 0) < args.min_count:
            continue
        if int(item.get("priority") or 0) < args.min_priority:
            continue
        if gaps and not any(gap_value(item, gap) > 0 for gap in gaps):
            continue
        rows.append(item)
    rows = sorted(rows, key=lambda item: (-int(item.get("priority") or 0), str(item.get("dimension") or ""), str(item.get("value") or "")))
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Paper Batches",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Dimensions: {payload.get('dimension_count', 0)}",
        f"- Total batches: {payload.get('batch_count', 0)}",
        f"- Exported batches: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No batches match the selected filters.", ""])
        return "\n".join(lines)
    for item in rows:
        lines.extend(
            [
                f"## {item.get('dimension_label') or item.get('dimension')} / {item.get('value')} `{item.get('id')}`",
                "",
                f"- Severity: {item.get('severity')} / priority {item.get('priority')}",
                f"- Papers: {item.get('count')}",
                f"- Latest year: {item.get('latest_year') or '-'}",
                f"- Gaps: missing_review={item.get('missing_review', 0)}, due_review={item.get('due_review', 0)}, missing_taxonomy={item.get('missing_taxonomy', 0)}, no_code={item.get('no_code', 0)}",
                f"- Action: {item.get('recommended_action') or '-'}",
                f"- View: {item.get('href') or '-'}",
                f"- Slugs: {join_value(item.get('slugs')) or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=BATCH_FIELDS)
    writer.writeheader()
    for item in rows:
        writer.writerow({field: join_value(item.get(field)) for field in BATCH_FIELDS})
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "")
    priority = int(item.get("priority") or 0)
    if severity == "high" or priority >= 75:
        return "P1"
    if severity == "medium" or priority >= 35:
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
            for label in ["batch", str(item.get("dimension") or ""), str(item.get("severity") or "")]
            if label
        )
        body_parts = [
            f"Action: {item.get('recommended_action') or '-'}",
            f"Gaps: missing_review={item.get('missing_review', 0)}, due_review={item.get('due_review', 0)}, missing_taxonomy={item.get('missing_taxonomy', 0)}, no_code={item.get('no_code', 0)}",
            f"Samples: {join_value(item.get('sample_slugs')) or '-'}",
            f"View: {item.get('href') or '-'}",
            f"Export command: {item.get('export_command') or '-'}",
        ]
        writer.writerow(
            {
                "task_id": f"batch-{index:03d}",
                "title": f"[{item.get('dimension')}] {item.get('value')}: {item.get('recommended_action')}",
                "status": args.task_status,
                "priority": priority_for(item),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "batch_id": item.get("id"),
                "dimension": item.get("dimension"),
                "value": item.get("value"),
                "severity": item.get("severity"),
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
    buffer = StringIO()
    field = str(args.field)
    fieldnames = ["slug", field, "_list_mode"] if field in LIST_FIELDS else ["slug", field]
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
    print(f"Exported batches to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_batches(report_dir)
        rows = filter_batches(payload, args)
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
