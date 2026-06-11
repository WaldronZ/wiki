#!/usr/bin/env python3
"""Apply shared view JSON snippets to guides/taxonomy.json.

The command is dry-run by default. It accepts a single shared view object,
a {"shared_views": [...]} package, or a browser-exported {"saved_views": [...]}
package from index.html/library.html.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
VIEW_PAGES = {"all", "index", "library"}
VIEW_STATE_KEYS = {
    "q",
    "domain",
    "track",
    "problem",
    "line",
    "role",
    "workflow",
    "topic",
    "method",
    "status",
    "stage",
    "reviewStage",
    "review",
    "code",
    "importance",
    "sort",
    "size",
    "page",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply shared saved views to taxonomy.json.")
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
        help="Shared view JSON path. Relative paths are resolved from the current directory, report_dir, then repo root.",
    )
    parser.add_argument(
        "--taxonomy-json",
        default="guides/taxonomy.json",
        help="taxonomy config path, absolute or relative to report_dir.",
    )
    parser.add_argument(
        "--page",
        choices=sorted(VIEW_PAGES),
        help="Default page for imported saved_views that do not carry page.",
    )
    parser.add_argument("--replace", action="store_true", help="Replace all existing shared_views instead of merging.")
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


def load_json_object(path: Path) -> dict[str, Any] | list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is invalid JSON: {exc}") from exc
    if not isinstance(data, (dict, list)):
        raise SystemExit(f"{path} must contain a JSON object or list")
    return data


def display_path(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def payload_views(payload: dict[str, Any] | list[Any]) -> tuple[list[Any], str]:
    if isinstance(payload, list):
        return payload, ""
    if isinstance(payload.get("shared_views"), list):
        return payload["shared_views"], str(payload.get("page") or "").strip()
    if isinstance(payload.get("saved_views"), list):
        return payload["saved_views"], str(payload.get("page") or "").strip()
    if payload.get("name") and isinstance(payload.get("state"), dict):
        return [payload], str(payload.get("page") or "").strip()
    raise SystemExit("input must contain shared_views, saved_views, or a single view object")


def clean_view(raw: Any, default_page: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SystemExit("each shared view must be an object")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise SystemExit("shared view name must be a non-empty string")
    page = str(raw.get("page") or default_page or "all").strip() or "all"
    if page not in VIEW_PAGES:
        raise SystemExit(f"shared view {name!r} page must be one of: {', '.join(sorted(VIEW_PAGES))}")
    state_raw = raw.get("state")
    if not isinstance(state_raw, dict) or not state_raw:
        raise SystemExit(f"shared view {name!r} state must be a non-empty object")
    state: dict[str, str] = {}
    for key, value in state_raw.items():
        field = str(key).strip()
        if field not in VIEW_STATE_KEYS:
            raise SystemExit(f"shared view {name!r} has unknown state key: {field}")
        if isinstance(value, (dict, list)) or value is None:
            raise SystemExit(f"shared view {name!r} state.{field} must be a scalar value")
        text = str(value).strip()
        if text:
            state[field] = text
    if not state:
        raise SystemExit(f"shared view {name!r} state must contain at least one non-empty value")
    return {"name": name, "page": page, "state": state}


def parse_views(payload: dict[str, Any] | list[Any], page_override: str | None) -> list[dict[str, Any]]:
    views_raw, payload_page = payload_views(payload)
    default_page = page_override or payload_page or "all"
    seen: set[tuple[str, str]] = set()
    views: list[dict[str, Any]] = []
    for raw in views_raw:
        view = clean_view(raw, default_page)
        key = (view["page"], view["name"].casefold())
        if key in seen:
            raise SystemExit(f"duplicate shared view in input: {view['page']} / {view['name']}")
        seen.add(key)
        views.append(view)
    return views


def merge_views(
    taxonomy: dict[str, Any],
    incoming: list[dict[str, Any]],
    replace: bool,
) -> tuple[dict[str, Any], list[str]]:
    existing_raw = taxonomy.get("shared_views") or []
    if not isinstance(existing_raw, list):
        raise SystemExit("taxonomy.json shared_views must be a list")
    existing = [clean_view(view, "all") for view in existing_raw]
    merged = [] if replace else existing.copy()
    changes: list[str] = []

    index = {(view["page"], view["name"].casefold()): position for position, view in enumerate(merged)}
    if replace and existing:
        changes.append(f"REPLACE existing shared views ({len(existing)} removed)")
    for view in incoming:
        key = (view["page"], view["name"].casefold())
        if key in index:
            position = index[key]
            action = "OK" if merged[position] == view else "UPDATE"
            merged[position] = view
            changes.append(f"{action} shared view {view['page']} / {view['name']}")
        else:
            index[key] = len(merged)
            merged.append(view)
            changes.append(f"ADD shared view {view['page']} / {view['name']}")

    updated = dict(taxonomy)
    updated["shared_views"] = merged
    return updated, changes


def main() -> int:
    args = parse_args()
    report_dir = resolve_report_dir(args.report_dir)
    input_path = resolve_input_path(report_dir, args.input)
    taxonomy_path = resolve_inside_report(report_dir, args.taxonomy_json)
    payload = load_json_object(input_path)
    taxonomy_payload = load_json_object(taxonomy_path)
    if not isinstance(taxonomy_payload, dict):
        raise SystemExit("taxonomy.json must contain a JSON object")
    incoming = parse_views(payload, args.page)
    updated, changes = merge_views(taxonomy_payload, incoming, args.replace)

    print(f"input: {display_path(input_path, report_dir)}")
    print(f"taxonomy: {display_path(taxonomy_path, report_dir)}")
    for change in changes:
        print(f"{'WRITE' if args.write else 'DRY'}  {change}")
    if args.write:
        taxonomy_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"updated {display_path(taxonomy_path, report_dir)}")
    else:
        print("Run again with --write to apply these shared views.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
