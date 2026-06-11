#!/usr/bin/env python3
"""Export taxonomy label registry items as Markdown, CSV, project tasks, or patch templates."""

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
    "label",
    "severity",
    "fields",
    "definition_status",
    "owner_name",
    "description",
    "total_count",
    "paper_count",
    "configured",
    "aliases",
    "signals",
    "query_href",
    "recommended_action",
    "slugs",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "severity",
    "taxonomy_label",
    "fields",
    "definition_status",
    "owner_name",
    "signals",
    "slugs",
    "href",
    "body",
]

PATCH_METADATA_FIELDS = [
    "domains",
    "tracks",
    "problems",
    "topics",
    "methods",
    "research_line",
    "line_role",
    "status",
    "reading_stage",
    "review_stage",
]

PATCH_AUDIT_FIELDS = [
    "source_value",
    "source_field",
    "severity",
    "signals",
    "recommendation",
    "href",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader taxonomy label registry.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing registry.json.",
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
    parser.add_argument(
        "--target-value",
        default="<target_value>",
        help="Replacement value used by --format patch. Edit this column in the CSV before applying if needed.",
    )
    parser.add_argument(
        "--severity",
        choices=["high", "medium", "low", "ok"],
        action="append",
        help="Only include registry labels with this severity. Can be repeated.",
    )
    parser.add_argument(
        "--signal",
        action="append",
        help="Only include labels carrying this signal, such as singleton, cross_field, or overloaded. Can be repeated.",
    )
    parser.add_argument(
        "--field",
        action="append",
        help="Only include labels used in this metadata field. Can be repeated.",
    )
    parser.add_argument(
        "--configured",
        choices=["yes", "no"],
        help="Only include labels that are configured in taxonomy.json-derived controls, or only labels observed from reports/aliases.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_registry(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "registry.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    labels = payload.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError("registry.json has invalid 'labels' payload")
    return payload


def load_papers(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "papers.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("papers.json has invalid 'papers' payload")
    return papers


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def filter_labels(labels: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    severities = set(args.severity or [])
    signals = {str(signal).strip() for signal in (args.signal or []) if str(signal).strip()}
    fields = {str(field).strip() for field in (args.field or []) if str(field).strip()}
    configured_filter = args.configured
    filtered = []
    for item in labels:
        item_signals = set(str(signal) for signal in item.get("signals", []))
        item_fields = set(str(field) for field in item.get("field_names", []))
        if severities and item.get("severity") not in severities:
            continue
        if signals and not signals.intersection(item_signals):
            continue
        if fields and not fields.intersection(item_fields):
            continue
        if configured_filter == "yes" and not item.get("configured"):
            continue
        if configured_filter == "no" and item.get("configured"):
            continue
        filtered.append(item)
    severity_rank = {"high": 0, "medium": 1, "low": 2, "ok": 3}
    return sorted(
        filtered,
        key=lambda item: (
            severity_rank.get(str(item.get("severity") or ""), 9),
            -int(item.get("total_count") or 0),
            str(item.get("label") or "").lower(),
        ),
    )


def render_markdown(payload: dict[str, Any], labels: list[dict[str, Any]]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "# Taxonomy Label Registry",
        "",
        f"- Registry labels: {payload.get('label_count', len(labels))}",
        f"- Exported labels: {len(labels)}",
        f"- High: {summary.get('high', 0)}",
        f"- Medium: {summary.get('medium', 0)}",
        f"- Cross-field: {summary.get('cross_field', 0)}",
        f"- Singleton: {summary.get('singleton', 0)}",
        "",
    ]
    if not labels:
        lines.extend(["No registry labels match the selected filters.", ""])
        return "\n".join(lines)

    current_group = ""
    for item in labels:
        group = str(item.get("severity") or "unknown")
        if group != current_group:
            current_group = group
            lines.extend([f"## {group}", ""])
        label = str(item.get("label") or "")
        href = str(item.get("query_href") or "")
        display = f"[{label}]({href})" if href else label
        fields = join_value(item.get("field_names"))
        signals = join_value(item.get("signals"))
        slugs = join_value(item.get("slugs"))
        description = str(item.get("description") or "")
        owner = str(item.get("owner_name") or "")
        lines.append(f"- [ ] {display} ({item.get('total_count', 0)} uses, {item.get('paper_count', 0)} papers)")
        lines.append(f"  - Fields: {fields or 'alias'}")
        if description:
            lines.append(f"  - Definition: {description}")
        if owner:
            lines.append(f"  - Owner: {owner}")
        if signals:
            lines.append(f"  - Signals: {signals}")
        lines.append(f"  - Recommendation: {item.get('recommended_action', '')}")
        if slugs:
            lines.append(f"  - Slugs: {slugs}")
    lines.append("")
    return "\n".join(lines)


def render_csv(labels: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in labels:
        row = {
            "label": join_value(item.get("label")),
            "severity": join_value(item.get("severity")),
            "fields": join_value(item.get("field_names")),
            "definition_status": join_value(item.get("definition_status")),
            "owner_name": join_value(item.get("owner_name")),
            "description": join_value(item.get("description")),
            "total_count": join_value(item.get("total_count")),
            "paper_count": join_value(item.get("paper_count")),
            "configured": "yes" if item.get("configured") else "no",
            "aliases": join_value(item.get("aliases")),
            "signals": join_value(item.get("signals")),
            "query_href": join_value(item.get("query_href")),
            "recommended_action": join_value(item.get("recommended_action")),
            "slugs": join_value(item.get("slugs")),
        }
        writer.writerow(row)
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "")
    return {"high": "P1", "medium": "P2", "low": "P3", "ok": "P4"}.get(severity, "P3")


def task_body(item: dict[str, Any]) -> str:
    parts = [
        str(item.get("recommended_action") or ""),
        f"Uses: {item.get('total_count', 0)}",
        f"Papers: {item.get('paper_count', 0)}",
    ]
    aliases = join_value(item.get("aliases"))
    if aliases:
        parts.append(f"Aliases: {aliases}")
    description = str(item.get("description") or "")
    if description:
        parts.append(f"Definition: {description}")
    signals = join_value(item.get("signals"))
    if signals:
        parts.append(f"Signals: {signals}")
    href = str(item.get("query_href") or "")
    if href:
        parts.append(f"View: {href}")
    return " | ".join(part for part in parts if part)


def render_project_csv(labels: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(labels, start=1):
        severity = str(item.get("severity") or "")
        field_names = join_value(item.get("field_names"))
        signals = join_value(item.get("signals"))
        label = str(item.get("label") or "")
        row = {
            "task_id": f"reg-{index:03d}",
            "title": f"Review taxonomy label: {label}",
            "status": args.task_status,
            "priority": priority_for(item),
            "assignee": args.assignee,
            "due_date": args.due_date,
            "labels": "; ".join(value for value in ["taxonomy_registry", severity, *item.get("signals", [])] if value),
            "severity": severity,
            "taxonomy_label": label,
            "fields": field_names,
            "definition_status": join_value(item.get("definition_status")),
            "owner_name": join_value(item.get("owner_name")),
            "signals": signals,
            "slugs": join_value(item.get("slugs")),
            "href": join_value(item.get("query_href")),
            "body": task_body(item),
        }
        writer.writerow(row)
    return buffer.getvalue()


def paper_values(paper: dict[str, Any], field: str) -> list[str]:
    value = paper.get(field)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text and text != "Unassigned" else []


def replacement_value(paper: dict[str, Any], field: str, source: str, target: str) -> str:
    values = paper_values(paper, field)
    if field in {"domains", "tracks", "problems", "topics", "methods"}:
        replaced: list[str] = []
        for value in values:
            next_value = target if value == source else value
            if next_value and next_value not in replaced:
                replaced.append(next_value)
        return "; ".join(replaced)
    return target


def render_patch_csv(labels: list[dict[str, Any]], papers: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    fieldnames = ["slug", *PATCH_METADATA_FIELDS, *PATCH_AUDIT_FIELDS]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    target = str(args.target_value or "<target_value>").strip() or "<target_value>"
    for item in labels:
        source = str(item.get("label") or "")
        for field in item.get("field_names", []):
            if field not in PATCH_METADATA_FIELDS:
                continue
            for paper in papers:
                if source not in paper_values(paper, field):
                    continue
                row = {name: "" for name in fieldnames}
                row.update(
                    {
                        "slug": str(paper.get("slug") or ""),
                        field: replacement_value(paper, field, source, target),
                        "source_value": source,
                        "source_field": field,
                        "severity": join_value(item.get("severity")),
                        "signals": join_value(item.get("signals")),
                        "recommendation": join_value(item.get("recommended_action")),
                        "href": join_value(item.get("query_href")),
                    }
                )
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
    print(f"Exported taxonomy registry to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_registry(report_dir)
        labels = filter_labels(payload.get("labels", []), args)
        if args.format == "csv":
            text = render_csv(labels)
        elif args.format == "project":
            text = render_project_csv(labels, args)
        elif args.format == "patch":
            text = render_patch_csv(labels, load_papers(report_dir), args)
        else:
            text = render_markdown(payload, labels)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
