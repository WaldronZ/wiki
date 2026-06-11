#!/usr/bin/env python3
"""Apply label alias suggestions from quality.json to taxonomy.json.

The command is dry-run by default. Review docs/quality.html first, then run
with --write to merge approved suggestions into guides/taxonomy.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply taxonomy label alias suggestions.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing quality.json and guides/taxonomy.json.",
    )
    parser.add_argument(
        "--quality-json",
        default="quality.json",
        help="quality JSON path, absolute or relative to report_dir.",
    )
    parser.add_argument(
        "--taxonomy-json",
        default="guides/taxonomy.json",
        help="taxonomy config path, absolute or relative to report_dir.",
    )
    parser.add_argument("--write", action="store_true", help="Write taxonomy.json instead of printing a dry-run preview.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing conflicting aliases.")
    parser.add_argument("--canonical", action="append", default=[], help="Apply only suggestions with this canonical label.")
    parser.add_argument("--alias", action="append", default=[], help="Apply only these alias labels. May be repeated.")
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


def selected_suggestions(suggestions: list[dict[str, Any]], canonical_filter: set[str], alias_filter: set[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in suggestions:
        canonical = str(item.get("canonical") or "").strip()
        if canonical_filter and canonical not in canonical_filter:
            continue
        for alias, target in (item.get("aliases") or {}).items():
            alias_text = str(alias).strip()
            target_text = str(target or canonical).strip()
            if not alias_text or not target_text:
                continue
            if alias_filter and alias_text not in alias_filter:
                continue
            aliases[alias_text] = target_text
    return aliases


def load_json_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def display_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    quality_path = resolve_inside_report(report_dir, args.quality_json)
    taxonomy_path = resolve_inside_report(report_dir, args.taxonomy_json)
    quality = load_json_object(quality_path)
    taxonomy = load_json_object(taxonomy_path)

    suggestions = quality.get("label_alias_suggestions") or []
    if not isinstance(suggestions, list):
        raise SystemExit("quality.json label_alias_suggestions must be a list")

    wanted = selected_suggestions(suggestions, set(args.canonical), set(args.alias))
    existing_raw = taxonomy.get("label_aliases") or {}
    if not isinstance(existing_raw, dict):
        raise SystemExit("taxonomy.json label_aliases must be an object")
    existing = {str(alias): str(target) for alias, target in existing_raw.items()}

    applied: dict[str, str] = {}
    skipped: list[str] = []
    conflicts: list[str] = []
    for alias, target in sorted(wanted.items(), key=lambda item: item[0].lower()):
        current = existing.get(alias)
        if current == target:
            skipped.append(f"{alias} -> {target} already present")
            continue
        if current and current != target and not args.force:
            conflicts.append(f"{alias}: existing {current!r}, suggested {target!r}")
            continue
        applied[alias] = target

    for alias, target in applied.items():
        existing[alias] = target

    print(f"quality: {display_path(quality_path, report_dir)}")
    print(f"taxonomy: {display_path(taxonomy_path, report_dir)}")
    if not wanted:
        print("No matching label alias suggestions.")
    for alias, target in applied.items():
        print(f"{'WRITE' if args.write else 'DRY'}  {alias} -> {target}")
    for item in skipped:
        print(f"OK   {item}")
    for item in conflicts:
        print(f"SKIP conflict {item}")

    if applied and args.write:
        taxonomy["label_aliases"] = dict(sorted(existing.items(), key=lambda item: item[0].lower()))
        taxonomy_path.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    action = "updated" if args.write else "would update"
    print(f"{action} {len(applied)} alias(es)")
    if applied and not args.write:
        print("Run again with --write to apply these aliases.")
    if conflicts and not args.force:
        print("Use --force to overwrite conflicting aliases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
