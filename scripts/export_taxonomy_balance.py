#!/usr/bin/env python3
"""Export taxonomy balance metrics as Markdown, CSV, or project tasks."""

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
    "field",
    "label",
    "english",
    "balance_score",
    "used_count",
    "configured_count",
    "unused_count",
    "singleton_count",
    "overloaded_count",
    "max_value",
    "max_count",
    "max_share",
    "effective_count",
    "recommendation",
]

PROJECT_FIELDS = [
    "task_id",
    "title",
    "status",
    "priority",
    "assignee",
    "due_date",
    "labels",
    "field",
    "balance_score",
    "body",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader taxonomy balance metrics.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing stats.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "project"],
        default="markdown",
        help="Output format. Use 'project' for a task CSV suitable for project trackers.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--field", action="append", default=[], help="Only include this taxonomy field. May be repeated.")
    parser.add_argument("--max-score", type=int, default=100, help="Only include fields with balance_score <= this value.")
    parser.add_argument("--assignee", default="", help="Default assignee for --format project rows.")
    parser.add_argument("--due-date", default="", help="Default due date for --format project rows.")
    parser.add_argument("--task-status", default="todo", help="Default task status for --format project rows.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_balance(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "stats.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("taxonomy_balance", [])
    if not isinstance(items, list):
        raise ValueError("stats.json has invalid 'taxonomy_balance' payload")
    return [item for item in items if isinstance(item, dict)]


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def recommendation(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("field") or "taxonomy")
    max_value = str(item.get("max_value") or "")
    used_count = int(item.get("used_count") or 0)
    unused_count = int(item.get("unused_count") or 0)
    singleton_count = int(item.get("singleton_count") or 0)
    overloaded_count = int(item.get("overloaded_count") or 0)
    if used_count == 0:
        return f"{label} 当前没有被任何论文使用；确认是否应开始标注，或从当前 taxonomy/workflow 中移除。"
    if overloaded_count:
        return f"{label} 被少数值过度占用；优先拆分 `{max_value}` 或补充更细粒度的子类。"
    if used_count >= 4 and singleton_count / used_count >= 0.5:
        return f"{label} 长尾较多；检查是否存在同义词、大小写差异或过细标签。"
    if unused_count:
        return f"{label} 有未使用配置值；确认是预留流程状态，还是应该清理。"
    return f"{label} 分布相对稳定；继续观察随新增论文产生的变化。"


def enrich(item: dict[str, Any]) -> dict[str, Any]:
    row = item.copy()
    row["recommendation"] = recommendation(item)
    return row


def filter_items(items: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    fields = set(args.field or [])
    filtered = []
    for item in items:
        field = str(item.get("field") or "")
        score = int(item.get("balance_score") or 0)
        if fields and field not in fields:
            continue
        if score > args.max_score:
            continue
        filtered.append(enrich(item))
    return sorted(
        filtered,
        key=lambda item: (
            int(item.get("balance_score") or 0),
            -int(item.get("overloaded_count") or 0),
            -int(item.get("singleton_count") or 0),
            str(item.get("label") or item.get("field") or ""),
        ),
    )


def render_markdown(items: list[dict[str, Any]]) -> str:
    lines = ["# Taxonomy Balance Review", "", f"- Exported fields: {len(items)}", ""]
    if not items:
        lines.extend(["No taxonomy balance fields match the selected filters.", ""])
        return "\n".join(lines)

    for item in items:
        label = str(item.get("label") or item.get("field") or "")
        field = str(item.get("field") or "")
        lines.append(f"- [ ] `{field}` {label} - score {item.get('balance_score', 0)}")
        lines.append(
            "  - Counts: "
            f"used {item.get('used_count', 0)} / configured {item.get('configured_count', 0)}, "
            f"long-tail {item.get('singleton_count', 0)}, overloaded {item.get('overloaded_count', 0)}"
        )
        max_value = str(item.get("max_value") or "")
        if max_value:
            lines.append(f"  - Largest value: {max_value} ({round(float(item.get('max_share') or 0) * 100)}%)")
        lines.append(f"  - Recommendation: {item.get('recommendation', '')}")
    lines.append("")
    return "\n".join(lines)


def render_csv(items: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        writer.writerow({field: join_value(item.get(field)) for field in FIELDS})
    return buffer.getvalue()


def priority_for(item: dict[str, Any]) -> str:
    score = int(item.get("balance_score") or 0)
    if score <= 25 or int(item.get("overloaded_count") or 0):
        return "P1"
    if score <= 50 or int(item.get("singleton_count") or 0):
        return "P2"
    return "P3"


def render_project_csv(items: list[dict[str, Any]], args: argparse.Namespace) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PROJECT_FIELDS)
    writer.writeheader()
    for index, item in enumerate(items, start=1):
        label = str(item.get("label") or item.get("field") or "")
        field = str(item.get("field") or "")
        priority = priority_for(item)
        body = (
            f"{item.get('recommendation', '')} | "
            f"Used/configured: {item.get('used_count', 0)}/{item.get('configured_count', 0)} | "
            f"Long-tail: {item.get('singleton_count', 0)} | "
            f"Overloaded: {item.get('overloaded_count', 0)} | "
            f"Max: {item.get('max_value', '')} ({round(float(item.get('max_share') or 0) * 100)}%)"
        )
        writer.writerow(
            {
                "task_id": f"bal-{index:03d}",
                "title": f"Review taxonomy balance: {label}",
                "status": args.task_status,
                "priority": priority,
                "assignee": args.assignee,
                "due_date": args.due_date,
                "labels": f"taxonomy_balance; {field}; {priority}",
                "field": field,
                "balance_score": join_value(item.get("balance_score")),
                "body": body,
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
    print(f"Exported taxonomy balance review to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        items = filter_items(load_balance(report_dir), args)
        if args.format == "csv":
            text = render_csv(items)
        elif args.format == "project":
            text = render_project_csv(items, args)
        else:
            text = render_markdown(items)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
