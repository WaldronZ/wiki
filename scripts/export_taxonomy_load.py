#!/usr/bin/env python3
"""Export per-paper taxonomy load audit items as Markdown or CSV."""

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
    "slug",
    "title",
    "research_line",
    "structure_count",
    "topic_count",
    "method_count",
    "tag_count",
    "signals",
    "recommendation",
    "html_path",
]

PATCH_FIELDS = [
    "slug",
    "domains",
    "tracks",
    "problems",
    "topics",
    "methods",
    "research_line",
    "line_role",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader taxonomy load audit items.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing quality.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "csv", "patch"],
        default="markdown",
        help="Output format. Use 'patch' for a CSV template compatible with apply_library_metadata.py.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument(
        "--signal",
        choices=["sparse_structure", "sparse_tags", "dense_tags", "method_overload"],
        action="append",
        help="Only include items carrying this signal. Can be repeated.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_quality(report_dir: Path) -> dict[str, Any]:
    path = report_dir / "quality.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("taxonomy_load", [])
    if not isinstance(items, list):
        raise ValueError("quality.json has invalid 'taxonomy_load' payload")
    return payload


def load_papers(report_dir: Path) -> dict[str, dict[str, Any]]:
    path = report_dir / "papers.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("papers.json has invalid 'papers' payload")
    return {
        str(paper.get("slug") or ""): paper
        for paper in papers
        if isinstance(paper, dict) and str(paper.get("slug") or "").strip()
    }


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def filter_items(items: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    signals = set(args.signal or [])
    filtered = []
    for item in items:
        item_signals = set(str(signal) for signal in item.get("signals", []))
        if signals and not signals.intersection(item_signals):
            continue
        filtered.append(item)
    return sorted(
        filtered,
        key=lambda item: (
            "dense_tags" not in set(str(signal) for signal in item.get("signals", [])),
            "sparse_tags" not in set(str(signal) for signal in item.get("signals", [])),
            -int(item.get("tag_count") or 0),
            str(item.get("research_line") or ""),
            str(item.get("slug") or ""),
        ),
    )


def render_markdown(items: list[dict[str, Any]]) -> str:
    lines = ["# Taxonomy Load Audit", "", f"- Exported items: {len(items)}", ""]
    if not items:
        lines.extend(["No taxonomy load items match the selected filters.", ""])
        return "\n".join(lines)

    current_line = ""
    for item in items:
        research_line = str(item.get("research_line") or "Unassigned")
        if research_line != current_line:
            current_line = research_line
            lines.extend([f"## {research_line}", ""])
        title = str(item.get("title_zh") or item.get("title") or item.get("slug") or "")
        href = str(item.get("html_path") or "")
        label = f"[{title}]({href})" if href else title
        signals = join_value(item.get("signals"))
        counts = (
            f"structure {item.get('structure_count', 0)}, "
            f"topic {item.get('topic_count', 0)}, "
            f"method {item.get('method_count', 0)}"
        )
        lines.append(f"- [ ] `{item.get('slug')}` {label}")
        lines.append(f"  - Signals: {signals}")
        lines.append(f"  - Counts: {counts}")
        lines.append(f"  - Recommendation: {item.get('recommendation', '')}")
    lines.append("")
    return "\n".join(lines)


def render_csv(items: list[dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for item in items:
        title = item.get("title_zh") or item.get("title")
        row = {field: join_value(item.get(field)) for field in FIELDS}
        row["title"] = join_value(title)
        writer.writerow(row)
    return buffer.getvalue()


def render_patch_csv(items: list[dict[str, Any]], papers_by_slug: dict[str, dict[str, Any]]) -> str:
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=PATCH_FIELDS)
    writer.writeheader()
    for item in items:
        slug = str(item.get("slug") or "")
        paper = papers_by_slug.get(slug, {})
        row = {field: join_value(paper.get(field)) for field in PATCH_FIELDS}
        row["slug"] = slug
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
    print(f"Exported taxonomy load audit to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    try:
        payload = load_quality(report_dir)
        items = filter_items(payload.get("taxonomy_load", []), args)
        if args.format == "csv":
            text = render_csv(items)
        elif args.format == "patch":
            text = render_patch_csv(items, load_papers(report_dir))
        else:
            text = render_markdown(items)
        write_output(text, args.output, report_dir, sys.stdout)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
