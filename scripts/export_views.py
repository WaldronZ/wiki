#!/usr/bin/env python3
"""Export view directory entries as Markdown, CSV, or sidebar JSON."""

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
    "name",
    "source",
    "kind",
    "page",
    "target_page",
    "href",
    "count",
    "empty",
    "state",
    "slugs",
    "sample_titles",
    "note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader view directory entries.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing views.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "sidebar"],
        default="markdown",
        help="Output format. Use 'sidebar' for desktop/navigation JSON.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--source", action="append", help="Only include this source. Can be repeated.")
    parser.add_argument("--kind", action="append", help="Only include this kind. Can be repeated.")
    parser.add_argument("--page", action="append", help="Only include this view page. Can be repeated.")
    parser.add_argument("--view", action="append", help="Only include views whose id or name matches. Can be repeated.")
    parser.add_argument("--min-count", type=int, default=0, help="Only include views with at least this many papers.")
    parser.add_argument("--include-empty", action="store_true", help="Keep empty views instead of hiding them.")
    parser.add_argument("--top", type=int, default=0, help="Limit to the first N filtered views.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_views(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "views.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("views"), list):
        raise ValueError("views.json has invalid 'views' payload")
    return payload


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def sample_titles(view: dict[str, Any]) -> list[str]:
    titles = []
    for paper in view.get("sample_papers", []):
        if not isinstance(paper, dict):
            continue
        title = str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or "").strip()
        if title:
            titles.append(title)
    return titles


def filtered_views(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    sources = {str(value).strip() for value in (args.source or []) if str(value).strip()}
    kinds = {str(value).strip() for value in (args.kind or []) if str(value).strip()}
    pages = {str(value).strip() for value in (args.page or []) if str(value).strip()}
    selected = {str(value).strip().lower() for value in (args.view or []) if str(value).strip()}
    rows = []
    for raw in payload.get("views", []):
        if not isinstance(raw, dict):
            continue
        count = int(raw.get("count") or 0)
        if sources and str(raw.get("source") or "") not in sources:
            continue
        if kinds and str(raw.get("kind") or "") not in kinds:
            continue
        if pages and str(raw.get("page") or "") not in pages:
            continue
        if count < args.min_count:
            continue
        if not args.include_empty and raw.get("empty"):
            continue
        identity = {str(raw.get("id") or "").lower(), str(raw.get("name") or "").lower()}
        if selected and not selected.intersection(identity):
            continue
        row = dict(raw)
        row["sample_titles"] = sample_titles(raw)
        rows.append(row)
    rows.sort(
        key=lambda item: (
            str(item.get("source") or ""),
            str(item.get("kind") or ""),
            -int(item.get("count") or 0),
            str(item.get("name") or "").lower(),
        )
    )
    if args.top > 0:
        rows = rows[: args.top]
    return rows


def render_markdown(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    lines = [
        "# AutoPaperReader View Directory",
        "",
        f"- Papers: {payload.get('count', 0)}",
        f"- Views: {payload.get('view_count', 0)}",
        f"- Configured: {payload.get('configured_count', 0)}",
        f"- System: {payload.get('system_count', 0)}",
        f"- Generated: {payload.get('generated_count', 0)}",
        f"- Exported views: {len(rows)}",
        "",
    ]
    if not rows:
        lines.extend(["No views match the selected filters.", ""])
        return "\n".join(lines)
    current_group = ""
    for view in rows:
        group = f"{view.get('source')} / {view.get('kind')}"
        if group != current_group:
            current_group = group
            lines.extend([f"## {group}", ""])
        name = str(view.get("name") or view.get("id") or "")
        href = str(view.get("href") or "")
        label = f"[{name}]({href})" if href else name
        lines.append(f"- [ ] {label} ({view.get('count', 0)} papers)")
        lines.append(f"  - Page: {view.get('page')} -> {view.get('target_page')}")
        lines.append(f"  - State: {join_value(view.get('state')) or '-'}")
        if view.get("slugs"):
            lines.append(f"  - Slugs: {join_value(view.get('slugs'))}")
        if view.get("sample_titles"):
            lines.append(f"  - Samples: {join_value(view.get('sample_titles'))}")
        if view.get("note"):
            lines.append(f"  - Note: {view.get('note')}")
    lines.append("")
    return "\n".join(lines)


def render_csv(rows: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    for view in rows:
        writer.writerow({field: join_value(view.get(field)) for field in FIELDS})
    return buffer.getvalue()


def render_sidebar(payload: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    groups: dict[str, list[dict[str, Any]]] = {}
    for view in rows:
        group = f"{view.get('source')} / {view.get('kind')}"
        groups.setdefault(group, []).append(
            {
                "id": view.get("id"),
                "label": view.get("name"),
                "href": view.get("href"),
                "count": view.get("count"),
                "source": view.get("source"),
                "kind": view.get("kind"),
                "page": view.get("page"),
                "state": view.get("state") or {},
                "slugs": view.get("slugs") or [],
            }
        )
    payload_out = {
        "generated_from": "views.json",
        "paper_count": payload.get("count", 0),
        "view_count": len(rows),
        "groups": [
            {"label": label, "items": items}
            for label, items in sorted(groups.items(), key=lambda item: item[0])
        ],
    }
    return json.dumps(payload_out, ensure_ascii=False, indent=2) + "\n"


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
    print(f"Exported views to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_views(report_dir)
        rows = filtered_views(payload, args)
        if args.format == "csv":
            text = render_csv(rows)
        elif args.format == "sidebar":
            text = render_sidebar(payload, rows)
        else:
            text = render_markdown(payload, rows)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
