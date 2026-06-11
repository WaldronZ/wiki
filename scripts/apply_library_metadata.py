#!/usr/bin/env python3
"""Apply spreadsheet-edited library metadata back to report frontmatter.

The command is dry-run by default. Export with export_library_csv.py, edit
taxonomy/status columns in a spreadsheet, then run this script to preview and
optionally write the frontmatter updates.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

LIST_FIELDS = {
    "authors",
    "domains",
    "tracks",
    "problems",
    "topics",
    "methods",
}
LIST_MODES = {"replace", "append", "remove"}
INT_FIELDS = {"year", "importance", "confidence", "reproducibility"}
BOOL_FIELDS = {"has_code"}
SCALAR_FIELDS = {
    "title",
    "title_zh",
    "title_en",
    "arxiv_id",
    "arxiv_url",
    "code_url",
    "project_url",
    "research_line",
    "line_role",
    "status",
    "reading_stage",
    "review_stage",
    "last_reviewed",
    "next_review",
}
UPDATABLE_FIELDS = LIST_FIELDS | INT_FIELDS | BOOL_FIELDS | SCALAR_FIELDS
FIELD_ORDER = [
    "slug",
    "title",
    "title_zh",
    "title_en",
    "arxiv_id",
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
    "importance",
    "confidence",
    "reproducibility",
    "has_code",
    "arxiv_url",
    "code_url",
    "project_url",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply edited library CSV metadata to markdown frontmatter.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing <slug>.md reports.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="CSV file containing a slug column and one or more editable metadata columns.",
    )
    parser.add_argument("--write", action="store_true", help="Write changes instead of printing a dry-run preview.")
    parser.add_argument("--clear-empty", action="store_true", help="Treat empty cells as intentional clears.")
    parser.add_argument(
        "--list-mode",
        choices=sorted(LIST_MODES),
        default="replace",
        help="How list fields from the CSV affect existing frontmatter values.",
    )
    parser.add_argument("--slug", action="append", default=[], help="Limit updates to one slug. May be repeated.")
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Limit updates to one metadata field. May be repeated. Defaults to all editable columns.",
    )
    parser.add_argument(
        "--audit-output",
        help="Write a machine-readable JSON audit of the planned or applied metadata changes.",
    )
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def resolve_input_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def resolve_output_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("unterminated YAML frontmatter")
    frontmatter = text[4:end].strip("\n")
    body = text[end + len("\n---") :]
    return frontmatter, body


def clean_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def parse_frontmatter(frontmatter: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in frontmatter.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_key:
            item = line.strip()
            if item.startswith("- "):
                existing = data.setdefault(current_key, [])
                if not isinstance(existing, list):
                    existing = data[current_key] = [existing]
                existing.append(clean_scalar(item[2:].strip()))
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "":
            data[key] = []
        elif value.startswith("[") and value.endswith("]"):
            data[key] = [clean_scalar(part.strip()) for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = clean_scalar(value)
    return data


def split_list_cell(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    delimiter = ";" if ";" in value else "|" if "|" in value else ","
    items = [item.strip() for item in value.split(delimiter)]
    return [item for item in items if item]


def parse_cell(field: str, raw: str) -> Any:
    value = raw.strip()
    if field in LIST_FIELDS:
        return split_list_cell(value)
    if field in BOOL_FIELDS:
        lowered = value.lower()
        if lowered in {"true", "yes", "1", "y"}:
            return True
        if lowered in {"false", "no", "0", "n"}:
            return False
        raise ValueError(f"{field} expects true/false, got {raw!r}")
    if field in INT_FIELDS:
        if not value:
            return ""
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{field} expects integer, got {raw!r}") from exc
    return value


def normalized(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if value is None:
        return ""
    return str(value).strip()


def list_mode_for(row: dict[str, str], default: str) -> str:
    mode = str(row.get("_list_mode") or row.get("list_mode") or default).strip().lower()
    if mode not in LIST_MODES:
        raise ValueError(f"list mode must be one of {', '.join(sorted(LIST_MODES))}, got {mode!r}")
    return mode


def merge_list_values(existing: Any, incoming: Any, mode: str) -> list[str]:
    current_value = normalized(existing)
    incoming_value = normalized(incoming)
    current = current_value if isinstance(current_value, list) else ([current_value] if current_value else [])
    values = incoming_value if isinstance(incoming_value, list) else ([incoming_value] if incoming_value else [])
    if mode == "replace":
        return values

    seen = {item.casefold() for item in current}
    if mode == "append":
        merged = list(current)
        for item in values:
            key = item.casefold()
            if key not in seen:
                merged.append(item)
                seen.add(key)
        return merged

    remove = {item.casefold() for item in values}
    return [item for item in current if item.casefold() not in remove]


def format_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "":
        return ""
    if text[0] in {"@", "`", "{", "}", "[", "]", "&", "*", "#", "!", "|", ">", "%"} or re.search(r"[:#]\s", text):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def render_field(field: str, value: Any) -> list[str]:
    if field in LIST_FIELDS:
        items = normalized(value)
        if not items:
            return [f"{field}: []"]
        return [f"{field}:"] + [f"  - {format_scalar(item)}" for item in items]
    return [f"{field}: {format_scalar(value)}"]


def field_block(lines: list[str], field: str) -> tuple[int, int] | None:
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(field)}\s*:", line):
            end = index + 1
            while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
                end += 1
            return index, end
    return None


def insert_position(lines: list[str], field: str) -> int:
    try:
        field_index = FIELD_ORDER.index(field)
    except ValueError:
        field_index = len(FIELD_ORDER)

    insert_at = len(lines)
    for prior in reversed(FIELD_ORDER[:field_index]):
        block = field_block(lines, prior)
        if block:
            insert_at = block[1]
            break
    return insert_at


def set_field(frontmatter: str, field: str, value: Any) -> str:
    lines = frontmatter.splitlines()
    replacement = render_field(field, value)
    block = field_block(lines, field)
    if block:
        start, end = block
        next_lines = lines[:start] + replacement + lines[end:]
    else:
        at = insert_position(lines, field)
        next_lines = lines[:at] + replacement + lines[at:]
    return "\n".join(next_lines)


def load_rows(input_path: Path) -> list[dict[str, str]]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "slug" not in reader.fieldnames:
            raise SystemExit("CSV must contain a slug column.")
        return [dict(row) for row in reader]


def editable_fields(row: dict[str, str], selected_fields: set[str]) -> list[str]:
    fields = [field for field in row if field in UPDATABLE_FIELDS]
    if selected_fields:
        fields = [field for field in fields if field in selected_fields]
    return fields


def update_report(
    md_path: Path,
    row: dict[str, str],
    selected_fields: set[str],
    clear_empty: bool,
    default_list_mode: str,
) -> tuple[str, list[dict[str, Any]]]:
    text = md_path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    current = parse_frontmatter(frontmatter)
    changes: list[dict[str, Any]] = []
    next_frontmatter = frontmatter
    list_mode = list_mode_for(row, default_list_mode)

    for field in editable_fields(row, selected_fields):
        raw = str(row.get(field) or "")
        if not raw.strip() and not clear_empty:
            continue
        value = parse_cell(field, raw)
        if field in LIST_FIELDS:
            value = merge_list_values(current.get(field, []), value, list_mode)
        before = normalized(current.get(field, [] if field in LIST_FIELDS else ""))
        after = normalized(value)
        if before == after:
            continue
        next_frontmatter = set_field(next_frontmatter, field, value)
        current[field] = value
        mode_note = f" ({list_mode})" if field in LIST_FIELDS and list_mode != "replace" else ""
        changes.append(
            {
                "field": field,
                "mode": list_mode if field in LIST_FIELDS else "replace",
                "before": before,
                "after": after,
                "display": f"{field}{mode_note}: {before!r} -> {after!r}",
            }
        )

    return f"---\n{next_frontmatter}\n---{body}", changes


def write_audit(
    output_path: Path,
    report_dir: Path,
    input_path: Path,
    args: argparse.Namespace,
    reports: list[dict[str, Any]],
    skipped: list[dict[str, str]],
) -> None:
    field_counts: dict[str, int] = {}
    for report in reports:
        for change in report["changes"]:
            field = str(change["field"])
            field_counts[field] = field_counts.get(field, 0) + 1
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": "write" if args.write else "dry_run",
        "write": bool(args.write),
        "report_dir": report_dir.as_posix(),
        "input": input_path.as_posix(),
        "clear_empty": bool(args.clear_empty),
        "list_mode": args.list_mode,
        "selected_slugs": sorted(args.slug),
        "selected_fields": sorted(args.field),
        "summary": {
            "changed_reports": len(reports),
            "skipped_reports": len(skipped),
            "total_changes": sum(len(report["changes"]) for report in reports),
            "changed_fields": dict(sorted(field_counts.items())),
        },
        "reports": reports,
        "skipped": skipped,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    input_path = resolve_input_path(args.input)
    selected_slugs = set(args.slug)
    selected_fields = set(args.field)
    unknown_fields = selected_fields - UPDATABLE_FIELDS
    if unknown_fields:
        print(f"Unknown editable field(s): {', '.join(sorted(unknown_fields))}", file=sys.stderr)
        return 2

    rows = load_rows(input_path)
    changed = 0
    skipped = 0
    audit_reports: list[dict[str, Any]] = []
    audit_skipped: list[dict[str, str]] = []

    for row in rows:
        slug = str(row.get("slug") or "").strip()
        if not slug or (selected_slugs and slug not in selected_slugs):
            continue
        md_path = report_dir / f"{slug}.md"
        if not md_path.exists():
            skipped += 1
            print(f"SKIP {slug}: missing {md_path}")
            audit_skipped.append({"slug": slug, "reason": f"missing {md_path}"})
            continue
        try:
            next_text, changes = update_report(md_path, row, selected_fields, args.clear_empty, args.list_mode)
        except (ValueError, OSError) as exc:
            skipped += 1
            print(f"SKIP {slug}: {exc}")
            audit_skipped.append({"slug": slug, "reason": str(exc)})
            continue
        if not changes:
            print(f"OK   {slug}: no metadata changes")
            continue
        changed += 1
        audit_reports.append(
            {
                "slug": slug,
                "path": md_path.as_posix(),
                "changes": changes,
            }
        )
        print(f"{'WRITE' if args.write else 'DRY'}  {slug}:")
        for change in changes:
            print(f"  - {change['display']}")
        if args.write:
            md_path.write_text(next_text, encoding="utf-8")

    action = "updated" if args.write else "would update"
    print(f"{action} {changed} report(s); skipped {skipped}.")
    if args.audit_output:
        audit_path = resolve_output_path(args.audit_output)
        write_audit(audit_path, report_dir, input_path, args, audit_reports, audit_skipped)
        print(f"audit written to {audit_path}")
    if not args.write:
        print("Run again with --write to apply these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
