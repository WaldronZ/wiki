#!/usr/bin/env python3
"""Export research-line taxonomy coverage as Markdown, CSV, project tasks, or metadata patches."""

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

FIELDS = [
    "line",
    "owner",
    "team",
    "cadence",
    "risk",
    "score",
    "papers",
    "missing_total",
    "field",
    "label",
    "coverage",
    "missing",
    "unique",
    "missing_slugs",
    "top_values",
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
    "owner",
    "team",
    "field",
    "risk",
    "score",
    "missing",
    "href",
    "missing_slugs",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader research-line coverage gaps.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing coverage.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project", "patch"],
        default="markdown",
        help="Output format. Use 'patch' for a CSV template compatible with apply_library_metadata.py.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument("--line", action="append", help="Only include this research line. Can be repeated.")
    parser.add_argument("--owner", action="append", help="Only include this owner. Can be repeated.")
    parser.add_argument("--field", action="append", help="Only include this metadata field. Can be repeated.")
    parser.add_argument(
        "--risk",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this research-line risk. Can be repeated.",
    )
    parser.add_argument("--min-missing", type=int, default=1, help="Only include field rows with at least this many missing papers.")
    parser.add_argument("--max-score", type=int, default=100, help="Only include lines at or below this coverage score.")
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


def load_coverage(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "coverage.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("coverage"), list):
        raise ValueError("coverage.json has invalid 'coverage' payload")
    if not isinstance(payload.get("fields"), list):
        raise ValueError("coverage.json has invalid 'fields' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def top_values(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    items = []
    for item in value:
        if isinstance(item, dict) and item.get("value"):
            items.append(f"{item.get('value')}:{item.get('count', 0)}")
    return "; ".join(items)


def flat_rows(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    lines = {str(value).strip().lower() for value in (args.line or []) if str(value).strip()}
    owners = {str(value).strip().lower() for value in (args.owner or []) if str(value).strip()}
    fields = {str(value).strip() for value in (args.field or []) if str(value).strip()}
    risks = set(args.risk or [])
    rows: list[dict[str, Any]] = []
    for line in payload.get("coverage", []):
        if not isinstance(line, dict):
            continue
        if lines and str(line.get("line") or "").lower() not in lines:
            continue
        if owners and str(line.get("owner") or "").lower() not in owners:
            continue
        if risks and line.get("risk") not in risks:
            continue
        if int(line.get("score") or 0) > args.max_score:
            continue
        for field in line.get("fields", []):
            if not isinstance(field, dict):
                continue
            if fields and str(field.get("field") or "") not in fields:
                continue
            if int(field.get("missing") or 0) < args.min_missing:
                continue
            rows.append(
                {
                    "line": line.get("line"),
                    "owner": line.get("owner"),
                    "team": line.get("team"),
                    "cadence": line.get("cadence"),
                    "risk": line.get("risk"),
                    "score": line.get("score"),
                    "papers": line.get("count"),
                    "missing_total": line.get("missing_total"),
                    "field": field.get("field"),
                    "label": field.get("label"),
                    "coverage": field.get("coverage"),
                    "missing": field.get("missing"),
                    "unique": field.get("unique"),
                    "missing_slugs": field.get("missing_slugs") or [],
                    "top_values": field.get("top_values") or [],
                    "href": line.get("href"),
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("risk")), 9),
            int(row.get("score") or 0),
            -int(row.get("missing") or 0),
            str(row.get("line") or "").lower(),
            str(row.get("field") or ""),
        ),
    )


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines = [
        "# AutoPaperReader Coverage Gaps",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Research lines: {payload.get('line_count', 0)}",
        f"- Average score: {payload.get('avg_score', 0)}",
        f"- Exported gaps: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No coverage gaps match the selected filters.", ""])
        return "\n".join(lines)
    for row in rows:
        lines.extend(
            [
                f"- [ ] {row['line']} / {row['label']}: missing {row['missing']} ({row['coverage']}%)",
                f"  - Owner: {row.get('owner') or 'unassigned'}",
                f"  - Risk: {row.get('risk')} / score {row.get('score')}",
                f"  - Missing slugs: {join_value(row.get('missing_slugs')) or '-'}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: top_values(row.get(field)) if field == "top_values" else join_value(row.get(field)) for field in FIELDS})
    return buffer.getvalue()


def priority_for(row: dict[str, Any]) -> str:
    risk = str(row.get("risk") or "")
    missing = int(row.get("missing") or 0)
    score = int(row.get("score") or 0)
    if risk == "high" or missing >= 5 or score < 50:
        return "P1"
    if risk == "medium" or missing >= 2 or score < 75:
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, row in enumerate(rows, start=1):
        labels = "; ".join(label for label in ["coverage", str(row.get("field") or ""), str(row.get("risk") or "")] if label)
        body = " | ".join(
            [
                f"Line: {row.get('line')}",
                f"Owner: {row.get('owner') or 'unassigned'}",
                f"Missing slugs: {join_value(row.get('missing_slugs')) or '-'}",
                f"Top values: {top_values(row.get('top_values')) or '-'}",
                f"View: {row.get('href') or '-'}",
            ]
        )
        writer.writerow(
            {
                "task_id": f"coverage-{index:03d}",
                "title": f"[{row.get('field')}] {row.get('line')}: fill {row.get('missing')} missing values",
                "status": args.task_status,
                "priority": priority_for(row),
                "assignee": args.assignee or row.get("owner") or "",
                "due_date": args.due_date,
                "labels": labels,
                "line": row.get("line"),
                "owner": row.get("owner"),
                "team": row.get("team"),
                "field": row.get("field"),
                "risk": row.get("risk"),
                "score": row.get("score"),
                "missing": row.get("missing"),
                "href": row.get("href"),
                "missing_slugs": join_value(row.get("missing_slugs")),
                "body": body,
            }
        )
    return buffer.getvalue()


def render_patch_csv(payload: dict[str, Any], rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    if not args.field or len(args.field) != 1 or args.set_value is None:
        raise ValueError("--format patch requires exactly one --field and --set-value")
    from io import StringIO

    field_name = args.field[0]
    known_fields = {str(field.get("field") or ""): field for field in payload.get("fields", []) if isinstance(field, dict)}
    if field_name not in known_fields:
        raise ValueError(f"unknown coverage field for patch: {field_name}")
    slugs: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.get("field") != field_name:
            continue
        for slug in row.get("missing_slugs", []):
            text = str(slug).strip()
            if text and text not in seen:
                seen.add(text)
                slugs.append(text)
    buffer = StringIO()
    fieldnames = ["slug", field_name, "_list_mode"] if field_name in LIST_FIELDS else ["slug", field_name]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for slug in slugs:
        row = {"slug": slug, field_name: args.set_value}
        if field_name in LIST_FIELDS:
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
    print(f"Exported coverage to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_coverage(report_dir)
        rows = flat_rows(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, args)
        elif args.format == "patch":
            text = render_patch_csv(payload, rows, args)
        else:
            text = render_markdown(payload, rows, args)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
