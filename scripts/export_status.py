#!/usr/bin/env python3
"""Export dynamic status selections as checklists, CSVs, workflow configs, or metadata patches."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

STATUS_FIELDS = [
    "slug",
    "title",
    "title_zh",
    "research_line",
    "line_role",
    "status",
    "reading_stage",
    "review_stage",
    "importance",
    "has_code",
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
    "workflow",
    "source_status",
    "source_reading_stage",
    "source_review_stage",
    "href",
    "body",
]

PATCH_META_FIELDS = ["source_field", "source_value", "workflow", "display_title", "href"]
PATCHABLE_FIELDS = ("status", "reading_stage", "review_stage")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader dynamic status selections.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing status.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project", "patch", "workflow-config"],
        default="markdown",
        help="Output format. Use patch to generate apply_library_metadata.py input.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--workflow", help="Status workflow name. Defaults to active_status_workflow.")
    parser.add_argument("--all-workflows", action="store_true", help="Include all workflows in --format workflow-config.")
    parser.add_argument("--status", action="append", help="Only include papers with this status. Can be repeated.")
    parser.add_argument("--reading-stage", action="append", help="Only include papers with this reading_stage. Can be repeated.")
    parser.add_argument("--review-stage", action="append", help="Only include papers with this review_stage. Can be repeated.")
    parser.add_argument("--line", action="append", help="Only include this research line. Can be repeated.")
    parser.add_argument("--slug", action="append", help="Only include this paper slug. Can be repeated.")
    parser.add_argument("--min-importance", type=int, default=0, help="Only include papers with at least this importance.")
    parser.add_argument("--has-code", choices=["yes", "no"], help="Only include papers by code availability.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered papers after sorting.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    parser.add_argument(
        "--field",
        choices=PATCHABLE_FIELDS,
        help="Metadata field to set when --format patch is used.",
    )
    parser.add_argument("--set-value", help="Metadata value to write when --format patch is used.")
    parser.add_argument(
        "--allow-unconfigured",
        action="store_true",
        help="Allow --set-value outside the selected workflow candidates.",
    )
    parser.add_argument(
        "--include-unchanged",
        action="store_true",
        help="Keep patch rows even when the selected paper already has --set-value.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_status(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "status.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("papers"), list):
        raise ValueError("status.json has invalid 'papers' payload")
    if not isinstance(payload.get("workflows"), list):
        raise ValueError("status.json has invalid 'workflows' payload")
    return payload


def workflow_lookup(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(workflow.get("name") or ""): workflow
        for workflow in payload.get("workflows", [])
        if isinstance(workflow, dict) and workflow.get("name")
    }


def selected_workflow(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    workflows = workflow_lookup(payload)
    name = args.workflow or payload.get("active_status_workflow") or next(iter(workflows), "")
    if name not in workflows:
        raise ValueError(f"workflow {name!r} is not listed in status.json")
    return workflows[name]


def value_set(values: list[str] | None) -> set[str]:
    return {str(value).strip() for value in (values or []) if str(value).strip()}


def item_value(item: dict[str, Any], field: str) -> str:
    return str(item.get(field) or "").strip()


def filter_rows(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    statuses = value_set(args.status)
    reading_stages = value_set(args.reading_stage)
    review_stages = value_set(args.review_stage)
    lines = value_set(args.line)
    slugs = value_set(args.slug)
    rows = []
    for paper in payload.get("papers", []):
        if not isinstance(paper, dict):
            continue
        if statuses and item_value(paper, "status") not in statuses:
            continue
        if reading_stages and item_value(paper, "reading_stage") not in reading_stages:
            continue
        if review_stages and item_value(paper, "review_stage") not in review_stages:
            continue
        if lines and item_value(paper, "research_line") not in lines:
            continue
        if slugs and item_value(paper, "slug") not in slugs:
            continue
        if int(paper.get("importance") or 0) < args.min_importance:
            continue
        if args.has_code == "yes" and not paper.get("has_code"):
            continue
        if args.has_code == "no" and paper.get("has_code"):
            continue
        rows.append(paper)
    rows = sorted(
        rows,
        key=lambda paper: (
            item_value(paper, "status"),
            item_value(paper, "reading_stage"),
            item_value(paper, "review_stage"),
            -int(paper.get("importance") or 0),
            item_value(paper, "research_line"),
            item_value(paper, "title_zh") or item_value(paper, "title") or item_value(paper, "slug"),
        ),
    )
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def render_markdown(payload: dict[str, Any], workflow: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader Status Selection",
        "",
        f"- Workflow: {workflow.get('name') or payload.get('active_status_workflow') or '-'}",
        f"- Papers: {payload.get('count', len(rows))}",
        f"- Exported papers: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No papers match the selected status filters.", ""])
        return "\n".join(lines)
    current = ""
    for paper in rows:
        group = f"{paper.get('status') or 'empty'} / {paper.get('reading_stage') or 'empty'} / {paper.get('review_stage') or 'empty'}"
        if group != current:
            current = group
            lines.extend([f"## {group}", ""])
        title = item_value(paper, "title_zh") or item_value(paper, "title") or item_value(paper, "slug")
        href = item_value(paper, "href")
        label = f"[{title}]({href})" if href else title
        lines.append(f"- [ ] {label} `{paper.get('slug')}`")
        lines.append(f"  - Line: {paper.get('research_line') or 'Unassigned'}")
        lines.append(f"  - Importance: {paper.get('importance') or '-'}")
    lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=STATUS_FIELDS)
    writer.writeheader()
    for paper in rows:
        writer.writerow({field: csv_cell(paper.get(field)) for field in STATUS_FIELDS})
    return buffer.getvalue()


def project_priority(paper: dict[str, Any]) -> str:
    if item_value(paper, "review_stage") == "due" or item_value(paper, "status") in {"reading", "triaged"}:
        return "P1"
    if int(paper.get("importance") or 0) >= 4:
        return "P2"
    return "P3"


def render_project_csv(rows: list[dict[str, Any]], workflow: dict[str, Any], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    workflow_name = item_value(workflow, "name")
    for index, paper in enumerate(rows, start=1):
        labels = "; ".join(
            label
            for label in ["status", workflow_name, item_value(paper, "status"), item_value(paper, "reading_stage"), item_value(paper, "review_stage")]
            if label
        )
        body = " | ".join(
            [
                f"Status: {paper.get('status') or '-'}",
                f"Reading: {paper.get('reading_stage') or '-'}",
                f"Review: {paper.get('review_stage') or '-'}",
                f"Line: {paper.get('research_line') or 'Unassigned'}",
                f"View: {paper.get('href') or '-'}",
            ]
        )
        writer.writerow(
            {
                "task_id": f"status-{index:03d}",
                "title": f"[status] {paper.get('title_zh') or paper.get('title') or paper.get('slug')}",
                "status": args.task_status,
                "priority": project_priority(paper),
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": labels,
                "slug": paper.get("slug"),
                "workflow": workflow_name,
                "source_status": paper.get("status") or "",
                "source_reading_stage": paper.get("reading_stage") or "",
                "source_review_stage": paper.get("review_stage") or "",
                "href": paper.get("href") or "",
                "body": body,
            }
        )
    return buffer.getvalue()


def workflow_values(workflow: dict[str, Any], field: str) -> list[str]:
    key = {
        "status": "status_values",
        "reading_stage": "reading_stage_values",
        "review_stage": "review_stage_values",
    }[field]
    return [str(value) for value in workflow.get(key, []) if str(value).strip()]


def validate_patch_args(workflow: dict[str, Any], args: argparse.Namespace) -> None:
    if args.format != "patch":
        return
    if not args.field or args.set_value is None:
        raise ValueError("--format patch requires --field and --set-value")
    allowed = workflow_values(workflow, args.field)
    if allowed and args.set_value not in allowed and not args.allow_unconfigured:
        joined = ", ".join(allowed)
        raise ValueError(
            f"{args.field}={args.set_value!r} is not configured in workflow {workflow.get('name')!r}; "
            f"use one of: {joined}; or pass --allow-unconfigured"
        )


def render_patch_csv(rows: list[dict[str, Any]], workflow: dict[str, Any], args: argparse.Namespace) -> str:
    from io import StringIO

    validate_patch_args(workflow, args)
    assert args.field is not None
    assert args.set_value is not None
    fieldnames = ["slug", args.field, *PATCH_META_FIELDS]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for paper in rows:
        before = item_value(paper, args.field)
        if before == args.set_value and not args.include_unchanged:
            continue
        writer.writerow(
            {
                "slug": paper.get("slug"),
                args.field: args.set_value,
                "source_field": args.field,
                "source_value": before,
                "workflow": workflow.get("name") or "",
                "display_title": paper.get("title_zh") or paper.get("title") or paper.get("slug"),
                "href": paper.get("href") or "",
            }
        )
    return buffer.getvalue()


def workflow_config(payload: dict[str, Any], workflow: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    workflows = workflow_lookup(payload)
    if args.all_workflows:
        selected = workflows
        active = str(payload.get("active_status_workflow") or workflow.get("name") or "")
    else:
        name = str(workflow.get("name") or payload.get("active_status_workflow") or "default")
        selected = {name: workflow}
        active = name
    config: dict[str, Any] = {"active_status_workflow": active, "status_workflows": {}}
    for name, item in selected.items():
        config["status_workflows"][name] = {
            "status_values": item.get("status_values") or [],
            "reading_stage_values": item.get("reading_stage_values") or [],
            "review_stage_values": item.get("review_stage_values") or [],
        }
    return config


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
    print(f"Exported status selection to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_status(report_dir)
        workflow = selected_workflow(payload, args)
        rows = filter_rows(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "project":
            text = render_project_csv(rows, workflow, args)
        elif args.format == "patch":
            text = render_patch_csv(rows, workflow, args)
        elif args.format == "workflow-config":
            text = json.dumps(workflow_config(payload, workflow, args), ensure_ascii=False, indent=2) + "\n"
        else:
            text = render_markdown(payload, workflow, rows)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
