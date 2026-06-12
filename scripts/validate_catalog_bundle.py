#!/usr/bin/env python3
"""Validate an AutoPaperReader bootstrap bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an AutoPaperReader catalog bootstrap bundle.")
    parser.add_argument("bundle", help="Path to bootstrap-bundle.json or bootstrap-manifest.json.")
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing generated wiki data files for hash checks. Use --skip-hash-check to disable.",
    )
    parser.add_argument(
        "--require-payloads",
        action="store_true",
        help="Require every existing file entry to embed a payload object.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Require the bundle to contain no embedded payloads.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow missing files listed by the bundle.",
    )
    parser.add_argument(
        "--skip-hash-check",
        action="store_true",
        help="Do not compare bundle hashes and sizes with files on disk.",
    )
    return parser.parse_args()


def resolve_path(value: str, base: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def safe_report_path(report_dir: Path, href: str) -> Path:
    path = (report_dir / href).resolve()
    try:
        path.relative_to(report_dir)
    except ValueError as exc:
        raise ValueError(f"refuses path outside report_dir: {href}") from exc
    return path


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_keys(item: dict[str, Any], keys: tuple[str, ...], label: str, errors: list[str]) -> None:
    for key in keys:
        if key not in item:
            errors.append(f"{label}: missing {key}")


def collection_counts(payload: Any) -> dict[str, tuple[str, int]]:
    if not isinstance(payload, dict):
        return {}
    counts: dict[str, tuple[str, int]] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            counts[key] = ("list", len(value))
        elif isinstance(value, dict):
            counts[key] = ("object", len(value))
    return counts


def validate_payload_shape(entry: dict[str, Any], errors: list[str]) -> None:
    href = str(entry.get("href") or "<unknown>")
    if "payload" not in entry:
        return
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        errors.append(f"{href}: payload must be a JSON object")
        return
    top_level_keys = entry.get("top_level_keys")
    if isinstance(top_level_keys, list):
        expected = sorted(str(key) for key in payload.keys())
        actual = sorted(str(key) for key in top_level_keys)
        if actual != expected:
            errors.append(f"{href}: top_level_keys do not match embedded payload")
    declared = entry.get("declared_count")
    if isinstance(declared, int) and isinstance(payload.get("count"), int) and declared != payload.get("count"):
        errors.append(f"{href}: declared_count does not match payload.count")
    collection_by_key = collection_counts(payload)
    for collection in entry.get("collections") or []:
        if not isinstance(collection, dict):
            errors.append(f"{href}: collections entries must be objects")
            continue
        key = str(collection.get("key") or "")
        expected = collection_by_key.get(key)
        if not expected:
            errors.append(f"{href}: collection {key} is not present in payload")
            continue
        kind, count = expected
        if collection.get("type") != kind or collection.get("count") != count:
            errors.append(f"{href}: collection {key} summary does not match payload")


def validate_file_entry(
    entry: Any,
    index: int,
    args: argparse.Namespace,
    report_dir: Path,
    errors: list[str],
) -> None:
    label = f"files[{index}]"
    if not isinstance(entry, dict):
        errors.append(f"{label}: must be an object")
        return
    require_keys(
        entry,
        (
            "href",
            "exists",
            "size_bytes",
            "sha256",
            "top_level_keys",
            "collections",
            "error",
        ),
        label,
        errors,
    )
    href = str(entry.get("href") or "").strip()
    if not href:
        errors.append(f"{label}: href must be non-empty")
        return
    exists = bool(entry.get("exists"))
    if not exists and not args.allow_missing:
        errors.append(f"{href}: missing files are not allowed")
    if args.require_payloads and exists and entry.get("error", "") == "" and "payload" not in entry:
        errors.append(f"{href}: payload is required")
    if args.metadata_only and "payload" in entry:
        errors.append(f"{href}: metadata-only bundle must not embed payload")

    sha256 = str(entry.get("sha256") or "")
    if exists and not SHA256_RE.match(sha256):
        errors.append(f"{href}: sha256 must be 64 lowercase hex characters")
    size = entry.get("size_bytes")
    if not isinstance(size, int) or size < 0:
        errors.append(f"{href}: size_bytes must be a non-negative integer")
    if not isinstance(entry.get("top_level_keys"), list):
        errors.append(f"{href}: top_level_keys must be a list")
    if not isinstance(entry.get("collections"), list):
        errors.append(f"{href}: collections must be a list")
    validate_payload_shape(entry, errors)

    if args.skip_hash_check:
        return
    try:
        path = safe_report_path(report_dir, href)
    except ValueError as exc:
        errors.append(f"{href}: {exc}")
        return
    if not path.exists():
        if exists:
            errors.append(f"{href}: bundle says file exists, but it is missing on disk")
        return
    if not exists:
        errors.append(f"{href}: bundle says file is missing, but it exists on disk")
        return
    actual_size = path.stat().st_size
    if actual_size != size:
        errors.append(f"{href}: size mismatch bundle={size} disk={actual_size}")
    actual_hash = sha256_path(path)
    if actual_hash != sha256:
        errors.append(f"{href}: sha256 mismatch bundle={sha256} disk={actual_hash}")


def validate_bundle(payload: Any, args: argparse.Namespace, report_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["bundle root must be a JSON object"]

    require_keys(payload, ("generated_at", "report_dir", "source_catalog", "summary", "files", "missing", "errors"), "bundle", errors)
    source_catalog = payload.get("source_catalog")
    if not isinstance(source_catalog, dict):
        errors.append("source_catalog must be an object")
    else:
        require_keys(source_catalog, ("href", "generated_at", "count", "data_file_count", "recommended_bootstrap_files"), "source_catalog", errors)
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be an object")
        summary = {}
    else:
        require_keys(summary, ("file_count", "payload_count", "missing_count", "error_count", "total_size_bytes", "mode"), "summary", errors)
        if summary.get("mode") not in {"recommended", "explicit", "all_data"}:
            errors.append("summary.mode must be recommended, explicit, or all_data")

    files = payload.get("files")
    if not isinstance(files, list):
        errors.append("files must be a list")
        files = []
    missing = payload.get("missing")
    if not isinstance(missing, list):
        errors.append("missing must be a list")
        missing = []
    bundle_errors = payload.get("errors")
    if not isinstance(bundle_errors, list):
        errors.append("errors must be a list")
        bundle_errors = []

    if isinstance(summary.get("file_count"), int) and summary["file_count"] != len(files):
        errors.append("summary.file_count does not match files length")
    payload_count = sum(1 for item in files if isinstance(item, dict) and "payload" in item)
    if isinstance(summary.get("payload_count"), int) and summary["payload_count"] != payload_count:
        errors.append("summary.payload_count does not match embedded payload count")
    missing_hrefs = [str(item.get("href") or "") for item in files if isinstance(item, dict) and not item.get("exists")]
    if sorted(str(item) for item in missing) != sorted(missing_hrefs):
        errors.append("missing list does not match files marked missing")
    if isinstance(summary.get("missing_count"), int) and summary["missing_count"] != len(missing):
        errors.append("summary.missing_count does not match missing length")
    if isinstance(summary.get("error_count"), int) and summary["error_count"] != len(bundle_errors):
        errors.append("summary.error_count does not match errors length")
    if args.metadata_only and summary.get("payload_count") != 0:
        errors.append("metadata-only bundle must have summary.payload_count=0")

    seen: set[str] = set()
    for index, entry in enumerate(files):
        if isinstance(entry, dict):
            href = str(entry.get("href") or "")
            if href in seen:
                errors.append(f"{href}: duplicate file entry")
            seen.add(href)
        validate_file_entry(entry, index, args, report_dir, errors)
    return errors


def main() -> int:
    args = parse_args()
    bundle_path = resolve_path(args.bundle)
    report_dir = resolve_path(args.report_dir)
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: {bundle_path} does not exist", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}", file=sys.stderr)
        return 1

    errors = validate_bundle(payload, args, report_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    files = payload.get("files") if isinstance(payload, dict) else []
    file_count = len(files) if isinstance(files, list) else 0
    mode = ((payload.get("summary") or {}).get("mode") if isinstance(payload, dict) else "") or "unknown"
    print(f"Bundle validation passed for {file_count} files ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
