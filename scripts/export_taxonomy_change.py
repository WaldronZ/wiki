#!/usr/bin/env python3
"""Export a metadata patch for a taxonomy/status value change."""

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
SCALAR_FIELDS = {"research_line", "line_role", "status", "reading_stage", "review_stage"}
SUPPORTED_FIELDS = sorted(LIST_FIELDS | SCALAR_FIELDS)
AUDIT_FIELDS = ["source_field", "source_value", "previous_value", "next_value", "display_title", "href"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an apply_library_metadata.py patch for a taxonomy/status change.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing papers.json.",
    )
    parser.add_argument("--field", required=True, choices=SUPPORTED_FIELDS, help="Metadata field to change.")
    parser.add_argument("--from-value", required=True, help="Existing value to match exactly.")
    parser.add_argument("--to-value", required=True, help="Replacement value to write.")
    parser.add_argument("--output", "-o", help="Output CSV path. Defaults to stdout.")
    parser.add_argument(
        "--case-insensitive",
        action="store_true",
        help="Match --from-value case-insensitively while preserving other list values.",
    )
    parser.add_argument(
        "--fail-if-empty",
        action="store_true",
        help="Exit with an error when no papers match.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def resolve_output_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def load_papers(report_dir: Path) -> list[dict[str, Any]]:
    path = report_dir / "papers.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if not isinstance(papers, list):
        raise ValueError("papers.json has invalid 'papers' payload")
    return papers


def same_value(left: str, right: str, case_insensitive: bool) -> bool:
    if case_insensitive:
        return left.casefold() == right.casefold()
    return left == right


def clean_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def paper_href(paper: dict[str, Any]) -> str:
    return str(paper.get("html_path") or paper.get("md_path") or "")


def replacement_list(values: list[str], from_value: str, to_value: str, case_insensitive: bool) -> list[str]:
    next_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        replacement = to_value if same_value(value, from_value, case_insensitive) else value
        text = str(replacement or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key not in seen:
            next_values.append(text)
            seen.add(key)
    return next_values


def patch_rows(papers: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[str], list[dict[str, str]]]:
    field = str(args.field)
    from_value = str(args.from_value).strip()
    to_value = str(args.to_value).strip()
    if not from_value:
        raise ValueError("--from-value must be non-empty")
    if not to_value:
        raise ValueError("--to-value must be non-empty")

    list_field = field in LIST_FIELDS
    header = ["slug", field]
    if list_field:
        header.append("_list_mode")
    header.extend(AUDIT_FIELDS)
    rows: list[dict[str, str]] = []
    for paper in papers:
        slug = str(paper.get("slug") or "").strip()
        if not slug:
            continue
        if list_field:
            current_values = clean_list(paper.get(field))
            if not any(same_value(value, from_value, args.case_insensitive) for value in current_values):
                continue
            next_values = replacement_list(current_values, from_value, to_value, args.case_insensitive)
            row = {
                "slug": slug,
                field: "; ".join(next_values),
                "_list_mode": "replace",
                "previous_value": "; ".join(current_values),
                "next_value": "; ".join(next_values),
            }
        else:
            current = str(paper.get(field) or "").strip()
            if not same_value(current, from_value, args.case_insensitive):
                continue
            row = {
                "slug": slug,
                field: to_value,
                "previous_value": current,
                "next_value": to_value,
            }
        row.update(
            {
                "source_field": field,
                "source_value": from_value,
                "display_title": str(paper.get("title_zh") or paper.get("title") or slug),
                "href": paper_href(paper),
            }
        )
        rows.append(row)
    rows.sort(key=lambda item: item["slug"])
    return header, rows


def write_csv(header: list[str], rows: list[dict[str, str]], output: TextIO) -> None:
    writer = csv.DictWriter(output, fieldnames=header, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def write_output(header: list[str], rows: list[dict[str, str]], args: argparse.Namespace) -> None:
    if args.output:
        path = resolve_output_path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            write_csv(header, rows, handle)
        return
    write_csv(header, rows, sys.stdout)


def main() -> int:
    args = parse_args()
    try:
        report_dir = resolve_report_dir(args.report_dir)
        header, rows = patch_rows(load_papers(report_dir), args)
        if args.fail_if_empty and not rows:
            raise ValueError("No papers matched the requested taxonomy change")
        write_output(header, rows, args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
