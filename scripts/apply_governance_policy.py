#!/usr/bin/env python3
"""Apply governance policy thresholds to guides/taxonomy.json.

The command is dry-run by default. It accepts the JSON downloaded from
docs/taxonomy.html, either as {"governance_policy": {...}} or as the policy
object itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
POLICY_FIELDS: dict[str, dict[str, type]] = {
    "taxonomy_load": {
        "min_structure_labels": int,
        "min_tags": int,
        "max_tags": int,
        "max_methods": int,
    },
    "taxonomy_actions": {
        "singleton_max_count": int,
        "watch_share": float,
        "watch_min_count": int,
        "split_share": float,
        "split_min_count": int,
    },
    "taxonomy_balance": {
        "high_score_below": int,
        "medium_score_below": int,
        "singleton_medium_count": int,
        "unused_medium_count": int,
    },
    "coverage": {
        "high_score_below": int,
        "medium_score_below": int,
        "missing_high_min": int,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply governance policy thresholds to taxonomy.json.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing guides/taxonomy.json.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Policy JSON path. Relative paths are resolved from the current directory, report_dir, then repo root.",
    )
    parser.add_argument(
        "--taxonomy-json",
        default="guides/taxonomy.json",
        help="taxonomy config path, absolute or relative to report_dir.",
    )
    parser.add_argument("--write", action="store_true", help="Write taxonomy.json instead of printing a dry-run preview.")
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


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def display_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def clean_policy(payload: dict[str, Any]) -> dict[str, dict[str, int | float]]:
    raw_policy = payload.get("governance_policy", payload)
    if not isinstance(raw_policy, dict):
        raise SystemExit("governance_policy must be an object")

    unknown_sections = sorted(set(raw_policy) - set(POLICY_FIELDS))
    if unknown_sections:
        raise SystemExit(f"governance_policy has unknown sections: {', '.join(unknown_sections)}")

    policy: dict[str, dict[str, int | float]] = {}
    for section, field_types in POLICY_FIELDS.items():
        raw_section = raw_policy.get(section, {})
        if raw_section in (None, {}):
            continue
        if not isinstance(raw_section, dict):
            raise SystemExit(f"governance_policy.{section} must be an object")
        unknown_keys = sorted(set(raw_section) - set(field_types))
        if unknown_keys:
            raise SystemExit(f"governance_policy.{section} has unknown keys: {', '.join(unknown_keys)}")
        cleaned: dict[str, int | float] = {}
        for key, expected_type in field_types.items():
            if key not in raw_section:
                continue
            value = raw_section[key]
            if expected_type is int:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise SystemExit(f"governance_policy.{section}.{key} must be a non-negative integer")
                cleaned[key] = value
            else:
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    raise SystemExit(f"governance_policy.{section}.{key} must be a non-negative number")
                cleaned[key] = float(value)
        if cleaned:
            policy[section] = cleaned
    if not policy:
        raise SystemExit("governance_policy must contain at least one supported threshold")
    return policy


def merge_policy(
    taxonomy: dict[str, Any],
    incoming: dict[str, dict[str, int | float]],
) -> tuple[dict[str, Any], list[str]]:
    merged = dict(taxonomy)
    existing = taxonomy.get("governance_policy") or {}
    if not isinstance(existing, dict):
        raise SystemExit("taxonomy.json governance_policy must be an object")

    policy = {section: dict(values) for section, values in existing.items() if isinstance(values, dict)}
    changes: list[str] = []
    for section, values in incoming.items():
        current_section = policy.setdefault(section, {})
        for key, value in values.items():
            previous = current_section.get(key)
            if previous == value:
                changes.append(f"OK {section}.{key} = {value}")
            else:
                action = "ADD" if previous is None else "UPDATE"
                changes.append(f"{action} {section}.{key} {previous if previous is not None else '<unset>'} -> {value}")
            current_section[key] = value
    merged["governance_policy"] = policy
    return merged, changes


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    input_path = resolve_input_path(report_dir, args.input)
    taxonomy_path = resolve_inside_report(report_dir, args.taxonomy_json)
    payload = load_json_object(input_path)
    taxonomy = load_json_object(taxonomy_path)
    policy = clean_policy(payload)
    updated, changes = merge_policy(taxonomy, policy)

    print(f"input: {display_path(input_path, report_dir)}")
    print(f"taxonomy: {display_path(taxonomy_path, report_dir)}")
    for change in changes:
        print(f"{'WRITE' if args.write else 'DRY'}  {change}")

    if args.write:
        taxonomy_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {display_path(taxonomy_path, report_dir)}")
    else:
        print("Run again with --write to apply this governance policy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
