#!/usr/bin/env python3
"""Merge candidate paper rows into docs/inbox.csv.

The command is dry-run by default. It accepts the same CSV columns documented in
guides/inbox.schema.json, including common aliases such as name/url/topics.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
FIELDS = ["id", "title", "link", "status", "priority", "tags", "note", "added_at"]
ALIASES = {
    "name": "title",
    "paper": "title",
    "url": "link",
    "arxiv_url": "link",
    "topics": "tags",
    "notes": "note",
    "created_at": "added_at",
}
VALID_STATUSES = {"queued", "triaged", "reading", "done", "skipped"}
VALID_PRIORITIES = {"high", "normal", "medium", "low"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge candidate paper rows into inbox.csv.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing inbox.csv.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Candidate CSV path. Relative paths are resolved from the current directory, report_dir, then repo root.",
    )
    parser.add_argument(
        "--inbox-csv",
        default="inbox.csv",
        help="Inbox CSV path, absolute or relative to report_dir.",
    )
    parser.add_argument("--default-status", default="queued", choices=sorted(VALID_STATUSES))
    parser.add_argument("--default-priority", default="normal", choices=sorted(VALID_PRIORITIES))
    parser.add_argument(
        "--default-added-at",
        default="",
        help="Default added_at date for rows without one. Use 'today' for the current date.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace existing inbox rows instead of merging.")
    parser.add_argument(
        "--skip-known",
        action="store_true",
        help="Skip candidates that appear to already have a report in papers.json.",
    )
    parser.add_argument("--write", action="store_true", help="Write inbox.csv instead of printing a dry-run preview.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def resolve_inside_report(report_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = report_dir / path
    return path.resolve()


def resolve_input_path(report_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    for candidate in (Path.cwd() / path, report_dir / path, ROOT / path):
        if candidate.exists():
            return candidate.resolve()
    return (Path.cwd() / path).resolve()


def canonical_header(value: str | None) -> str:
    name = str(value or "").strip()
    return ALIASES.get(name, name)


def normalize_list_cell(value: str) -> str:
    parts = [part.strip() for part in str(value or "").replace("|", ";").replace(",", ";").split(";")]
    cleaned: list[str] = []
    for part in parts:
        if part and part not in cleaned:
            cleaned.append(part)
    return "; ".join(cleaned)


def normalize_date(value: str, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        dt.date.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a valid YYYY-MM-DD date") from exc
    return text


def default_added_at(value: str) -> str:
    text = str(value or "").strip()
    if text == "today":
        return dt.date.today().isoformat()
    return normalize_date(text, "--default-added-at") if text else ""


def read_csv_rows(path: Path, defaults: argparse.Namespace) -> list[dict[str, str]]:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise SystemExit(f"{path} does not exist") from exc
    with handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise SystemExit(f"{path} must contain a header row")
        rows: list[dict[str, str]] = []
        for row_index, raw in enumerate(reader, start=2):
            normalized = {canonical_header(key): str(value or "").strip() for key, value in raw.items()}
            if not any(normalized.values()):
                continue
            title = normalized.get("title", "")
            link = normalized.get("link", "")
            if not title or not link:
                raise SystemExit(f"{path} row {row_index}: title and link are required")
            status = str(normalized.get("status") or defaults.default_status).strip().lower()
            priority = str(normalized.get("priority") or defaults.default_priority).strip().lower()
            if status not in VALID_STATUSES:
                raise SystemExit(f"{path} row {row_index}: status must be one of {', '.join(sorted(VALID_STATUSES))}")
            if priority not in VALID_PRIORITIES:
                raise SystemExit(f"{path} row {row_index}: priority must be one of {', '.join(sorted(VALID_PRIORITIES))}")
            added_at = normalize_date(normalized.get("added_at", "") or default_added_at(defaults.default_added_at), f"{path} row {row_index}: added_at")
            rows.append(
                {
                    "id": normalized.get("id", ""),
                    "title": title,
                    "link": link,
                    "status": status,
                    "priority": priority,
                    "tags": normalize_list_cell(normalized.get("tags", "")),
                    "note": normalized.get("note", ""),
                    "added_at": added_at,
                }
            )
        return rows


def read_existing_inbox(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [
            {field: str(row.get(field) or row.get(next((alias for alias, target in ALIASES.items() if target == field), ""), "") or "").strip() for field in FIELDS}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]


def merge_key(row: dict[str, str]) -> tuple[str, str]:
    if row.get("id"):
        return ("id", row["id"])
    if row.get("link"):
        return ("link", row["link"].lower())
    return ("title", row.get("title", "").lower())


def known_report_keys(report_dir: Path) -> set[tuple[str, str]]:
    path = report_dir / "papers.json"
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    keys: set[tuple[str, str]] = set()
    for paper in payload.get("papers", []):
        if not isinstance(paper, dict):
            continue
        for field in ("arxiv_url", "code_url"):
            value = str(paper.get(field) or "").strip().lower()
            if value:
                keys.add(("link", value))
        for field in ("title", "title_zh", "title_en"):
            value = str(paper.get(field) or "").strip().lower()
            if value:
                keys.add(("title", value))
    return keys


def merge_rows(
    existing: list[dict[str, str]],
    incoming: list[dict[str, str]],
    replace: bool,
    known_keys: set[tuple[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    merged = [] if replace else existing.copy()
    changes: list[str] = []
    if replace and existing:
        changes.append(f"REPLACE existing inbox rows ({len(existing)} removed)")
    index = {merge_key(row): position for position, row in enumerate(merged)}
    for row in incoming:
        key = merge_key(row)
        title_key = ("title", row["title"].lower())
        link_key = ("link", row["link"].lower())
        if key in known_keys or title_key in known_keys or link_key in known_keys:
            changes.append(f"SKIP known report {row['title']}")
            continue
        if key in index:
            position = index[key]
            action = "OK" if merged[position] == row else "UPDATE"
            merged[position] = row
            changes.append(f"{action} inbox item {row['title']}")
        else:
            index[key] = len(merged)
            merged.append(row)
            changes.append(f"ADD inbox item {row['title']}")
    return merged, changes


def write_inbox(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    input_path = resolve_input_path(report_dir, args.input)
    inbox_path = resolve_inside_report(report_dir, args.inbox_csv)
    incoming = read_csv_rows(input_path, args)
    existing = read_existing_inbox(inbox_path)
    known_keys = known_report_keys(report_dir) if args.skip_known else set()
    merged, changes = merge_rows(existing, incoming, args.replace, known_keys)

    print(f"input: {input_path}")
    print(f"inbox: {inbox_path}")
    for change in changes:
        print(f"{'WRITE' if args.write else 'DRY'}  {change}")
    if args.write:
        write_inbox(inbox_path, merged)
        print(f"updated {inbox_path} ({len(merged)} row(s))")
    else:
        print("Run again with --write to apply these inbox rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
