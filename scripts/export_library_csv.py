#!/usr/bin/env python3
"""Export wiki metadata to a spreadsheet-friendly CSV table."""

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
    "title_zh",
    "title_en",
    "year",
    "authors",
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
    "last_reviewed",
    "next_review",
    "suggested_next_review",
    "review_state",
    "review_priority",
    "importance",
    "confidence",
    "reproducibility",
    "has_code",
    "quality_score",
    "missing_fields",
    "weak_fields",
    "md_path",
    "html_path",
    "arxiv_url",
    "code_url",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader wiki metadata as CSV.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing papers.json, review.json, and quality.json.",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="CSV output path. Defaults to stdout.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def join_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_rows(report_dir: Path) -> list[dict[str, str]]:
    papers = load_json(report_dir / "papers.json", {"papers": []}).get("papers", [])
    review_items = {
        item.get("slug"): item
        for item in load_json(report_dir / "review.json", {"items": []}).get("items", [])
    }
    quality_items = {
        item.get("slug"): item
        for item in load_json(report_dir / "quality.json", {"issues": []}).get("issues", [])
    }

    rows: list[dict[str, str]] = []
    for paper in papers:
        slug = paper.get("slug")
        review = review_items.get(slug, {})
        quality = quality_items.get(slug, {})
        merged: dict[str, Any] = {
            **paper,
            "suggested_next_review": review.get("suggested_next_review", ""),
            "review_state": review.get("state", ""),
            "review_priority": review.get("priority", ""),
            "quality_score": quality.get("score", ""),
            "missing_fields": quality.get("missing_fields", []),
            "weak_fields": quality.get("weak_fields", []),
        }
        rows.append({field: join_value(merged.get(field)) for field in FIELDS})
    return rows


def write_csv(rows: list[dict[str, str]], output: TextIO) -> None:
    writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    rows = build_rows(report_dir)

    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = ROOT / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            write_csv(rows, handle)
        print(f"Exported {len(rows)} papers to {output_path}")
    else:
        write_csv(rows, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
