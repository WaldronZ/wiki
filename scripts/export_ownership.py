#!/usr/bin/env python3
"""Export ownership workload as Markdown, CSV, or project tasks."""

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
    "scope",
    "owner",
    "team",
    "line",
    "risk",
    "risk_points",
    "paper_count",
    "line_count",
    "cadence",
    "queues",
    "href",
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
    "owner",
    "team",
    "scope",
    "line",
    "queue",
    "queue_count",
    "risk",
    "risk_points",
    "href",
    "sample_slugs",
    "body",
]

QUEUE_LABELS = {
    "missing_taxonomy": "补齐分类元数据",
    "needs_review_plan": "补复习计划",
    "due_review": "处理到期复习",
    "freshness_due": "复查报告时效",
    "stale": "更新过期报告",
    "no_code_observation": "补代码实现观察",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader ownership workload.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing ownership.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project"],
        default="markdown",
        help="Output format. Use 'project' for task trackers.",
    )
    parser.add_argument(
        "--scope",
        choices=["owner", "line"],
        default="owner",
        help="Export owner aggregates or research-line rows.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument(
        "--risk",
        choices=["high", "medium", "low"],
        action="append",
        help="Only include this workload risk. Can be repeated.",
    )
    parser.add_argument("--owner", action="append", help="Only include this owner. Can be repeated.")
    parser.add_argument("--team", action="append", help="Only include this team. Can be repeated.")
    parser.add_argument(
        "--queue",
        action="append",
        help="Only include this queue key in project tasks and row filtering. Can be repeated.",
    )
    parser.add_argument("--min-risk-points", type=int, default=0, help="Only include rows with at least this risk score.")
    parser.add_argument(
        "--only-open-queues",
        action="store_true",
        help="Only include rows with at least one non-zero queue after --queue filtering.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_ownership(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "ownership.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("owners"), list):
        raise ValueError("ownership.json has invalid 'owners' payload")
    if not isinstance(payload.get("lines"), list):
        raise ValueError("ownership.json has invalid 'lines' payload")
    return payload


def slugify(value: str) -> str:
    text = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in text.split("-") if part) or "unassigned"


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}={value[key]}" for key in sorted(value))
    return str(value)


def queue_items(queues: Any, selected: set[str] | None = None) -> list[tuple[str, int]]:
    if not isinstance(queues, dict):
        return []
    items = []
    for key, value in sorted(queues.items()):
        if selected and key not in selected:
            continue
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        items.append((str(key), count))
    return items


def open_queue_items(row: dict[str, Any], selected: set[str] | None = None) -> list[tuple[str, int]]:
    return [(key, count) for key, count in queue_items(row.get("queues"), selected) if count > 0]


