#!/usr/bin/env python3
"""Export filtered wiki papers as Markdown, BibTeX, or plain links."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader papers as a reading list.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing papers.json.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["markdown", "bibtex", "links"],
        default="markdown",
        help="Output format.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--line", help="Filter by research_line.")
    parser.add_argument("--status", help="Filter by status.")
    parser.add_argument("--track", help="Filter by track.")
    parser.add_argument("--topic", help="Filter by topic.")
    parser.add_argument("--method", help="Filter by method.")
    parser.add_argument("--min-importance", type=int, default=0, help="Minimum importance score.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_papers(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "papers.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    data = json.loads(path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("papers.json has invalid 'papers' payload")
    return papers


def has_value(values: Any, expected: str | None) -> bool:
    if not expected:
        return True
    return expected in [str(value) for value in (values or [])]


def filter_papers(papers: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    items = []
    for paper in papers:
        if args.line and paper.get("research_line") != args.line:
            continue
        if args.status and paper.get("status") != args.status:
            continue
        if not has_value(paper.get("tracks"), args.track):
            continue
        if not has_value(paper.get("topics"), args.topic):
            continue
        if not has_value(paper.get("methods"), args.method):
            continue
        if args.min_importance and int(paper.get("importance") or 0) < args.min_importance:
            continue
        items.append(paper)
    return sorted(
        items,
        key=lambda paper: (
            -int(paper.get("importance") or 0),
            -int(paper.get("year") or 0),
            str(paper.get("title_en") or paper.get("title") or paper.get("slug") or ""),
        ),
    )


def paper_url(paper: dict[str, Any]) -> str:
    return str(paper.get("arxiv_url") or paper.get("html_path") or paper.get("md_path") or "")


def render_markdown(papers: list[dict[str, Any]]) -> str:
    lines = ["# Reading List", ""]
    for paper in papers:
        title = str(paper.get("title_en") or paper.get("title") or paper.get("slug"))
        title_zh = str(paper.get("title_zh") or "")
        url = paper_url(paper)
        label = f"[{title}]({url})" if url else title
        meta = " · ".join(
            str(value)
            for value in [
                paper.get("year"),
                paper.get("research_line"),
                paper.get("status"),
                f"I{paper.get('importance')}" if paper.get("importance") else "",
            ]
            if value
        )
        lines.append(f"- {label}")
        if title_zh and title_zh != title:
            lines.append(f"  - 中文：{title_zh}")
        if meta:
            lines.append(f"  - 元数据：{meta}")
        if paper.get("code_url"):
            lines.append(f"  - 代码：{paper['code_url']}")
    lines.append("")
    return "\n".join(lines)


def bibtex_key(paper: dict[str, Any]) -> str:
    authors = paper.get("authors") or []
    first_author = str(authors[0] if authors else "paper").split()[-1].lower()
    first_author = re.sub(r"[^a-z0-9]+", "", first_author) or "paper"
    year = str(paper.get("year") or "nd")
    short = re.sub(r"[^a-z0-9]+", "", str(paper.get("slug") or paper.get("title") or "paper").lower())
    return f"{first_author}{year}{short[:24]}"


def bibtex_escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def render_bibtex(papers: list[dict[str, Any]]) -> str:
    entries = []
    for paper in papers:
        fields = [
            ("title", paper.get("title_en") or paper.get("title")),
            ("author", " and ".join(str(author) for author in paper.get("authors", []))),
            ("year", paper.get("year")),
            ("url", paper_url(paper)),
            ("note", paper.get("arxiv_id")),
        ]
        body = "\n".join(
            f"  {name} = {{{bibtex_escape(value)}}},"
            for name, value in fields
            if value
        )
        entries.append(f"@misc{{{bibtex_key(paper)},\n{body}\n}}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def render_links(papers: list[dict[str, Any]]) -> str:
    return "".join(f"{paper_url(paper)}\n" for paper in papers if paper_url(paper))


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
    print(f"Exported reading list to {path}")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    papers = filter_papers(load_papers(report_dir), args)
    if args.format == "markdown":
        text = render_markdown(papers)
    elif args.format == "bibtex":
        text = render_bibtex(papers)
    else:
        text = render_links(papers)
    try:
        write_output(text, args.output, report_dir, sys.stdout)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
