#!/usr/bin/env python3
"""Export a desktop/bootstrap JSON bundle from catalog.json."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export AutoPaperReader catalog bootstrap bundle.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing catalog.json and generated data files.",
    )
    parser.add_argument(
        "--include",
        action="append",
        help="Catalog data file href to include. Can be repeated. Defaults to catalog recommended_bootstrap_files.",
    )
    parser.add_argument(
        "--all-data",
        action="store_true",
        help="Include every data resource declared in catalog.json.",
    )
    parser.add_argument(
        "--no-payloads",
        action="store_true",
        help="Only include file metadata, hashes, and schema shape; do not embed JSON payloads.",
    )
    parser.add_argument("--output", "-o", help="Output path. Defaults to stdout.")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation. Use 0 for compact output.")
    return parser.parse_args()


def resolve_report_dir(value: str) -> Path:
    report_dir = Path(value).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    return report_dir.resolve()


def safe_report_path(report_dir: Path, href: str) -> Path:
    path = (report_dir / href).resolve()
    try:
        path.relative_to(report_dir)
    except ValueError as exc:
        raise ValueError(f"Refusing to read outside report_dir: {href}") from exc
    return path


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run scripts/build_wiki.py first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def collection_summary(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    collections: list[dict[str, Any]] = []
    for key, value in payload.items():
        if isinstance(value, list):
            collections.append({"key": key, "type": "list", "count": len(value)})
        elif isinstance(value, dict):
            collections.append({"key": key, "type": "object", "count": len(value)})
    return collections


def catalog_resources(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for item in catalog.get("data_resources") or []:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        if href:
            resources[href] = item
    return resources


def selected_hrefs(catalog: dict[str, Any], resources: dict[str, dict[str, Any]], args: argparse.Namespace) -> list[str]:
    if args.all_data:
        candidates = sorted(resources)
    elif args.include:
        candidates = [str(item).strip() for item in args.include if str(item).strip()]
    else:
        candidates = [
            str(item).strip()
            for item in (catalog.get("recommended_bootstrap_files") or [])
            if str(item).strip()
        ]

    seen: set[str] = set()
    hrefs: list[str] = []
    for href in candidates:
        if href in seen:
            continue
        seen.add(href)
        if href not in resources:
            raise ValueError(f"{href} is not listed in catalog.json data_resources")
        hrefs.append(href)
    return hrefs


def file_entry(report_dir: Path, href: str, resource: dict[str, Any], include_payload: bool) -> dict[str, Any]:
    path = safe_report_path(report_dir, href)
    entry: dict[str, Any] = {
        "href": href,
        "description": str(resource.get("description") or ""),
        "consumers": list(resource.get("consumers") or []),
        "exists": path.exists(),
        "size_bytes": 0,
        "sha256": "",
        "top_level_keys": [],
        "collections": [],
        "declared_count": resource.get("declared_count"),
        "generated_at": "",
        "error": "",
    }
    if not path.exists():
        entry["error"] = "missing"
        return entry

    data = path.read_bytes()
    entry["size_bytes"] = len(data)
    entry["sha256"] = sha256_bytes(data)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        entry["error"] = f"invalid json: {exc}"
        return entry

    if isinstance(payload, dict):
        entry["top_level_keys"] = sorted(payload.keys())
        entry["collections"] = collection_summary(payload)
        entry["declared_count"] = payload.get("count", entry["declared_count"])
        entry["generated_at"] = str(payload.get("generated_at") or "")
    else:
        entry["error"] = "payload is not a JSON object"

    if include_payload:
        entry["payload"] = payload
    return entry


def build_bundle(report_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    catalog = load_json(report_dir / "catalog.json")
    resources = catalog_resources(catalog)
    hrefs = selected_hrefs(catalog, resources, args)
    files = [
        file_entry(report_dir, href, resources[href], include_payload=not args.no_payloads)
        for href in hrefs
    ]
    missing = [item["href"] for item in files if not item["exists"]]
    errors = [item for item in files if item.get("error") and item.get("error") != "missing"]
    payload_count = sum(1 for item in files if "payload" in item)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "report_dir": str(report_dir),
        "source_catalog": {
            "href": "catalog.json",
            "generated_at": str(catalog.get("generated_at") or ""),
            "count": catalog.get("count"),
            "data_file_count": catalog.get("data_file_count"),
            "recommended_bootstrap_files": catalog.get("recommended_bootstrap_files") or [],
        },
        "summary": {
            "file_count": len(files),
            "payload_count": payload_count,
            "missing_count": len(missing),
            "error_count": len(errors),
            "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in files),
            "mode": "all_data" if args.all_data else "explicit" if args.include else "recommended",
        },
        "files": files,
        "missing": missing,
        "errors": [{"href": item["href"], "error": item["error"]} for item in errors],
    }


def write_output(payload: dict[str, Any], args: argparse.Namespace) -> None:
    indent = None if args.indent == 0 else args.indent
    text = json.dumps(payload, ensure_ascii=False, indent=indent)
    if indent is not None:
        text += "\n"
    if not args.output:
        sys.stdout.write(text)
        return
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        report_dir = resolve_report_dir(args.report_dir)
        payload = build_bundle(report_dir, args)
        write_output(payload, args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
