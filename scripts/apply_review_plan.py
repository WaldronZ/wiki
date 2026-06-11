#!/usr/bin/env python3
"""Apply generated review suggestions back to markdown frontmatter.

The command is dry-run by default. Use --write when the preview looks right.
It only fills missing review_stage and next_review fields unless --force is
provided, so hand-curated review metadata stays intact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply docs/review.json suggestions to report frontmatter.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing <slug>.md reports and review.json.",
    )
    parser.add_argument(
        "--review-json",
        default="review.json",
        help="Review plan JSON path, absolute or relative to report_dir.",
    )
    parser.add_argument("--stage", default="fresh", help="review_stage value to insert when missing.")
    parser.add_argument("--write", action="store_true", help="Write changes instead of printing a dry-run preview.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing review_stage and next_review values.")
    parser.add_argument("--slug", action="append", default=[], help="Limit updates to one slug. May be repeated.")
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    frontmatter = text[4:end].strip("\n")
    body = text[end + len("\n---") :]
    return frontmatter, body


def scalar_fields(frontmatter: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if not value.startswith("["):
            fields[key.strip()] = value.strip('"').strip("'")
    return fields


def insert_after(lines: list[str], anchors: tuple[str, ...], new_lines: list[str]) -> list[str]:
    insert_at = len(lines)
    for index, line in enumerate(lines):
        if any(line.startswith(f"{anchor}:") for anchor in anchors):
            insert_at = index + 1
    return lines[:insert_at] + new_lines + lines[insert_at:]


def update_frontmatter(frontmatter: str, item: dict[str, Any], stage: str, force: bool) -> tuple[str, list[str]]:
    fields = scalar_fields(frontmatter)
    lines = frontmatter.splitlines()
    additions: list[str] = []
    changes: list[str] = []

    suggested_next = str(item.get("suggested_next_review") or "").strip()
    if not suggested_next:
        return frontmatter, []

    if force or not fields.get("review_stage"):
        if "review_stage" in fields:
            lines = replace_scalar(lines, "review_stage", stage)
            changes.append(f"review_stage={stage}")
        else:
            additions.append(f"review_stage: {stage}")
            changes.append(f"review_stage={stage}")

    if force or not fields.get("next_review"):
        if "next_review" in fields:
            lines = replace_scalar(lines, "next_review", suggested_next)
            changes.append(f"next_review={suggested_next}")
        else:
            additions.append(f"next_review: {suggested_next}")
            changes.append(f"next_review={suggested_next}")

    if additions:
        lines = insert_after(lines, ("reading_stage", "review_stage"), additions)
    return "\n".join(lines), changes


def replace_scalar(lines: list[str], key: str, value: str) -> list[str]:
    replaced: list[str] = []
    for line in lines:
        if line.startswith(f"{key}:"):
            replaced.append(f"{key}: {value}")
        else:
            replaced.append(line)
    return replaced


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def resolve_review_path(report_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = report_dir / path
    return path.resolve()


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    review_path = resolve_review_path(report_dir, args.review_json)
    plan = json.loads(review_path.read_text(encoding="utf-8"))
    selected = set(args.slug)
    changed = 0

    for item in plan.get("items", []):
        slug = str(item.get("slug") or "").strip()
        if not slug or (selected and slug not in selected):
            continue
        md_path = report_dir / f"{slug}.md"
        if not md_path.exists():
            print(f"SKIP {slug}: missing {md_path}")
            continue
        text = md_path.read_text(encoding="utf-8")
        try:
            frontmatter, body = split_frontmatter(text)
        except ValueError as exc:
            print(f"SKIP {slug}: {exc}")
            continue
        next_frontmatter, changes = update_frontmatter(frontmatter, item, args.stage, args.force)
        if not changes:
            print(f"OK   {slug}: already has review metadata")
            continue
        changed += 1
        print(f"{'WRITE' if args.write else 'DRY'}  {slug}: {', '.join(changes)}")
        if args.write:
            md_path.write_text(f"---\n{next_frontmatter}\n---{body}", encoding="utf-8")

    action = "updated" if args.write else "would update"
    print(f"{action} {changed} report(s)")
    if not args.write:
        print("Run again with --write to apply these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
