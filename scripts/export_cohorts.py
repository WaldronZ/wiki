#!/usr/bin/env python3
"""Export taxonomy cohorts as Markdown, CSV, project tasks, or metadata patches."""

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

COHORT_FIELDS = [
    "id",
    "label",
    "pair",
    "primary_field",
    "primary_value",
    "secondary_field",
    "secondary_value",
    "count",
    "share",
    "action",
    "severity",
    "href",
    "recommendation",
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
    "cohort_id",
    "pair",
    "action",
    "severity",
    "paper_count",
    "href",
    "slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader taxonomy cohorts.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing cohorts.json.",
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
    parser.add_argument("--cohort", action="append", help="Only include this cohort id. Can be repeated.")
    parser.add_argument("--pair", action="append", help="Only include this pair label. Can be repeated.")
    parser.add_argument("--primary-field", action="append", help="Only include this primary field. Can be repeated.")
    parser.add_argument("--secondary-field", action="append", help="Only include this secondary field. Can be repeated.")
    parser.add_argument(
        "--action",
        choices=["singleton", "split_candidate", "topic_candidate", "watch"],
        action="append",
        help="Only include this cohort action. Can be repeated.",
    )
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this severity. Can be repeated.",
    )
    parser.add_argument("--min-count", type=int, default=0, help="Only include cohorts with at least this many papers.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered cohorts after sorting.")
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


def load_cohorts(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "cohorts.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("cohorts"), list):
        raise ValueError("cohorts.json has invalid 'cohorts' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def sample_slugs(item: dict[str, Any]) -> list[str]:
    samples = item.get("sample_papers") or []
    if not isinstance(samples, list):
        return []
    return [
        str(sample.get("slug") or "").strip()
        for sample in samples
        if isinstance(sample, dict) and str(sample.get("slug") or "").strip()
    ]


def filter_cohorts(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    cohort_ids = {str(value).strip() for value in (args.cohort or []) if str(value).strip()}
    pairs = {str(value).strip() for value in (args.pair or []) if str(value).strip()}
    primary_fields = {str(value).strip() for value in (args.primary_field or []) if str(value).strip()}
    secondary_fields = {str(value).strip() for value in (args.secondary_field or []) if str(value).strip()}
    actions = set(args.action or [])
    severities = set(args.severity or [])
    rows = []
    for item in payload.get("cohorts", []):
        if not isinstance(item, dict):
            continue
        if cohort_ids and str(item.get("id") or "") not in cohort_ids:
            continue
        if pairs and str(item.get("pair") or "") not in pairs:
            continue
        if primary_fields and str(item.get("primary_field") or "") not in primary_fields:
            continue
        if secondary_fields and str(item.get("secondary_field") or "") not in secondary_fields:
            continue
        if actions and item.get("action") not in actions:
            continue
        if severities and item.get("severity") not in severities:
            continue
        if int(item.get("count") or 0) < args.min_count:
            continue
        rows.append(item)
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    action_rank = {"split_candidate": 0, "singleton": 1, "topic_candidate": 2, "watch": 3}
    rows = sorted(
        rows,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or ""), 9),
            action_rank.get(str(item.get("action") or ""), 9),
            -int(item.get("count") or 0),
            str(item.get("pair") or ""),
            str(item.get("label") or "").lower(),
        ),
    )
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Taxonomy Cohorts",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Pair specs: {payload.get('pair_count', 0)}",
        f"- Total cohorts: {payload.get('cohort_count', 0)}",
        f"- Exported cohorts: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No cohorts match the selected filters.", ""])
        return "\n".join(lines)
    for item in rows:
        lines.extend(
            [
                f"## {item.get('label')} `{item.get('id')}`",
                "",
                f"- Pair: {item.get('pair')}",
                f"- Action: {item.get('action')} / {item.get('severity')}",
                f"- Papers: {item.get('count')}",
                f"- Fields: {item.get('primary_field')}={item.get('primary_value')} -> {item.get('secondary_field')}={item.get('secondary_value')}",
                f"- View: {item.get('href') or '-'}",
                f"- Slugs: {join_value(item.get('slugs')) or '-'}",
                f"- Samples: {join_value(sample_slugs(item)) or '-'}",
                f"- Recommendation: {item.get('recommendation') or '-'}",
                "",
            ]
        )
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COHORT_FIELDS)
    writer.writeheader()
    for item in rows:
        writer.writerow(
            {
                field: join_value(sample_slugs(item)) if field == "sample_slugs" else join_value(item.get(field))
                for field in COHORT_FIELDS
            }
        )
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "")
    action = str(item.get("action") or "")
    if severity == "high" or action == "split_candidate":
        return "P1"
    if severity == "medium" or action == "singleton":
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
            for label in ["cohort", str(item.get("action") or ""), str(item.get("severity") or ""), str(item.get("pair") or "")]
            if label
        )
        body_parts = [
            f"Recommendation: {item.get('recommendation') or '-'}",
            f"Primary: {item.get('primary_field')}={item.get('primary_value')}",
            f"Secondary: {item.get('secondary_field')}={item.get('secondary_value')}",
            f"Samples: {join_value(sample_slugs(item)) or '-'}",
            f"View: {item.get('href') or '-'}",
        ]
        writer.writerow(
            {
                "task_id": f"cohort-{index:03d}",
                "title": f"[cohort] {item.get('label')} ({item.get('count')} papers)",
                "status": args.task_status,
                "priority": priority_for(item),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "cohort_id": item.get("id"),
                "pair": item.get("pair"),
                "action": item.get("action"),
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
    print(f"Exported cohorts to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_cohorts(report_dir)
        rows = filter_cohorts(payload, args)
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