def normalized_rows(payload: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if scope == "owner":
        for item in payload.get("owners", []):
            if not isinstance(item, dict):
                continue
            owner = str(item.get("owner") or "unassigned")
            rows.append(
                {
                    "id": f"owner-{slugify(owner)}",
                    "scope": "owner",
                    "owner": owner,
                    "team": str(item.get("team") or ""),
                    "line": "",
                    "risk": str(item.get("risk") or "low"),
                    "risk_points": int(item.get("risk_points") or 0),
                    "paper_count": int(item.get("paper_count") or 0),
                    "line_count": int(item.get("line_count") or 0),
                    "cadence": "",
                    "queues": item.get("queues") or {},
                    "href": "ownership.html",
                    "sample_slugs": [
                        slug
                        for line in item.get("lines", [])
                        if isinstance(line, dict)
                        for slug in line.get("sample_slugs", [])
                    ],
                    "lines": [line.get("line") for line in item.get("lines", []) if isinstance(line, dict)],
                }
            )
    else:
        for item in payload.get("lines", []):
            if not isinstance(item, dict):
                continue
            line = str(item.get("line") or "Unassigned")
            rows.append(
                {
                    "id": f"line-{slugify(line)}",
                    "scope": "line",
                    "owner": str(item.get("owner") or "unassigned"),
                    "team": str(item.get("team") or ""),
                    "line": line,
                    "risk": str(item.get("risk") or "low"),
                    "risk_points": int(item.get("risk_points") or 0),
                    "paper_count": int(item.get("count") or 0),
                    "line_count": 1,
                    "cadence": str(item.get("cadence") or ""),
                    "queues": item.get("queues") or {},
                    "href": str(item.get("href") or "library.html"),
                    "sample_slugs": item.get("sample_slugs") or [],
                    "lines": [line],
                }
            )
    return sorted(rows, key=lambda row: (-int(row["risk_points"]), str(row["owner"]).lower(), str(row["line"]).lower()))


def filter_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    risks = set(args.risk or [])
    owners = {str(value).strip().lower() for value in (args.owner or []) if str(value).strip()}
    teams = {str(value).strip().lower() for value in (args.team or []) if str(value).strip()}
    selected_queues = {str(value).strip() for value in (args.queue or []) if str(value).strip()}
    filtered = []
    for row in rows:
        if risks and row["risk"] not in risks:
            continue
        if owners and str(row["owner"]).lower() not in owners:
            continue
        if teams and str(row["team"]).lower() not in teams:
            continue
        if int(row["risk_points"]) < args.min_risk_points:
            continue
        open_items = open_queue_items(row, selected_queues or None)
        if (args.only_open_queues or selected_queues) and not open_items:
            continue
        filtered.append(row)
    return filtered


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines = [
        "# AutoPaperReader Ownership Workload",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Owners: {payload.get('owner_count', 0)}",
        f"- Scope: {args.scope}",
        f"- Exported rows: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No ownership rows match the selected filters.", ""])
        return "\n".join(lines)

    selected_queues = {str(value).strip() for value in (args.queue or []) if str(value).strip()} or None
    for row in rows:
        title = row["owner"] if row["scope"] == "owner" else f"{row['line']} ({row['owner']})"
        lines.extend(
            [
                f"## {title} `{row['id']}`",
                "",
                f"- Team: {row['team'] or '-'}",
                f"- Risk: {row['risk']} / points {row['risk_points']}",
                f"- Papers: {row['paper_count']}",
                f"- Lines: {join_value(row.get('lines')) or '-'}",
                f"- Sample slugs: {join_value(row.get('sample_slugs')) or '-'}",
                "",
                "### Queues",
            ]
        )
        queues = queue_items(row.get("queues"), selected_queues)
        if not queues:
            lines.append("- [ ] maintain: no matching queues")
        for key, count in queues:
            label = QUEUE_LABELS.get(key, key)
            marker = " " if count else "x"
            lines.append(f"- [{marker}] {label}: {count}")
        lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: join_value(row.get(field)) for field in FIELDS})
    return buffer.getvalue()


def priority_for(row: dict[str, Any], queue_count: int) -> str:
    risk = str(row.get("risk") or "")
    points = int(row.get("risk_points") or 0)
    if risk == "high" or points >= 10 or queue_count >= 5:
        return "P1"
    if risk == "medium" or points >= 4 or queue_count >= 2:
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    selected_queues = {str(value).strip() for value in (args.queue or []) if str(value).strip()} or None
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    task_index = 1
    for row in rows:
        queues = open_queue_items(row, selected_queues)
        if not queues and not args.only_open_queues:
            queues = [("maintain", 0)]
        for queue_key, count in queues:
            label = QUEUE_LABELS.get(queue_key, queue_key)
            title_target = row["owner"] if row["scope"] == "owner" else row["line"]
            labels = "; ".join(label for label in ["ownership", row["scope"], row["risk"], queue_key] if label)
            body_parts = [
                f"Owner: {row['owner']}",
                f"Team: {row['team'] or '-'}",
                f"Lines: {join_value(row.get('lines')) or '-'}",
                f"Papers: {row['paper_count']}",
                f"Sample slugs: {join_value(row.get('sample_slugs')) or '-'}",
                f"View: {row['href']}",
            ]
            writer.writerow(
                {
                    "task_id": f"owner-{task_index:03d}",
                    "title": f"[{queue_key}] {title_target}: {label}",
                    "status": args.task_status,
                    "priority": priority_for(row, count),
                    "assignee": args.assignee or (row["owner"] if row["owner"] != "unassigned" else ""),
                    "due_date": args.due_date,
                    "labels": labels,
                    "owner": row["owner"],
                    "team": row["team"],
                    "scope": row["scope"],
                    "line": row["line"],
                    "queue": queue_key,
                    "queue_count": count,
                    "risk": row["risk"],
                    "risk_points": row["risk_points"],
                    "href": row["href"],
                    "sample_slugs": join_value(row.get("sample_slugs")),
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
    print(f"Exported ownership workload to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_ownership(report_dir)
        rows = filter_rows(normalized_rows(payload, args.scope), args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, args)
        else:
            text = render_markdown(payload, rows, args)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
