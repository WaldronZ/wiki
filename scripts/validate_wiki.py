#!/usr/bin/env python3
"""Validate generated AutoPaperReader wiki artifacts.

The validator is intentionally standard-library only so it can run in CI or on
fresh clones before publishing a large paper library.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

REQUIRED_META = {
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
    "importance",
    "confidence",
    "reproducibility",
    "has_code",
}

DEFAULT_METADATA_SCHEMA: dict[str, Any] = {
    "required": sorted(REQUIRED_META),
    "fields": {
        "slug": {"type": "string", "pattern": r"^[a-z0-9][a-z0-9.-]*-[a-z0-9][a-z0-9-]*$"},
        "title": {"type": "string"},
        "title_zh": {"type": "string"},
        "title_en": {"type": "string"},
        "arxiv_id": {
            "type": "string",
            "pattern": r"^(\d{4}\.\d{4,5}(v\d+)?|noarxiv-[a-z0-9][a-z0-9-]*)$",
        },
        "year": {"type": "integer", "min": 1900, "max": 2100},
        "authors": {"type": "list", "items": "string", "min_items": 1},
        "domains": {"type": "list", "items": "string", "min_items": 1},
        "tracks": {"type": "list", "items": "string", "min_items": 1},
        "problems": {"type": "list", "items": "string", "min_items": 1},
        "topics": {"type": "list", "items": "string", "min_items": 1},
        "methods": {"type": "list", "items": "string", "min_items": 1},
        "research_line": {"type": "string"},
        "line_role": {"type": "string"},
        "status": {"type": "string"},
        "reading_stage": {"type": "string"},
        "review_stage": {"type": "string", "required": False},
        "last_reviewed": {"type": "date", "required": False},
        "next_review": {"type": "date", "required": False},
        "importance": {"type": "integer", "min": 1, "max": 5},
        "confidence": {"type": "integer", "min": 1, "max": 5},
        "reproducibility": {"type": "integer", "min": 1, "max": 5},
        "has_code": {"type": "boolean"},
    },
}

DEFAULT_INBOX_SCHEMA: dict[str, Any] = {
    "required": ["title", "link"],
    "fields": {
        "id": {"type": "string", "required": False},
        "title": {"type": "string", "required": True},
        "link": {"type": "string", "required": True},
        "status": {"type": "string", "required": False, "enum": ["queued", "triaged", "reading", "done", "skipped"]},
        "priority": {"type": "string", "required": False, "enum": ["high", "normal", "medium", "low"]},
        "tags": {"type": "list", "required": False, "separator": ";"},
        "note": {"type": "string", "required": False},
        "added_at": {"type": "date", "required": False},
    },
    "aliases": {
        "title": ["name", "paper"],
        "link": ["url", "arxiv_url"],
        "note": ["notes"],
        "added_at": ["created_at"],
        "tags": ["topics"],
    },
}

REQUIRED_PAGES = {
    "index.html",
    "command.html",
    "library.html",
    "board.html",
    "workflow.html",
    "status.html",
    "views.html",
    "batch.html",
    "pivot.html",
    "compare.html",
    "taxonomy_map.html",
    "clusters.html",
    "roadmap.html",
    "scale.html",
    "ownership.html",
    "routing.html",
    "onboarding.html",
    "catalog.html",
    "intake.html",
    "inbox.html",
    "dedupe.html",
    "registry.html",
    "quality.html",
    "review.html",
    "freshness.html",
    "dashboard.html",
    "release.html",
    "snapshot.html",
    "collections.html",
    "facets.html",
    "related.html",
    "taxonomy.html",
    "timeline.html",
    "matrix.html",
    "gaps.html",
    "tags.html",
    "papers.json",
    "search_index.json",
    "stats.json",
    "inbox.json",
    "dedupe.json",
    "registry.json",
    "facets.json",
    "quality.json",
    "review.json",
    "freshness.json",
    "taxonomy_actions.json",
    "actions.json",
    "command.json",
    "workflow.json",
    "status.json",
    "views.json",
    "batch.json",
    "collections.json",
    "coverage.json",
    "gaps.json",
    "pivot.json",
    "compare.json",
    "taxonomy_map.json",
    "clusters.json",
    "roadmap.json",
    "scale.json",
    "ownership.json",
    "routing.json",
    "onboarding.json",
    "catalog.json",
    "snapshot.json",
    "intake.json",
    "manifest.json",
    "lines/index.html",
}

TAXONOMY_CONFIG_LIST_FIELDS = {
    "role_order",
    "status_values",
    "reading_stage_values",
    "review_stage_values",
}
SHARED_VIEW_PAGES = {"all", "index", "library"}
SHARED_VIEW_STATE_KEYS = {
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
GOVERNANCE_POLICY_FIELDS: dict[str, dict[str, type]] = {
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


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"a", "img", "script", "link"}:
            return
        keys = {"a": "href", "img": "src", "script": "src", "link": "href"}
        for key, value in attrs:
            if key == keys[tag] and value:
                self.links.append(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate AutoPaperReader wiki artifacts.")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing generated wiki files and paper reports.",
    )
    parser.add_argument(
        "--strict-taxonomy",
        action="store_true",
        help="Treat report values outside configured taxonomy lists as errors instead of warnings.",
    )
    return parser.parse_args()


def strip_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip("\n")
    body = text[end + len("\n---") :].lstrip("\n")
    return parse_simple_yaml(raw), body


def parse_simple_yaml(raw: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None

    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_key:
            item = line.strip()
            if item.startswith("- "):
                existing = data.setdefault(current_key, [])
                if not isinstance(existing, list):
                    existing = data[current_key] = [existing]
                existing.append(clean_yaml_scalar(item[2:].strip()))
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
            data[key] = [
                clean_yaml_scalar(part.strip())
                for part in value[1:-1].split(",")
                if part.strip()
            ]
        else:
            data[key] = clean_yaml_scalar(value)

    return data


def clean_yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [item for item in value if str(item).strip()]
    return [value]


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return len(as_list(value)) == 0
    return str(value).strip() == ""


def paper_markdown_paths(report_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(report_dir.glob("*.md"))
        if not path.name.startswith(".") and path.stem not in {"index", "README"}
    ]


def load_metadata_schema(report_dir: Path, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    schema_path = report_dir / "guides" / "metadata.schema.json"
    if not schema_path.exists():
        warnings.append("guides/metadata.schema.json missing; using built-in metadata schema")
        return DEFAULT_METADATA_SCHEMA

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/metadata.schema.json: invalid JSON: {exc}")
        return DEFAULT_METADATA_SCHEMA

    if not isinstance(schema, dict):
        errors.append("guides/metadata.schema.json: root must be an object")
        return DEFAULT_METADATA_SCHEMA

    required = schema.get("required")
    fields = schema.get("fields")
    if not isinstance(required, list) or not all(isinstance(item, str) and item.strip() for item in required):
        errors.append("guides/metadata.schema.json: required must be a list of non-empty strings")
    if not isinstance(fields, dict):
        errors.append("guides/metadata.schema.json: fields must be an object")
        return DEFAULT_METADATA_SCHEMA
    elif isinstance(required, list):
        unknown_required = sorted(set(required) - set(fields))
        if unknown_required:
            errors.append(f"guides/metadata.schema.json: required fields are not defined: {', '.join(unknown_required)}")

    allowed_types = {"string", "integer", "boolean", "list", "date"}
    for name, spec in fields.items():
        if not isinstance(name, str) or not name.strip():
            errors.append("guides/metadata.schema.json: field names must be non-empty strings")
            continue
        if not isinstance(spec, dict):
            errors.append(f"guides/metadata.schema.json: fields.{name} must be an object")
            continue
        field_type = spec.get("type")
        if field_type not in allowed_types:
            allowed_text = ", ".join(sorted(allowed_types))
            errors.append(f"guides/metadata.schema.json: fields.{name}.type must be one of {allowed_text}")
        if field_type == "list" and spec.get("items", "string") != "string":
            errors.append(f"guides/metadata.schema.json: fields.{name}.items must be string")
        for bound in ("min", "max", "min_items"):
            if bound in spec and not isinstance(spec[bound], int):
                errors.append(f"guides/metadata.schema.json: fields.{name}.{bound} must be an integer")
        if "pattern" in spec:
            if not isinstance(spec["pattern"], str):
                errors.append(f"guides/metadata.schema.json: fields.{name}.pattern must be a string")
            else:
                try:
                    re.compile(spec["pattern"])
                except re.error as exc:
                    errors.append(f"guides/metadata.schema.json: fields.{name}.pattern is invalid: {exc}")

    return schema


def load_inbox_schema(report_dir: Path, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    schema_path = report_dir / "guides" / "inbox.schema.json"
    if not schema_path.exists():
        warnings.append("guides/inbox.schema.json missing; using built-in inbox CSV schema")
        return DEFAULT_INBOX_SCHEMA

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/inbox.schema.json: invalid JSON: {exc}")
        return DEFAULT_INBOX_SCHEMA

    if not isinstance(schema, dict):
        errors.append("guides/inbox.schema.json: root must be an object")
        return DEFAULT_INBOX_SCHEMA

    fields = schema.get("fields")
    required = schema.get("required", [])
    if not isinstance(fields, dict):
        errors.append("guides/inbox.schema.json: fields must be an object")
        return DEFAULT_INBOX_SCHEMA
    if not isinstance(required, list) or not all(isinstance(item, str) and item.strip() for item in required):
        errors.append("guides/inbox.schema.json: required must be a list of non-empty strings")
    elif sorted(set(required) - set(fields)):
        errors.append("guides/inbox.schema.json: required fields must be defined in fields")
    return schema


def inbox_header_aliases(schema: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for field in (schema.get("fields") or {}):
        aliases[str(field)] = str(field)
    for canonical, values in (schema.get("aliases") or {}).items():
        if not isinstance(values, list):
            continue
        for alias in values:
            aliases[str(alias)] = str(canonical)
    return aliases


def validate_inbox_csv(report_dir: Path, schema: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    inbox_path = report_dir / "inbox.csv"
    if not inbox_path.exists():
        return

    try:
        with inbox_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            raw_fields = [str(field or "").strip() for field in (reader.fieldnames or [])]
            if not raw_fields:
                errors.append("inbox.csv must contain a header row")
                return
            alias_map = inbox_header_aliases(schema)
            canonical_fields = [alias_map.get(field, field) for field in raw_fields]
            required = set(schema.get("required") or [])
            missing_required = sorted(required - set(canonical_fields))
            if missing_required:
                errors.append(f"inbox.csv missing required column(s): {', '.join(missing_required)}")
            unknown = sorted({field for field in canonical_fields if field not in (schema.get("fields") or {})})
            if unknown:
                warnings.append(f"inbox.csv has unknown column(s): {', '.join(unknown)}")

            seen_ids: set[str] = set()
            for row_index, row in enumerate(reader, start=2):
                normalized = {alias_map.get(str(key or "").strip(), str(key or "").strip()): str(value or "").strip() for key, value in row.items()}
                if not any(normalized.values()):
                    continue
                for field in required:
                    if not normalized.get(field):
                        errors.append(f"inbox.csv row {row_index}: missing required '{field}'")
                item_id = normalized.get("id")
                if item_id:
                    if item_id in seen_ids:
                        errors.append(f"inbox.csv row {row_index}: duplicate id {item_id!r}")
                    seen_ids.add(item_id)
                for field, spec in (schema.get("fields") or {}).items():
                    value = normalized.get(str(field), "")
                    if not value:
                        continue
                    enum = spec.get("enum") if isinstance(spec, dict) else None
                    if isinstance(enum, list) and value not in enum:
                        errors.append(f"inbox.csv row {row_index}: {field} must be one of {', '.join(str(item) for item in enum)}")
                    if isinstance(spec, dict) and spec.get("type") == "date":
                        try:
                            dt.date.fromisoformat(value)
                        except ValueError:
                            errors.append(f"inbox.csv row {row_index}: {field} must be a valid YYYY-MM-DD date")
    except OSError as exc:
        errors.append(f"inbox.csv: {exc}")


def validate_schema_value(md_name: str, field: str, value: Any, spec: dict[str, Any], errors: list[str]) -> None:
    if is_empty(value):
        return
    field_type = spec.get("type")

    if field_type == "string":
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{md_name}: metadata '{field}' must be a non-empty string")
            return
        pattern = spec.get("pattern")
        if pattern and not re.fullmatch(str(pattern), value):
            errors.append(f"{md_name}: metadata '{field}' does not match required pattern")
    elif field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{md_name}: metadata '{field}' must be an integer")
            return
        if "min" in spec and value < int(spec["min"]):
            errors.append(f"{md_name}: metadata '{field}' must be >= {spec['min']}")
        if "max" in spec and value > int(spec["max"]):
            errors.append(f"{md_name}: metadata '{field}' must be <= {spec['max']}")
    elif field_type == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{md_name}: metadata '{field}' must be true or false")
    elif field_type == "list":
        values = as_list(value)
        if not isinstance(value, list):
            errors.append(f"{md_name}: metadata '{field}' must be a list")
            return
        if len(values) < int(spec.get("min_items", 0)):
            errors.append(f"{md_name}: metadata '{field}' must contain at least {spec['min_items']} item(s)")
        if spec.get("items", "string") == "string":
            bad = [item for item in values if not isinstance(item, str) or not item.strip()]
            if bad:
                errors.append(f"{md_name}: metadata '{field}' list items must be non-empty strings")
    elif field_type == "date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            errors.append(f"{md_name}: metadata '{field}' must be a YYYY-MM-DD date")
            return
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            errors.append(f"{md_name}: metadata '{field}' must be a valid calendar date")


def validate_report_schema(md_name: str, meta: dict[str, Any], schema: dict[str, Any], errors: list[str]) -> None:
    required = schema.get("required") if isinstance(schema.get("required"), list) else sorted(REQUIRED_META)
    fields = schema.get("fields") if isinstance(schema.get("fields"), dict) else DEFAULT_METADATA_SCHEMA["fields"]

    missing = sorted(key for key in required if key not in meta or is_empty(meta.get(key)))
    if missing:
        errors.append(f"{md_name}: missing required metadata: {', '.join(missing)}")

    for field, spec in fields.items():
        if field in meta and isinstance(spec, dict):
            validate_schema_value(md_name, field, meta[field], spec, errors)


def validate_reports(report_dir: Path, schema: dict[str, Any], errors: list[str], warnings: list[str]) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for md_path in paper_markdown_paths(report_dir):
        meta, body = strip_frontmatter(md_path.read_text(encoding="utf-8"))
        slug = str(meta.get("slug") or md_path.stem).strip()
        reports[slug] = meta

        if not meta:
            errors.append(f"{md_path.name}: missing YAML frontmatter")
            continue
        if slug != md_path.stem:
            errors.append(f"{md_path.name}: slug '{slug}' does not match filename")

        validate_report_schema(md_path.name, meta, schema, errors)

        if "## 10. 代码实现观察" in body and not bool(meta.get("has_code")):
            warnings.append(f"{md_path.name}: has code section but has_code is not true")

        html_path = md_path.with_suffix(".html")
        if not html_path.exists():
            errors.append(f"{md_path.name}: missing rendered HTML report {html_path.name}")

    return reports


def validate_json(report_dir: Path, reports: dict[str, dict[str, Any]], errors: list[str]) -> None:
    papers_path = report_dir / "papers.json"
    search_path = report_dir / "search_index.json"
    quality_path = report_dir / "quality.json"
    review_path = report_dir / "review.json"
    taxonomy_actions_path = report_dir / "taxonomy_actions.json"
    actions_path = report_dir / "actions.json"
    command_path = report_dir / "command.json"
    workflow_path = report_dir / "workflow.json"
    status_path = report_dir / "status.json"
    views_path = report_dir / "views.json"
    batch_path = report_dir / "batch.json"
    collections_path = report_dir / "collections.json"
    coverage_path = report_dir / "coverage.json"
    gaps_path = report_dir / "gaps.json"
    pivot_path = report_dir / "pivot.json"
    compare_path = report_dir / "compare.json"
    taxonomy_map_path = report_dir / "taxonomy_map.json"
    clusters_path = report_dir / "clusters.json"
    roadmap_path = report_dir / "roadmap.json"
    scale_path = report_dir / "scale.json"
    ownership_path = report_dir / "ownership.json"
    routing_path = report_dir / "routing.json"
    onboarding_path = report_dir / "onboarding.json"
    catalog_path = report_dir / "catalog.json"
    stats_path = report_dir / "stats.json"
    intake_path = report_dir / "intake.json"
    inbox_path = report_dir / "inbox.json"
    dedupe_path = report_dir / "dedupe.json"
    registry_path = report_dir / "registry.json"
    facets_path = report_dir / "facets.json"
    snapshot_path = report_dir / "snapshot.json"
    manifest_path = report_dir / "manifest.json"
    if not papers_path.exists():
        errors.append("missing papers.json")
        return
    if not search_path.exists():
        errors.append("missing search_index.json")
        return
    if not quality_path.exists():
        errors.append("missing quality.json")
        return
    if not review_path.exists():
        errors.append("missing review.json")
        return
    if not taxonomy_actions_path.exists():
        errors.append("missing taxonomy_actions.json")
        return
    if not actions_path.exists():
        errors.append("missing actions.json")
        return
    if not command_path.exists():
        errors.append("missing command.json")
        return
    if not workflow_path.exists():
        errors.append("missing workflow.json")
        return
    if not status_path.exists():
        errors.append("missing status.json")
        return
    if not views_path.exists():
        errors.append("missing views.json")
        return
    if not batch_path.exists():
        errors.append("missing batch.json")
        return
    if not collections_path.exists():
        errors.append("missing collections.json")
        return
    if not coverage_path.exists():
        errors.append("missing coverage.json")
        return
    if not gaps_path.exists():
        errors.append("missing gaps.json")
        return
    if not pivot_path.exists():
        errors.append("missing pivot.json")
        return
    if not compare_path.exists():
        errors.append("missing compare.json")
        return
    if not taxonomy_map_path.exists():
        errors.append("missing taxonomy_map.json")
        return
    if not clusters_path.exists():
        errors.append("missing clusters.json")
        return
    if not roadmap_path.exists():
        errors.append("missing roadmap.json")
        return
    if not scale_path.exists():
        errors.append("missing scale.json")
        return
    if not ownership_path.exists():
        errors.append("missing ownership.json")
        return
    if not routing_path.exists():
        errors.append("missing routing.json")
        return
    if not onboarding_path.exists():
        errors.append("missing onboarding.json")
        return
    if not catalog_path.exists():
        errors.append("missing catalog.json")
        return
    if not stats_path.exists():
        errors.append("missing stats.json")
        return
    if not intake_path.exists():
        errors.append("missing intake.json")
        return
    if not inbox_path.exists():
        errors.append("missing inbox.json")
        return
    if not dedupe_path.exists():
        errors.append("missing dedupe.json")
        return
    if not registry_path.exists():
        errors.append("missing registry.json")
        return
    if not facets_path.exists():
        errors.append("missing facets.json")
        return
    if not snapshot_path.exists():
        errors.append("missing snapshot.json")
        return
    if not manifest_path.exists():
        errors.append("missing manifest.json")
        return

    papers_data = json.loads(papers_path.read_text(encoding="utf-8"))
    search_data = json.loads(search_path.read_text(encoding="utf-8"))
    quality_data = json.loads(quality_path.read_text(encoding="utf-8"))
    review_data = json.loads(review_path.read_text(encoding="utf-8"))
    taxonomy_actions_data = json.loads(taxonomy_actions_path.read_text(encoding="utf-8"))
    actions_data = json.loads(actions_path.read_text(encoding="utf-8"))
    command_data = json.loads(command_path.read_text(encoding="utf-8"))
    workflow_data = json.loads(workflow_path.read_text(encoding="utf-8"))
    status_data = json.loads(status_path.read_text(encoding="utf-8"))
    views_data = json.loads(views_path.read_text(encoding="utf-8"))
    batch_data = json.loads(batch_path.read_text(encoding="utf-8"))
    collections_data = json.loads(collections_path.read_text(encoding="utf-8"))
    coverage_data = json.loads(coverage_path.read_text(encoding="utf-8"))
    gaps_data = json.loads(gaps_path.read_text(encoding="utf-8"))
    pivot_data = json.loads(pivot_path.read_text(encoding="utf-8"))
    compare_data = json.loads(compare_path.read_text(encoding="utf-8"))
    taxonomy_map_data = json.loads(taxonomy_map_path.read_text(encoding="utf-8"))
    clusters_data = json.loads(clusters_path.read_text(encoding="utf-8"))
    roadmap_data = json.loads(roadmap_path.read_text(encoding="utf-8"))
    scale_data = json.loads(scale_path.read_text(encoding="utf-8"))
    ownership_data = json.loads(ownership_path.read_text(encoding="utf-8"))
    routing_data = json.loads(routing_path.read_text(encoding="utf-8"))
    onboarding_data = json.loads(onboarding_path.read_text(encoding="utf-8"))
    catalog_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
    intake_data = json.loads(intake_path.read_text(encoding="utf-8"))
    inbox_data = json.loads(inbox_path.read_text(encoding="utf-8"))
    dedupe_data = json.loads(dedupe_path.read_text(encoding="utf-8"))
    registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
    facets_data = json.loads(facets_path.read_text(encoding="utf-8"))
    snapshot_data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    paper_slugs = {paper.get("slug") for paper in papers_data.get("papers", [])}
    report_slugs = set(reports)

    if papers_data.get("count") != len(report_slugs):
        errors.append(f"papers.json count {papers_data.get('count')} != markdown report count {len(report_slugs)}")
    if paper_slugs != report_slugs:
        errors.append(
            "papers.json slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - paper_slugs)}, extra={sorted(paper_slugs - report_slugs)}"
        )

    search_slugs = {paper.get("slug") for paper in search_data.get("papers", [])}
    if search_slugs != report_slugs:
        errors.append(
            "search_index.json slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - search_slugs)}, extra={sorted(search_slugs - report_slugs)}"
        )

    quality_queues = quality_data.get("queues") or {}
    quality_slugs = set()
    for value in quality_queues.values():
        if isinstance(value, list):
            quality_slugs.update(value)
    quality_issue_slugs = {issue.get("slug") for issue in quality_data.get("issues", [])}
    quality_drift_slugs = {item.get("slug") for item in quality_data.get("taxonomy_drift", [])}
    duplicate_reports = quality_data.get("duplicate_reports", [])
    if duplicate_reports is not None and not isinstance(duplicate_reports, list):
        errors.append("quality.json duplicate_reports must be a list")
        duplicate_reports = []
    quality_duplicate_slugs = {
        slug
        for item in duplicate_reports
        if isinstance(item, dict)
        for slug in item.get("slugs", [])
    }
    alias_suggestions = quality_data.get("label_alias_suggestions", [])
    if alias_suggestions is not None and not isinstance(alias_suggestions, list):
        errors.append("quality.json label_alias_suggestions must be a list")
        alias_suggestions = []
    quality_alias_slugs = {
        slug
        for item in alias_suggestions
        if isinstance(item, dict)
        for slug in item.get("slugs", [])
    }
    unknown_quality_slugs = sorted((quality_slugs | quality_issue_slugs | quality_drift_slugs | quality_alias_slugs | quality_duplicate_slugs) - report_slugs)
    if quality_data.get("count") != len(report_slugs):
        errors.append(f"quality.json count {quality_data.get('count')} != markdown report count {len(report_slugs)}")
    if unknown_quality_slugs:
        errors.append(f"quality.json references unknown slugs: {unknown_quality_slugs}")
    required_quality = {"quality_score", "coverage", "queues", "issues", "taxonomy_drift", "label_alias_suggestions", "duplicate_reports"}
    missing_quality = sorted(required_quality - set(quality_data))
    if missing_quality:
        errors.append(f"quality.json missing keys: {', '.join(missing_quality)}")
    if not isinstance(quality_data.get("taxonomy_drift"), list):
        errors.append("quality.json taxonomy_drift must be a list")

    review_item_slugs = {item.get("slug") for item in review_data.get("items", [])}
    review_queues = review_data.get("queues") or {}
    review_queue_slugs = set()
    for value in review_queues.values():
        if isinstance(value, list):
            review_queue_slugs.update(value)
    if review_data.get("count") != len(report_slugs):
        errors.append(f"review.json count {review_data.get('count')} != markdown report count {len(report_slugs)}")
    if review_item_slugs != report_slugs:
        errors.append(
            "review.json item slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - review_item_slugs)}, extra={sorted(review_item_slugs - report_slugs)}"
        )
    unknown_review_slugs = sorted(review_queue_slugs - report_slugs)
    if unknown_review_slugs:
        errors.append(f"review.json queues reference unknown slugs: {unknown_review_slugs}")
    required_review = {"queues", "items"}
    missing_review = sorted(required_review - set(review_data))
    if missing_review:
        errors.append(f"review.json missing keys: {', '.join(missing_review)}")

    taxonomy = papers_data.get("taxonomy") or {}
    required_taxonomy = {
        "domains",
        "tracks",
        "problems",
        "topics",
        "methods",
        "research_lines",
        "line_roles",
        "statuses",
        "reading_stages",
        "review_stages",
    }
    missing_taxonomy = sorted(required_taxonomy - set(taxonomy))
    if missing_taxonomy:
        errors.append(f"papers.json taxonomy missing keys: {', '.join(missing_taxonomy)}")

    required_controls = {"status", "reading_stage", "review_stage", "line_role", "shared_views"}
    papers_controls = papers_data.get("controls") or {}
    missing_controls = sorted(required_controls - set(papers_controls))
    if missing_controls:
        errors.append(f"papers.json controls missing keys: {', '.join(missing_controls)}")
    if not isinstance(papers_controls.get("shared_views"), list):
        errors.append("papers.json controls.shared_views must be a list")

    taxonomy_actions = taxonomy_actions_data.get("actions", [])
    if not isinstance(taxonomy_actions, list):
        errors.append("taxonomy_actions.json actions must be a list")
        taxonomy_actions = []
    action_slugs = {
        slug
        for item in taxonomy_actions
        if isinstance(item, dict)
        for slug in item.get("sample_slugs", [])
    }
    unknown_action_slugs = sorted(action_slugs - report_slugs)
    if taxonomy_actions_data.get("paper_count") != len(report_slugs):
        errors.append(f"taxonomy_actions.json paper_count {taxonomy_actions_data.get('paper_count')} != markdown report count {len(report_slugs)}")
    if taxonomy_actions_data.get("count") != len(taxonomy_actions):
        errors.append("taxonomy_actions.json count must match actions length")
    if unknown_action_slugs:
        errors.append(f"taxonomy_actions.json references unknown sample slugs: {unknown_action_slugs}")
    required_taxonomy_actions = {"count", "paper_count", "summary", "actions"}
    missing_taxonomy_actions = sorted(required_taxonomy_actions - set(taxonomy_actions_data))
    if missing_taxonomy_actions:
        errors.append(f"taxonomy_actions.json missing keys: {', '.join(missing_taxonomy_actions)}")

    action_items = actions_data.get("actions", [])
    if not isinstance(action_items, list):
        errors.append("actions.json actions must be a list")
        action_items = []
    if actions_data.get("count") != len(action_items):
        errors.append("actions.json count must match actions length")
    missing_actions = sorted({"summary", "actions", "csv_columns", "commands", "links"} - set(actions_data))
    if missing_actions:
        errors.append(f"actions.json missing keys: {', '.join(missing_actions)}")
    action_summary = actions_data.get("summary")
    if not isinstance(action_summary, dict):
        errors.append("actions.json summary must be an object")
    else:
        if not isinstance(action_summary.get("groups"), dict):
            errors.append("actions.json summary.groups must be an object")
        if not isinstance(action_summary.get("severity"), dict):
            errors.append("actions.json summary.severity must be an object")
    valid_action_groups = {"review", "freshness", "metadata", "quality", "taxonomy", "dedupe", "inbox"}
    valid_action_severities = {"high", "medium", "low", "none"}
    action_ids: set[str] = set()
    for index, item in enumerate(action_items):
        if not isinstance(item, dict):
            errors.append(f"actions.json actions[{index}] must be an object")
            continue
        for key in ("id", "group", "severity", "priority", "title", "detail", "href", "source", "slugs", "command"):
            if key not in item:
                errors.append(f"actions.json actions[{index}] missing {key}")
        action_id = str(item.get("id") or "")
        if action_id in action_ids:
            errors.append(f"actions.json actions[{index}] has duplicate id {action_id!r}")
        action_ids.add(action_id)
        if item.get("group") not in valid_action_groups:
            errors.append(f"actions.json actions[{index}] has invalid group")
        if item.get("severity") not in valid_action_severities:
            errors.append(f"actions.json actions[{index}] has invalid severity")
        if not isinstance(item.get("priority"), int) or isinstance(item.get("priority"), bool):
            errors.append(f"actions.json actions[{index}].priority must be an integer")
        if not isinstance(item.get("slugs"), list):
            errors.append(f"actions.json actions[{index}].slugs must be a list")
        else:
            unknown_slugs = sorted(str(slug) for slug in item.get("slugs", []) if str(slug) not in report_slugs)
            if unknown_slugs:
                errors.append(f"actions.json actions[{index}] references unknown slugs: {unknown_slugs}")
    action_columns = actions_data.get("csv_columns")
    if not isinstance(action_columns, list) or not {"id", "group", "severity", "priority", "title", "source", "slugs", "command"}.issubset(set(action_columns)):
        errors.append("actions.json csv_columns must include id, group, severity, priority, title, source, slugs, and command")
    if not isinstance(actions_data.get("commands"), list) or not any("export_actions.py" in str(command) for command in actions_data.get("commands", [])):
        errors.append("actions.json commands must include export_actions.py")
    action_links = actions_data.get("links")
    if not isinstance(action_links, dict) or not {"html", "library", "quality", "review", "taxonomy", "facets", "inbox", "dedupe", "command"}.issubset(action_links):
        errors.append("actions.json links must include html, library, quality, review, taxonomy, facets, inbox, dedupe, and command")

    if command_data.get("count") != len(report_slugs):
        errors.append(f"command.json count {command_data.get('count')} != markdown report count {len(report_slugs)}")
    required_command = {"lane_count", "lanes", "summary", "recommended_next", "links"}
    missing_command = sorted(required_command - set(command_data))
    if missing_command:
        errors.append(f"command.json missing keys: {', '.join(missing_command)}")
    command_lanes = command_data.get("lanes")
    if not isinstance(command_lanes, list):
        errors.append("command.json lanes must be a list")
        command_lanes = []
    elif command_data.get("lane_count") != len(command_lanes):
        errors.append("command.json lane_count must match lanes length")
    for index, lane in enumerate(command_lanes):
        if not isinstance(lane, dict):
            errors.append(f"command.json lanes[{index}] must be an object")
            continue
        for key in ("id", "title", "primary_href", "pages", "data_files", "commands", "metrics", "next_actions"):
            if key not in lane:
                errors.append(f"command.json lanes[{index}] missing {key}")
        if not isinstance(lane.get("pages"), list):
            errors.append(f"command.json lanes[{index}].pages must be a list")
        if not isinstance(lane.get("data_files"), list):
            errors.append(f"command.json lanes[{index}].data_files must be a list")
        if not isinstance(lane.get("commands"), list):
            errors.append(f"command.json lanes[{index}].commands must be a list")
    if not isinstance(command_data.get("recommended_next"), list):
        errors.append("command.json recommended_next must be a list")

    if workflow_data.get("count") != len(report_slugs):
        errors.append(f"workflow.json count {workflow_data.get('count')} != markdown report count {len(report_slugs)}")
    required_workflow = {
        "active_status_workflow",
        "workflow_count",
        "workflows",
        "active_unconfigured",
        "shared_workflow_views",
        "recommendations",
        "commands",
    }
    missing_workflow = sorted(required_workflow - set(workflow_data))
    if missing_workflow:
        errors.append(f"workflow.json missing keys: {', '.join(missing_workflow)}")
    workflow_items = workflow_data.get("workflows")
    if not isinstance(workflow_items, list):
        errors.append("workflow.json workflows must be a list")
        workflow_items = []
    elif workflow_data.get("workflow_count") != len(workflow_items):
        errors.append("workflow.json workflow_count must match workflows length")
    if workflow_items and not any(isinstance(item, dict) and item.get("active") is True for item in workflow_items):
        errors.append("workflow.json workflows must include one active workflow")
    for index, workflow in enumerate(workflow_items):
        if not isinstance(workflow, dict):
            errors.append(f"workflow.json workflows[{index}] must be an object")
            continue
        for key in ("name", "status_values", "reading_stage_values", "review_stage_values", "fields"):
            if key not in workflow:
                errors.append(f"workflow.json workflows[{index}] missing {key}")
        fields = workflow.get("fields") or {}
        if not isinstance(fields, dict):
            errors.append(f"workflow.json workflows[{index}].fields must be an object")
            continue
        for field in ("status", "reading_stage", "review_stage"):
            field_data = fields.get(field)
            if not isinstance(field_data, dict):
                errors.append(f"workflow.json workflows[{index}].fields.{field} must be an object")
                continue
            if not isinstance(field_data.get("values"), list):
                errors.append(f"workflow.json workflows[{index}].fields.{field}.values must be a list")
            if not isinstance(field_data.get("unconfigured"), list):
                errors.append(f"workflow.json workflows[{index}].fields.{field}.unconfigured must be a list")
    if not isinstance(workflow_data.get("active_unconfigured"), list):
        errors.append("workflow.json active_unconfigured must be a list")
    if not isinstance(workflow_data.get("shared_workflow_views"), list):
        errors.append("workflow.json shared_workflow_views must be a list")

    if status_data.get("count") != len(report_slugs):
        errors.append(f"status.json count {status_data.get('count')} != markdown report count {len(report_slugs)}")
    required_status = {"active_status_workflow", "workflow_count", "workflows", "papers", "defaults", "links", "commands"}
    missing_status = sorted(required_status - set(status_data))
    if missing_status:
        errors.append(f"status.json missing keys: {', '.join(missing_status)}")
    status_workflows = status_data.get("workflows")
    if not isinstance(status_workflows, list):
        errors.append("status.json workflows must be a list")
        status_workflows = []
    elif status_data.get("workflow_count") != len(status_workflows):
        errors.append("status.json workflow_count must match workflows length")
    status_papers = status_data.get("papers")
    if not isinstance(status_papers, list):
        errors.append("status.json papers must be a list")
        status_papers = []
    status_slugs = {item.get("slug") for item in status_papers if isinstance(item, dict)}
    if status_slugs != report_slugs:
        errors.append(
            "status.json paper slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - status_slugs)}, extra={sorted(status_slugs - report_slugs)}"
        )
    defaults = status_data.get("defaults")
    if not isinstance(defaults, dict) or "workflow" not in defaults:
        errors.append("status.json defaults must include workflow")
    status_links = status_data.get("links")
    if not isinstance(status_links, dict) or not {"library", "board", "workflow"}.issubset(status_links):
        errors.append("status.json links must include library, board, and workflow")
    if not isinstance(status_data.get("commands"), list):
        errors.append("status.json commands must be a list")

    if views_data.get("count") != len(report_slugs):
        errors.append(f"views.json count {views_data.get('count')} != markdown report count {len(report_slugs)}")
    required_views = {"view_count", "configured_count", "system_count", "generated_count", "source_counts", "kind_counts", "empty_view_count", "views", "recommendations", "commands", "links"}
    missing_views = sorted(required_views - set(views_data))
    if missing_views:
        errors.append(f"views.json missing keys: {', '.join(missing_views)}")
    view_items = views_data.get("views")
    if not isinstance(view_items, list):
        errors.append("views.json views must be a list")
        view_items = []
    elif views_data.get("view_count") != len(view_items):
        errors.append("views.json view_count must match views length")
    valid_view_sources = {"configured", "system", "generated"}
    valid_view_kinds = {"shared", "queue", "research_line", "workflow_status"}
    view_ids: set[str] = set()
    for index, item in enumerate(view_items):
        if not isinstance(item, dict):
            errors.append(f"views.json views[{index}] must be an object")
            continue
        for key in ("id", "name", "source", "kind", "page", "target_page", "href", "state", "count", "slugs", "sample_papers", "shared_view", "empty"):
            if key not in item:
                errors.append(f"views.json views[{index}] missing {key}")
        if item.get("source") not in valid_view_sources:
            errors.append(f"views.json views[{index}] has invalid source")
        if item.get("kind") not in valid_view_kinds:
            errors.append(f"views.json views[{index}] has invalid kind")
        view_id = str(item.get("id") or "")
        if view_id in view_ids:
            errors.append(f"views.json duplicate view id: {view_id}")
        if view_id:
            view_ids.add(view_id)
        if not isinstance(item.get("state"), dict):
            errors.append(f"views.json views[{index}].state must be an object")
        if not isinstance(item.get("shared_view"), dict):
            errors.append(f"views.json views[{index}].shared_view must be an object")
        slugs = item.get("slugs")
        if not isinstance(slugs, list):
            errors.append(f"views.json views[{index}].slugs must be a list")
        else:
            unknown_view_slugs = sorted(str(slug) for slug in slugs if str(slug) not in report_slugs)
            if unknown_view_slugs:
                errors.append(f"views.json views[{index}] references unknown slugs: {unknown_view_slugs}")
            if isinstance(item.get("count"), int) and item.get("count") != len(slugs):
                errors.append(f"views.json views[{index}].count must match slugs length")
        sample_papers = item.get("sample_papers")
        if not isinstance(sample_papers, list):
            errors.append(f"views.json views[{index}].sample_papers must be a list")
        else:
            sample_slugs = sorted(str(paper.get("slug") or "") for paper in sample_papers if isinstance(paper, dict))
            unknown_sample_slugs = [slug for slug in sample_slugs if slug and slug not in report_slugs]
            if unknown_sample_slugs:
                errors.append(f"views.json views[{index}] references unknown sample paper slugs: {unknown_sample_slugs}")
    if not isinstance(views_data.get("recommendations"), list):
        errors.append("views.json recommendations must be a list")
    if not isinstance(views_data.get("commands"), list):
        errors.append("views.json commands must be a list")
    view_links = views_data.get("links")
    if not isinstance(view_links, dict) or not {"html", "index", "library", "collections", "status", "workflow", "quality"}.issubset(view_links):
        errors.append("views.json links missing required entries")

    if batch_data.get("count") != len(report_slugs):
        errors.append(f"batch.json count {batch_data.get('count')} != markdown report count {len(report_slugs)}")
    required_batch = {"dimension_count", "batch_count", "dimensions", "summary", "batches", "top_batches", "links"}
    missing_batch = sorted(required_batch - set(batch_data))
    if missing_batch:
        errors.append(f"batch.json missing keys: {', '.join(missing_batch)}")
    batch_dimensions = batch_data.get("dimensions")
    if not isinstance(batch_dimensions, list) or not batch_dimensions:
        errors.append("batch.json dimensions must be a non-empty list")
        batch_dimension_keys = set()
    else:
        batch_dimension_keys = {str(item.get("key") or "") for item in batch_dimensions if isinstance(item, dict)}
        if batch_data.get("dimension_count") != len(batch_dimensions):
            errors.append("batch.json dimension_count must match dimensions length")
        for index, item in enumerate(batch_dimensions):
            if not isinstance(item, dict):
                errors.append(f"batch.json dimensions[{index}] must be an object")
                continue
            for key in ("key", "label", "query", "multi", "paper_key"):
                if key not in item:
                    errors.append(f"batch.json dimensions[{index}] missing {key}")
            if not isinstance(item.get("multi"), bool):
                errors.append(f"batch.json dimensions[{index}].multi must be boolean")
    batch_items = batch_data.get("batches")
    if not isinstance(batch_items, list):
        errors.append("batch.json batches must be a list")
        batch_items = []
    elif batch_data.get("batch_count") != len(batch_items):
        errors.append("batch.json batch_count must match batches length")
    valid_batch_severities = {"high", "medium", "low"}
    for index, item in enumerate(batch_items):
        if not isinstance(item, dict):
            errors.append(f"batch.json batches[{index}] must be an object")
            continue
        for key in ("id", "dimension", "value", "count", "severity", "priority", "recommended_action", "href", "export_command", "slugs", "sample_slugs"):
            if key not in item:
                errors.append(f"batch.json batches[{index}] missing {key}")
        if item.get("severity") not in valid_batch_severities:
            errors.append(f"batch.json batches[{index}] has invalid severity")
        if str(item.get("dimension") or "") not in batch_dimension_keys:
            errors.append(f"batch.json batches[{index}] references unknown dimension")
        if not isinstance(item.get("slugs"), list):
            errors.append(f"batch.json batches[{index}].slugs must be a list")
        else:
            unknown_slugs = sorted(str(slug) for slug in item.get("slugs", []) if str(slug) not in report_slugs)
            if unknown_slugs:
                errors.append(f"batch.json batches[{index}] references unknown slugs: {unknown_slugs}")
        if not isinstance(item.get("sample_slugs"), list):
            errors.append(f"batch.json batches[{index}].sample_slugs must be a list")
        else:
            unknown_slugs = sorted(str(slug) for slug in item.get("sample_slugs", []) if str(slug) not in report_slugs)
            if unknown_slugs:
                errors.append(f"batch.json batches[{index}] references unknown sample slugs: {unknown_slugs}")
    top_batches = batch_data.get("top_batches")
    if not isinstance(top_batches, list):
        errors.append("batch.json top_batches must be a list")
        top_batches = []
    for index, item in enumerate(top_batches):
        if not isinstance(item, dict):
            errors.append(f"batch.json top_batches[{index}] must be an object")
            continue
        unknown_slugs = sorted(str(slug) for slug in item.get("slugs", []) if str(slug) not in report_slugs)
        if unknown_slugs:
            errors.append(f"batch.json top_batches[{index}] references unknown slugs: {unknown_slugs}")
    batch_links = batch_data.get("links")
    if not isinstance(batch_links, dict) or not {"library", "actions", "review", "facets"}.issubset(batch_links):
        errors.append("batch.json links must include library, actions, review, and facets")

    if collections_data.get("count") != len(report_slugs):
        errors.append(f"collections.json count {collections_data.get('count')} != markdown report count {len(report_slugs)}")
    missing_collections = sorted({"shared_views", "smart_collections", "research_lines", "links"} - set(collections_data))
    if missing_collections:
        errors.append(f"collections.json missing keys: {', '.join(missing_collections)}")
    for group_key, count_key in (
        ("shared_views", "shared_view_count"),
        ("smart_collections", "smart_collection_count"),
        ("research_lines", "research_line_count"),
    ):
        group_items = collections_data.get(group_key)
        if not isinstance(group_items, list):
            errors.append(f"collections.json {group_key} must be a list")
            continue
        if collections_data.get(count_key) != len(group_items):
            errors.append(f"collections.json {count_key} must match {group_key} length")
        for index, item in enumerate(group_items):
            if not isinstance(item, dict):
                errors.append(f"collections.json {group_key}[{index}] must be an object")
                continue
            slugs = item.get("slugs")
            if not isinstance(slugs, list):
                errors.append(f"collections.json {group_key}[{index}].slugs must be a list")
                continue
            unknown_slugs = sorted(str(slug) for slug in slugs if str(slug) not in report_slugs)
            if unknown_slugs:
                errors.append(f"collections.json {group_key}[{index}] references unknown slugs: {unknown_slugs}")
            sample_papers = item.get("sample_papers", [])
            if not isinstance(sample_papers, list):
                errors.append(f"collections.json {group_key}[{index}].sample_papers must be a list")
                continue
            sample_slugs = sorted(str(paper.get("slug") or "") for paper in sample_papers if isinstance(paper, dict))
            unknown_sample_slugs = [slug for slug in sample_slugs if slug and slug not in report_slugs]
            if unknown_sample_slugs:
                errors.append(f"collections.json {group_key}[{index}] references unknown sample paper slugs: {unknown_sample_slugs}")

    if coverage_data.get("count") != len(report_slugs):
        errors.append(f"coverage.json count {coverage_data.get('count')} != markdown report count {len(report_slugs)}")
    required_coverage = {"line_count", "field_count", "avg_score", "risk_counts", "weak_line_count", "total_missing", "fields", "coverage", "links"}
    missing_coverage = sorted(required_coverage - set(coverage_data))
    if missing_coverage:
        errors.append(f"coverage.json missing keys: {', '.join(missing_coverage)}")
    coverage_fields = coverage_data.get("fields")
    if not isinstance(coverage_fields, list) or not coverage_fields:
        errors.append("coverage.json fields must be a non-empty list")
        coverage_field_names = set()
    else:
        if coverage_data.get("field_count") != len(coverage_fields):
            errors.append("coverage.json field_count must match fields length")
        coverage_field_names = {str(field.get("field") or "") for field in coverage_fields if isinstance(field, dict)}
        for index, field in enumerate(coverage_fields):
            if not isinstance(field, dict):
                errors.append(f"coverage.json fields[{index}] must be an object")
                continue
            for key in ("field", "label", "query_key", "multi"):
                if key not in field:
                    errors.append(f"coverage.json fields[{index}] missing {key}")
    coverage_rows = coverage_data.get("coverage")
    if not isinstance(coverage_rows, list):
        errors.append("coverage.json coverage must be a list")
        coverage_rows = []
    elif coverage_data.get("line_count") != len(coverage_rows):
        errors.append("coverage.json line_count must match coverage length")
    valid_coverage_risks = {"high", "medium", "low"}
    for index, row in enumerate(coverage_rows):
        if not isinstance(row, dict):
            errors.append(f"coverage.json coverage[{index}] must be an object")
            continue
        for key in ("line", "href", "count", "score", "risk", "missing_total", "fields"):
            if key not in row:
                errors.append(f"coverage.json coverage[{index}] missing {key}")
        if row.get("risk") not in valid_coverage_risks:
            errors.append(f"coverage.json coverage[{index}].risk has invalid value")
        if not isinstance(row.get("fields"), list):
            errors.append(f"coverage.json coverage[{index}].fields must be a list")
            continue
        row_field_names = {str(field.get("field") or "") for field in row.get("fields", []) if isinstance(field, dict)}
        if coverage_field_names and row_field_names != coverage_field_names:
            errors.append(f"coverage.json coverage[{index}].fields must match fields contract")
        for field_index, field in enumerate(row.get("fields", [])):
            if not isinstance(field, dict):
                errors.append(f"coverage.json coverage[{index}].fields[{field_index}] must be an object")
                continue
            for key in ("field", "label", "query_key", "coverage", "missing", "missing_slugs", "unique", "top_values"):
                if key not in field:
                    errors.append(f"coverage.json coverage[{index}].fields[{field_index}] missing {key}")
            if not isinstance(field.get("missing_slugs"), list):
                errors.append(f"coverage.json coverage[{index}].fields[{field_index}].missing_slugs must be a list")
            else:
                unknown_missing_slugs = sorted(str(slug) for slug in field.get("missing_slugs", []) if str(slug) not in report_slugs)
                if unknown_missing_slugs:
                    errors.append(f"coverage.json coverage[{index}].fields[{field_index}] references unknown missing slugs: {unknown_missing_slugs}")
            if not isinstance(field.get("top_values"), list):
                errors.append(f"coverage.json coverage[{index}].fields[{field_index}].top_values must be a list")
    coverage_links = coverage_data.get("links")
    if not isinstance(coverage_links, dict) or not {"html", "library", "balance", "facets", "quality", "lines"}.issubset(coverage_links):
        errors.append("coverage.json links must include html, library, balance, facets, quality, and lines")

    if gaps_data.get("count") != len(report_slugs):
        errors.append(f"gaps.json count {gaps_data.get('count')} != markdown report count {len(report_slugs)}")
    required_gaps = {"line_count", "action_count", "recommended_roles", "summary", "lines", "actions", "queues", "links"}
    missing_gaps = sorted(required_gaps - set(gaps_data))
    if missing_gaps:
        errors.append(f"gaps.json missing keys: {', '.join(missing_gaps)}")
    gap_lines = gaps_data.get("lines")
    if not isinstance(gap_lines, list):
        errors.append("gaps.json lines must be a list")
        gap_lines = []
    elif gaps_data.get("line_count") != len(gap_lines):
        errors.append("gaps.json line_count must match lines length")
    for index, line in enumerate(gap_lines):
        if not isinstance(line, dict):
            errors.append(f"gaps.json lines[{index}] must be an object")
            continue
        for key in ("id", "line", "href", "count", "score", "missing_roles", "missing_taxonomy_slugs", "taxonomy_load_slugs", "no_review_slugs", "no_code_slugs", "actions"):
            if key not in line:
                errors.append(f"gaps.json lines[{index}] missing {key}")
        for key in ("missing_taxonomy_slugs", "taxonomy_load_slugs", "no_review_slugs", "no_code_slugs"):
            slugs = line.get(key)
            if not isinstance(slugs, list):
                errors.append(f"gaps.json lines[{index}].{key} must be a list")
                continue
            unknown_gap_slugs = sorted(str(slug) for slug in slugs if str(slug) not in report_slugs)
            if unknown_gap_slugs:
                errors.append(f"gaps.json lines[{index}].{key} references unknown slugs: {unknown_gap_slugs}")
        if not isinstance(line.get("actions"), list):
            errors.append(f"gaps.json lines[{index}].actions must be a list")
    gap_actions = gaps_data.get("actions")
    if not isinstance(gap_actions, list):
        errors.append("gaps.json actions must be a list")
        gap_actions = []
    elif gaps_data.get("action_count") != len(gap_actions):
        errors.append("gaps.json action_count must match actions length")
    for index, action in enumerate(gap_actions):
        if not isinstance(action, dict):
            errors.append(f"gaps.json actions[{index}] must be an object")
            continue
        for key in ("line", "priority", "type", "label", "href", "slugs"):
            if key not in action:
                errors.append(f"gaps.json actions[{index}] missing {key}")
        slugs = action.get("slugs")
        if not isinstance(slugs, list):
            errors.append(f"gaps.json actions[{index}].slugs must be a list")
        else:
            unknown_action_slugs = sorted(str(slug) for slug in slugs if str(slug) not in report_slugs)
            if unknown_action_slugs:
                errors.append(f"gaps.json actions[{index}] references unknown slugs: {unknown_action_slugs}")
    gap_queues = gaps_data.get("queues")
    if not isinstance(gap_queues, dict):
        errors.append("gaps.json queues must be an object")
    else:
        for key, items in gap_queues.items():
            if not isinstance(items, list):
                errors.append(f"gaps.json queues.{key} must be a list")
                continue
            queue_slugs = {str(item.get("slug") or "") for item in items if isinstance(item, dict)}
            unknown_queue_slugs = sorted(slug for slug in queue_slugs if slug and slug not in report_slugs)
            if unknown_queue_slugs:
                errors.append(f"gaps.json queues.{key} references unknown slugs: {unknown_queue_slugs}")
    gap_links = gaps_data.get("links")
    if not isinstance(gap_links, dict) or not {"html", "dashboard", "collections", "related", "library", "matrix", "timeline", "taxonomy", "review"}.issubset(gap_links):
        errors.append("gaps.json links missing required entries")

    if pivot_data.get("count") != len(report_slugs):
        errors.append(f"pivot.json count {pivot_data.get('count')} != markdown report count {len(report_slugs)}")
    required_pivot = {"dimensions", "papers", "presets"}
    missing_pivot = sorted(required_pivot - set(pivot_data))
    if missing_pivot:
        errors.append(f"pivot.json missing keys: {', '.join(missing_pivot)}")
    pivot_dimensions = pivot_data.get("dimensions")
    if not isinstance(pivot_dimensions, list) or not pivot_dimensions:
        errors.append("pivot.json dimensions must be a non-empty list")
    else:
        dimension_keys = {str(item.get("key") or "") for item in pivot_dimensions if isinstance(item, dict)}
        for key in ("research_line", "domain", "track", "problem", "topic", "method", "status", "year"):
            if key not in dimension_keys:
                errors.append(f"pivot.json dimensions missing {key}")
    pivot_papers = pivot_data.get("papers")
    if not isinstance(pivot_papers, list):
        errors.append("pivot.json papers must be a list")
        pivot_papers = []
    pivot_slugs = {item.get("slug") for item in pivot_papers if isinstance(item, dict)}
    if pivot_slugs != report_slugs:
        errors.append(
            "pivot.json paper slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - pivot_slugs)}, extra={sorted(pivot_slugs - report_slugs)}"
        )
    for index, item in enumerate(pivot_papers):
        if not isinstance(item, dict):
            errors.append(f"pivot.json papers[{index}] must be an object")
            continue
        if not isinstance(item.get("dimensions"), dict):
            errors.append(f"pivot.json papers[{index}].dimensions must be an object")
    pivot_presets = pivot_data.get("presets")
    if not isinstance(pivot_presets, list):
        errors.append("pivot.json presets must be a list")
        pivot_presets = []
    for index, preset in enumerate(pivot_presets):
        if not isinstance(preset, dict):
            errors.append(f"pivot.json presets[{index}] must be an object")
            continue
        for key in ("row_dimension", "column_dimension", "rows", "columns", "cells"):
            if key not in preset:
                errors.append(f"pivot.json presets[{index}] missing {key}")
        cells = preset.get("cells", [])
        if not isinstance(cells, list):
            errors.append(f"pivot.json presets[{index}].cells must be a list")
            cells = []
        cell_slugs = {
            slug
            for cell in cells
            if isinstance(cell, dict)
            for slug in cell.get("slugs", [])
        }
        unknown_cell_slugs = sorted(cell_slugs - report_slugs)
        if unknown_cell_slugs:
            errors.append(f"pivot.json presets[{index}] references unknown slugs: {unknown_cell_slugs}")

    if compare_data.get("count") != len(report_slugs):
        errors.append(f"compare.json count {compare_data.get('count')} != markdown report count {len(report_slugs)}")
    required_compare = {"fields", "papers", "suggested_sets"}
    missing_compare = sorted(required_compare - set(compare_data))
    if missing_compare:
        errors.append(f"compare.json missing keys: {', '.join(missing_compare)}")
    compare_fields = compare_data.get("fields")
    if not isinstance(compare_fields, list) or not compare_fields:
        errors.append("compare.json fields must be a non-empty list")
    else:
        field_keys = {str(item.get("key") or "") for item in compare_fields if isinstance(item, dict)}
        for key in ("title_zh", "research_line", "topics", "methods", "status", "importance", "has_code"):
            if key not in field_keys:
                errors.append(f"compare.json fields missing {key}")
    compare_papers = compare_data.get("papers")
    if not isinstance(compare_papers, list):
        errors.append("compare.json papers must be a list")
        compare_papers = []
    compare_slugs = {item.get("slug") for item in compare_papers if isinstance(item, dict)}
    if compare_slugs != report_slugs:
        errors.append(
            "compare.json paper slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - compare_slugs)}, extra={sorted(compare_slugs - report_slugs)}"
        )
    compare_sets = compare_data.get("suggested_sets")
    if not isinstance(compare_sets, list):
        errors.append("compare.json suggested_sets must be a list")
        compare_sets = []
    for index, item in enumerate(compare_sets):
        if not isinstance(item, dict):
            errors.append(f"compare.json suggested_sets[{index}] must be an object")
            continue
        slugs = item.get("slugs", [])
        if not isinstance(slugs, list):
            errors.append(f"compare.json suggested_sets[{index}].slugs must be a list")
            continue
        unknown_set_slugs = sorted(set(slugs) - report_slugs)
        if unknown_set_slugs:
            errors.append(f"compare.json suggested_sets[{index}] references unknown slugs: {unknown_set_slugs}")

    if taxonomy_map_data.get("count") != len(report_slugs):
        errors.append(f"taxonomy_map.json count {taxonomy_map_data.get('count')} != markdown report count {len(report_slugs)}")
    required_map = {"field_order", "edge_specs", "nodes", "edges", "clusters", "isolated_nodes", "recommendations", "slug_titles"}
    missing_map = sorted(required_map - set(taxonomy_map_data))
    if missing_map:
        errors.append(f"taxonomy_map.json missing keys: {', '.join(missing_map)}")
    map_nodes = taxonomy_map_data.get("nodes")
    if not isinstance(map_nodes, list) or not map_nodes:
        errors.append("taxonomy_map.json nodes must be a non-empty list")
        map_nodes = []
    node_ids = {str(node.get("id") or "") for node in map_nodes if isinstance(node, dict)}
    for index, node in enumerate(map_nodes):
        if not isinstance(node, dict):
            errors.append(f"taxonomy_map.json nodes[{index}] must be an object")
            continue
        for key in ("id", "field", "value", "count", "href", "sample_slugs"):
            if key not in node:
                errors.append(f"taxonomy_map.json nodes[{index}] missing {key}")
        sample_slugs = node.get("sample_slugs", [])
        if not isinstance(sample_slugs, list):
            errors.append(f"taxonomy_map.json nodes[{index}].sample_slugs must be a list")
            sample_slugs = []
        unknown_node_slugs = sorted(set(sample_slugs) - report_slugs)
        if unknown_node_slugs:
            errors.append(f"taxonomy_map.json nodes[{index}] references unknown slugs: {unknown_node_slugs}")
    map_edges = taxonomy_map_data.get("edges")
    if not isinstance(map_edges, list):
        errors.append("taxonomy_map.json edges must be a list")
        map_edges = []
    for index, edge in enumerate(map_edges):
        if not isinstance(edge, dict):
            errors.append(f"taxonomy_map.json edges[{index}] must be an object")
            continue
        for key in ("source", "target", "source_field", "target_field", "count", "href", "sample_slugs"):
            if key not in edge:
                errors.append(f"taxonomy_map.json edges[{index}] missing {key}")
        if edge.get("source") not in node_ids:
            errors.append(f"taxonomy_map.json edges[{index}] references unknown source node")
        if edge.get("target") not in node_ids:
            errors.append(f"taxonomy_map.json edges[{index}] references unknown target node")
        sample_slugs = edge.get("sample_slugs", [])
        if not isinstance(sample_slugs, list):
            errors.append(f"taxonomy_map.json edges[{index}].sample_slugs must be a list")
            sample_slugs = []
        unknown_edge_slugs = sorted(set(sample_slugs) - report_slugs)
        if unknown_edge_slugs:
            errors.append(f"taxonomy_map.json edges[{index}] references unknown slugs: {unknown_edge_slugs}")
    if not isinstance(taxonomy_map_data.get("clusters"), list):
        errors.append("taxonomy_map.json clusters must be a list")
    if not isinstance(taxonomy_map_data.get("recommendations"), list):
        errors.append("taxonomy_map.json recommendations must be a list")

    if clusters_data.get("count") != len(report_slugs):
        errors.append(f"clusters.json count {clusters_data.get('count')} != markdown report count {len(report_slugs)}")
    required_clusters = {"cluster_count", "largest_cluster_share", "clusters", "recommendations", "links"}
    missing_clusters = sorted(required_clusters - set(clusters_data))
    if missing_clusters:
        errors.append(f"clusters.json missing keys: {', '.join(missing_clusters)}")
    cluster_items = clusters_data.get("clusters")
    if not isinstance(cluster_items, list):
        errors.append("clusters.json clusters must be a list")
        cluster_items = []
    if clusters_data.get("cluster_count") != len(cluster_items):
        errors.append("clusters.json cluster_count must match clusters length")
    valid_cluster_risks = {"high", "medium", "low"}
    for index, cluster in enumerate(cluster_items):
        if not isinstance(cluster, dict):
            errors.append(f"clusters.json clusters[{index}] must be an object")
            continue
        for key in ("id", "name", "href", "count", "share", "risk", "top_labels", "representative_slugs"):
            if key not in cluster:
                errors.append(f"clusters.json clusters[{index}] missing {key}")
        if cluster.get("risk") not in valid_cluster_risks:
            errors.append(f"clusters.json clusters[{index}].risk has invalid value")
        if not isinstance(cluster.get("top_labels"), dict):
            errors.append(f"clusters.json clusters[{index}].top_labels must be an object")
        representative_slugs = cluster.get("representative_slugs", [])
        if not isinstance(representative_slugs, list):
            errors.append(f"clusters.json clusters[{index}].representative_slugs must be a list")
            representative_slugs = []
        unknown_cluster_slugs = sorted(set(representative_slugs) - report_slugs)
        if unknown_cluster_slugs:
            errors.append(f"clusters.json clusters[{index}] references unknown slugs: {unknown_cluster_slugs}")
        split_candidates = cluster.get("split_candidates", [])
        if not isinstance(split_candidates, list):
            errors.append(f"clusters.json clusters[{index}].split_candidates must be a list")
    if not isinstance(clusters_data.get("recommendations"), list):
        errors.append("clusters.json recommendations must be a list")

    if roadmap_data.get("count") != len(report_slugs):
        errors.append(f"roadmap.json count {roadmap_data.get('count')} != markdown report count {len(report_slugs)}")
    required_roadmap = {"line_count", "risk_counts", "recommended_roles", "roadmaps", "actions", "links"}
    missing_roadmap = sorted(required_roadmap - set(roadmap_data))
    if missing_roadmap:
        errors.append(f"roadmap.json missing keys: {', '.join(missing_roadmap)}")
    roadmap_items = roadmap_data.get("roadmaps")
    if not isinstance(roadmap_items, list):
        errors.append("roadmap.json roadmaps must be a list")
        roadmap_items = []
    if roadmap_data.get("line_count") != len(roadmap_items):
        errors.append("roadmap.json line_count must match roadmaps length")
    roadmap_action_types = {"role_gap", "year_gap", "freshness_gap", "review_plan", "metadata_gap", "taxonomy_load", "code_observation", "maintain"}
    valid_risks = {"high", "medium", "low"}
    for index, item in enumerate(roadmap_items):
        if not isinstance(item, dict):
            errors.append(f"roadmap.json roadmaps[{index}] must be an object")
            continue
        for key in ("id", "line", "href", "count", "risk", "score", "role_counts", "missing_roles", "milestones", "representative_papers", "queues", "actions"):
            if key not in item:
                errors.append(f"roadmap.json roadmaps[{index}] missing {key}")
        if item.get("risk") not in valid_risks:
            errors.append(f"roadmap.json roadmaps[{index}].risk has invalid value")
        if not isinstance(item.get("role_counts"), dict):
            errors.append(f"roadmap.json roadmaps[{index}].role_counts must be an object")
        if not isinstance(item.get("missing_roles"), list):
            errors.append(f"roadmap.json roadmaps[{index}].missing_roles must be a list")
        representative_slugs = [
            paper.get("slug")
            for paper in item.get("representative_papers", [])
            if isinstance(paper, dict)
        ]
        unknown_representatives = sorted(set(representative_slugs) - report_slugs)
        if unknown_representatives:
            errors.append(f"roadmap.json roadmaps[{index}] representative_papers reference unknown slugs: {unknown_representatives}")
        queue_slugs = {
            slug
            for queue in (item.get("queues") or {}).values()
            if isinstance(queue, list)
            for slug in queue
        }
        unknown_queue_slugs = sorted(queue_slugs - report_slugs)
        if unknown_queue_slugs:
            errors.append(f"roadmap.json roadmaps[{index}] queues reference unknown slugs: {unknown_queue_slugs}")
        milestone_slugs = {
            slug
            for milestone in item.get("milestones", [])
            if isinstance(milestone, dict)
            for slug in milestone.get("representative_slugs", [])
        }
        unknown_milestone_slugs = sorted(milestone_slugs - report_slugs)
        if unknown_milestone_slugs:
            errors.append(f"roadmap.json roadmaps[{index}] milestones reference unknown slugs: {unknown_milestone_slugs}")
        actions = item.get("actions")
        if not isinstance(actions, list):
            errors.append(f"roadmap.json roadmaps[{index}].actions must be a list")
            actions = []
        for action_index, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(f"roadmap.json roadmaps[{index}].actions[{action_index}] must be an object")
                continue
            for key in ("type", "priority", "label", "href", "slugs"):
                if key not in action:
                    errors.append(f"roadmap.json roadmaps[{index}].actions[{action_index}] missing {key}")
            if action.get("type") not in roadmap_action_types:
                errors.append(f"roadmap.json roadmaps[{index}].actions[{action_index}].type has invalid value")
            action_slugs = set(action.get("slugs", [])) if isinstance(action.get("slugs"), list) else set()
            unknown_action_slugs = sorted(action_slugs - report_slugs)
            if unknown_action_slugs:
                errors.append(f"roadmap.json roadmaps[{index}].actions[{action_index}] references unknown slugs: {unknown_action_slugs}")
    roadmap_actions = roadmap_data.get("actions")
    if not isinstance(roadmap_actions, list):
        errors.append("roadmap.json actions must be a list")
    if not isinstance(roadmap_data.get("recommended_roles"), list) or not roadmap_data.get("recommended_roles"):
        errors.append("roadmap.json recommended_roles must be a non-empty list")
    links = roadmap_data.get("links")
    if not isinstance(links, dict) or not {"library", "lines", "clusters", "gaps"}.issubset(links):
        errors.append("roadmap.json links must include library, lines, clusters, and gaps")

    if scale_data.get("count") != len(report_slugs):
        errors.append(f"scale.json count {scale_data.get('count')} != markdown report count {len(report_slugs)}")
    required_scale = {
        "readiness_score",
        "readiness_label",
        "resource_sizes",
        "queue_sizes",
        "bottlenecks",
        "capacity_projection",
        "scale_tiers",
        "status_workflow",
        "links",
    }
    missing_scale = sorted(required_scale - set(scale_data))
    if missing_scale:
        errors.append(f"scale.json missing keys: {', '.join(missing_scale)}")
    score = scale_data.get("readiness_score")
    if not isinstance(score, int) or not (0 <= score <= 100):
        errors.append("scale.json readiness_score must be an integer from 0 to 100")
    if scale_data.get("readiness_label") not in {"ready", "watch", "needs_governance"}:
        errors.append("scale.json readiness_label has invalid value")
    status_workflow = scale_data.get("status_workflow")
    if not isinstance(status_workflow, dict):
        errors.append("scale.json status_workflow must be an object")
        status_workflow = {}
    for key in ("workflow_count", "status_count", "reading_stage_count", "review_stage_count"):
        value = status_workflow.get(key)
        if not isinstance(value, int) or value < 0:
            errors.append(f"scale.json status_workflow.{key} must be a non-negative integer")
    if not status_workflow.get("active"):
        errors.append("scale.json status_workflow.active must be non-empty")
    resource_sizes = scale_data.get("resource_sizes")
    if not isinstance(resource_sizes, list):
        errors.append("scale.json resource_sizes must be a list")
        resource_sizes = []
    resource_hrefs = {str(item.get("href") or "") for item in resource_sizes if isinstance(item, dict)}
    for href in ("papers.json", "search_index.json", "taxonomy_map.json", "actions.json"):
        if href not in resource_hrefs:
            errors.append(f"scale.json resource_sizes missing {href}")
    bottlenecks = scale_data.get("bottlenecks")
    if not isinstance(bottlenecks, list) or not bottlenecks:
        errors.append("scale.json bottlenecks must be a non-empty list")
        bottlenecks = []
    for index, item in enumerate(bottlenecks):
        if not isinstance(item, dict):
            errors.append(f"scale.json bottlenecks[{index}] must be an object")
            continue
        for key in ("severity", "area", "signal", "recommendation", "href"):
            if key not in item:
                errors.append(f"scale.json bottlenecks[{index}] missing {key}")
    projections = scale_data.get("capacity_projection")
    if not isinstance(projections, list) or not projections:
        errors.append("scale.json capacity_projection must be a non-empty list")
    else:
        projected_counts = {item.get("paper_count") for item in projections if isinstance(item, dict)}
        for target in (100, 500, 1000, 5000):
            if target not in projected_counts:
                errors.append(f"scale.json capacity_projection missing {target}")
    if not isinstance(scale_data.get("scale_tiers"), list) or not scale_data.get("scale_tiers"):
        errors.append("scale.json scale_tiers must be a non-empty list")

    if ownership_data.get("count") != len(report_slugs):
        errors.append(f"ownership.json count {ownership_data.get('count')} != markdown report count {len(report_slugs)}")
    required_ownership = {"owner_count", "unassigned_line_count", "owners", "lines", "links"}
    missing_ownership = sorted(required_ownership - set(ownership_data))
    if missing_ownership:
        errors.append(f"ownership.json missing keys: {', '.join(missing_ownership)}")
    owners = ownership_data.get("owners")
    if not isinstance(owners, list):
        errors.append("ownership.json owners must be a list")
        owners = []
    lines = ownership_data.get("lines")
    if not isinstance(lines, list):
        errors.append("ownership.json lines must be a list")
        lines = []
    if ownership_data.get("owner_count") != len(owners):
        errors.append("ownership.json owner_count must match owners length")
    valid_risks = {"high", "medium", "low"}
    for index, owner in enumerate(owners):
        if not isinstance(owner, dict):
            errors.append(f"ownership.json owners[{index}] must be an object")
            continue
        for key in ("owner", "line_count", "paper_count", "risk", "queues", "lines"):
            if key not in owner:
                errors.append(f"ownership.json owners[{index}] missing {key}")
        if owner.get("risk") not in valid_risks:
            errors.append(f"ownership.json owners[{index}].risk has invalid value")
        if not isinstance(owner.get("queues"), dict):
            errors.append(f"ownership.json owners[{index}].queues must be an object")
        if not isinstance(owner.get("lines"), list):
            errors.append(f"ownership.json owners[{index}].lines must be a list")
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            errors.append(f"ownership.json lines[{index}] must be an object")
            continue
        for key in ("line", "owner", "count", "risk", "queues", "href"):
            if key not in line:
                errors.append(f"ownership.json lines[{index}] missing {key}")
        if line.get("risk") not in valid_risks:
            errors.append(f"ownership.json lines[{index}].risk has invalid value")
        if not isinstance(line.get("queues"), dict):
            errors.append(f"ownership.json lines[{index}].queues must be an object")
        sample_slugs = line.get("sample_slugs", [])
        if sample_slugs and not isinstance(sample_slugs, list):
            errors.append(f"ownership.json lines[{index}].sample_slugs must be a list")
        unknown_line_slugs = sorted(set(sample_slugs) - report_slugs) if isinstance(sample_slugs, list) else []
        if unknown_line_slugs:
            errors.append(f"ownership.json lines[{index}] references unknown slugs: {unknown_line_slugs}")

    if routing_data.get("count") != len(report_slugs):
        errors.append(f"routing.json count {routing_data.get('count')} != markdown report count {len(report_slugs)}")
    required_routing = {
        "line_profiles",
        "label_profiles",
        "paper_signatures",
        "tokenizer",
        "weights",
        "input_contract",
        "links",
    }
    missing_routing = sorted(required_routing - set(routing_data))
    if missing_routing:
        errors.append(f"routing.json missing keys: {', '.join(missing_routing)}")
    line_profiles = routing_data.get("line_profiles")
    if not isinstance(line_profiles, list) or not line_profiles:
        errors.append("routing.json line_profiles must be a non-empty list")
        line_profiles = []
    label_profiles = routing_data.get("label_profiles")
    if not isinstance(label_profiles, list) or not label_profiles:
        errors.append("routing.json label_profiles must be a non-empty list")
        label_profiles = []
    paper_signatures = routing_data.get("paper_signatures")
    if not isinstance(paper_signatures, list):
        errors.append("routing.json paper_signatures must be a list")
        paper_signatures = []
    if routing_data.get("paper_count") != len(paper_signatures):
        errors.append("routing.json paper_count must match paper_signatures length")
    if {str(item.get("slug") or "") for item in paper_signatures if isinstance(item, dict)} != report_slugs:
        errors.append("routing.json paper_signatures slugs must match markdown reports")
    for index, profile in enumerate(line_profiles):
        if not isinstance(profile, dict):
            errors.append(f"routing.json line_profiles[{index}] must be an object")
            continue
        for key in ("line", "count", "href", "terms", "sample_slugs"):
            if key not in profile:
                errors.append(f"routing.json line_profiles[{index}] missing {key}")
        if not isinstance(profile.get("terms"), list) or not profile.get("terms"):
            errors.append(f"routing.json line_profiles[{index}].terms must be a non-empty list")
    valid_label_fields = {"domains", "tracks", "problems", "topics", "methods"}
    for index, profile in enumerate(label_profiles):
        if not isinstance(profile, dict):
            errors.append(f"routing.json label_profiles[{index}] must be an object")
            continue
        for key in ("field", "value", "count", "href", "terms", "sample_slugs"):
            if key not in profile:
                errors.append(f"routing.json label_profiles[{index}] missing {key}")
        if profile.get("field") not in valid_label_fields:
            errors.append(f"routing.json label_profiles[{index}].field has invalid value")
        if not isinstance(profile.get("terms"), list) or not profile.get("terms"):
            errors.append(f"routing.json label_profiles[{index}].terms must be a non-empty list")

    if onboarding_data.get("count") != len(report_slugs):
        errors.append(f"onboarding.json count {onboarding_data.get('count')} != markdown report count {len(report_slugs)}")
    required_onboarding = {
        "readiness_score",
        "readiness_checks",
        "quickstart_steps",
        "contribution_paths",
        "command_groups",
        "contracts",
        "bootstrap_files",
        "links",
    }
    missing_onboarding = sorted(required_onboarding - set(onboarding_data))
    if missing_onboarding:
        errors.append(f"onboarding.json missing keys: {', '.join(missing_onboarding)}")
    readiness_checks = onboarding_data.get("readiness_checks")
    if not isinstance(readiness_checks, list) or not readiness_checks:
        errors.append("onboarding.json readiness_checks must be a non-empty list")
        readiness_checks = []
    for index, item in enumerate(readiness_checks):
        if not isinstance(item, dict):
            errors.append(f"onboarding.json readiness_checks[{index}] must be an object")
            continue
        for key in ("path", "label", "href", "exists"):
            if key not in item:
                errors.append(f"onboarding.json readiness_checks[{index}] missing {key}")
        if not isinstance(item.get("exists"), bool):
            errors.append(f"onboarding.json readiness_checks[{index}].exists must be boolean")
    contribution_paths = onboarding_data.get("contribution_paths")
    if not isinstance(contribution_paths, list) or not contribution_paths:
        errors.append("onboarding.json contribution_paths must be a non-empty list")
        contribution_paths = []
    for index, item in enumerate(contribution_paths):
        if not isinstance(item, dict):
            errors.append(f"onboarding.json contribution_paths[{index}] must be an object")
            continue
        for key in ("id", "title", "entry", "contract", "recommended_pages", "commands"):
            if key not in item:
                errors.append(f"onboarding.json contribution_paths[{index}] missing {key}")
        if not isinstance(item.get("recommended_pages"), list):
            errors.append(f"onboarding.json contribution_paths[{index}].recommended_pages must be a list")
        if not isinstance(item.get("commands"), list):
            errors.append(f"onboarding.json contribution_paths[{index}].commands must be a list")
    if not isinstance(onboarding_data.get("quickstart_steps"), list) or not onboarding_data.get("quickstart_steps"):
        errors.append("onboarding.json quickstart_steps must be a non-empty list")
    if not isinstance(onboarding_data.get("command_groups"), list) or not onboarding_data.get("command_groups"):
        errors.append("onboarding.json command_groups must be a non-empty list")
    if not isinstance(onboarding_data.get("contracts"), list) or not onboarding_data.get("contracts"):
        errors.append("onboarding.json contracts must be a non-empty list")
    bootstrap_files = onboarding_data.get("bootstrap_files")
    if not isinstance(bootstrap_files, list) or "onboarding.json" not in bootstrap_files:
        errors.append("onboarding.json bootstrap_files must include onboarding.json")

    if intake_data.get("count") != len(report_slugs):
        errors.append(f"intake.json count {intake_data.get('count')} != markdown report count {len(report_slugs)}")
    required_intake = {"existing_papers", "inbox_items", "csv_columns", "defaults", "statuses", "patterns", "commands", "links"}
    missing_intake = sorted(required_intake - set(intake_data))
    if missing_intake:
        errors.append(f"intake.json missing keys: {', '.join(missing_intake)}")
    intake_existing = intake_data.get("existing_papers")
    if not isinstance(intake_existing, list):
        errors.append("intake.json existing_papers must be a list")
        intake_existing = []
    intake_slugs = {item.get("slug") for item in intake_existing if isinstance(item, dict)}
    if intake_slugs != report_slugs:
        errors.append(
            "intake.json existing_papers slugs do not match markdown reports: "
            f"missing={sorted(report_slugs - intake_slugs)}, extra={sorted(intake_slugs - report_slugs)}"
        )
    for index, item in enumerate(intake_existing):
        if not isinstance(item, dict):
            errors.append(f"intake.json existing_papers[{index}] must be an object")
            continue
        for key in ("slug", "title", "arxiv_key", "title_keys", "link_keys", "href"):
            if key not in item:
                errors.append(f"intake.json existing_papers[{index}] missing {key}")
        if not isinstance(item.get("title_keys"), list):
            errors.append(f"intake.json existing_papers[{index}].title_keys must be a list")
        if not isinstance(item.get("link_keys"), list):
            errors.append(f"intake.json existing_papers[{index}].link_keys must be a list")
    intake_items = intake_data.get("inbox_items")
    if not isinstance(intake_items, list):
        errors.append("intake.json inbox_items must be a list")
        intake_items = []
    inbox_items_payload = inbox_data.get("items")
    if isinstance(inbox_items_payload, list) and intake_data.get("inbox_count") != len(inbox_items_payload):
        errors.append("intake.json inbox_count must match inbox.json items length")
    csv_columns = intake_data.get("csv_columns")
    if not isinstance(csv_columns, list) or not {"title", "link"}.issubset(set(csv_columns)):
        errors.append("intake.json csv_columns must include title and link")
    defaults = intake_data.get("defaults")
    if not isinstance(defaults, dict) or not {"status", "priority", "added_at"}.issubset(defaults):
        errors.append("intake.json defaults must include status, priority, and added_at")
    if not isinstance(intake_data.get("commands"), list) or not any("apply_inbox_items.py" in str(command) for command in intake_data.get("commands", [])):
        errors.append("intake.json commands must include apply_inbox_items.py")
    links = intake_data.get("links")
    if not isinstance(links, dict) or not {"inbox", "routing", "schema"}.issubset(links):
        errors.append("intake.json links must include inbox, routing, and schema")

    if catalog_data.get("count") != len(report_slugs):
        errors.append(f"catalog.json count {catalog_data.get('count')} != markdown report count {len(report_slugs)}")
    required_catalog = {"pages", "data_resources", "contracts", "integration_recipes", "recommended_bootstrap_files"}
    missing_catalog = sorted(required_catalog - set(catalog_data))
    if missing_catalog:
        errors.append(f"catalog.json missing keys: {', '.join(missing_catalog)}")
    catalog_pages = catalog_data.get("pages")
    if not isinstance(catalog_pages, list):
        errors.append("catalog.json pages must be a list")
        catalog_pages = []
    catalog_page_hrefs = {str(item.get("href") or "") for item in catalog_pages if isinstance(item, dict)}
    expected_catalog_pages = {page for page in REQUIRED_PAGES if page.endswith(".html")}
    missing_catalog_pages = sorted(expected_catalog_pages - catalog_page_hrefs)
    if missing_catalog_pages:
        errors.append(f"catalog.json pages missing entries: {', '.join(missing_catalog_pages)}")
    valid_catalog_page_kinds = {"view", "ops", "workflow", "analysis", "planning"}
    for index, item in enumerate(catalog_pages):
        if not isinstance(item, dict):
            errors.append(f"catalog.json pages[{index}] must be an object")
            continue
        for key in ("title", "href", "kind", "description"):
            if key not in item:
                errors.append(f"catalog.json pages[{index}] missing {key}")
        if item.get("kind") not in valid_catalog_page_kinds:
            errors.append(f"catalog.json pages[{index}] has invalid kind")
    catalog_resources = catalog_data.get("data_resources")
    if not isinstance(catalog_resources, list):
        errors.append("catalog.json data_resources must be a list")
        catalog_resources = []
    catalog_resource_hrefs = {str(item.get("href") or "") for item in catalog_resources if isinstance(item, dict)}
    expected_catalog_resources = {page for page in REQUIRED_PAGES if page.endswith(".json")}
    missing_catalog_resources = sorted(expected_catalog_resources - catalog_resource_hrefs)
    if missing_catalog_resources:
        errors.append(f"catalog.json data_resources missing entries: {', '.join(missing_catalog_resources)}")
    for index, item in enumerate(catalog_resources):
        if not isinstance(item, dict):
            errors.append(f"catalog.json data_resources[{index}] must be an object")
            continue
        for key in ("href", "description", "exists", "size_bytes", "top_level_keys", "collections", "declared_count", "generated_at", "consumers", "error"):
            if key not in item:
                errors.append(f"catalog.json data_resources[{index}] missing {key}")
        if not isinstance(item.get("exists"), bool):
            errors.append(f"catalog.json data_resources[{index}].exists must be boolean")
        if not isinstance(item.get("top_level_keys"), list):
            errors.append(f"catalog.json data_resources[{index}].top_level_keys must be a list")
        if not isinstance(item.get("collections"), list):
            errors.append(f"catalog.json data_resources[{index}].collections must be a list")
        if not isinstance(item.get("consumers"), list):
            errors.append(f"catalog.json data_resources[{index}].consumers must be a list")
    catalog_contracts = catalog_data.get("contracts")
    if not isinstance(catalog_contracts, list):
        errors.append("catalog.json contracts must be a list")
        catalog_contracts = []
    catalog_contract_hrefs = {str(item.get("href") or "") for item in catalog_contracts if isinstance(item, dict)}
    if "guides/taxonomy.json" not in catalog_contract_hrefs:
        errors.append("catalog.json contracts missing guides/taxonomy.json")
    for index, item in enumerate(catalog_contracts):
        if not isinstance(item, dict):
            errors.append(f"catalog.json contracts[{index}] must be an object")
            continue
        for key in ("href", "description"):
            if key not in item:
                errors.append(f"catalog.json contracts[{index}] missing {key}")
    integration_recipes = catalog_data.get("integration_recipes")
    if not isinstance(integration_recipes, list) or not integration_recipes:
        errors.append("catalog.json integration_recipes must be a non-empty list")
        integration_recipes = []
    for index, item in enumerate(integration_recipes):
        if not isinstance(item, dict):
            errors.append(f"catalog.json integration_recipes[{index}] must be an object")
            continue
        for key in ("name", "command", "uses", "outputs"):
            if key not in item:
                errors.append(f"catalog.json integration_recipes[{index}] missing {key}")
        if not isinstance(item.get("uses"), list):
            errors.append(f"catalog.json integration_recipes[{index}].uses must be a list")
        if not isinstance(item.get("outputs"), list):
            errors.append(f"catalog.json integration_recipes[{index}].outputs must be a list")
    bootstrap_files = catalog_data.get("recommended_bootstrap_files")
    if not isinstance(bootstrap_files, list) or "catalog.json" not in bootstrap_files:
        errors.append("catalog.json recommended_bootstrap_files must include catalog.json")

    if stats_data.get("count") != len(report_slugs):
        errors.append(f"stats.json count {stats_data.get('count')} != markdown report count {len(report_slugs)}")
    required_stats = {"quality_score", "controls", "coverage", "queue_sizes", "taxonomy", "distributions", "research_lines"}
    missing_stats = sorted(required_stats - set(stats_data))
    if missing_stats:
        errors.append(f"stats.json missing keys: {', '.join(missing_stats)}")
    stats_controls = stats_data.get("controls") or {}
    missing_stats_controls = sorted(required_controls - set(stats_controls))
    if missing_stats_controls:
        errors.append(f"stats.json controls missing keys: {', '.join(missing_stats_controls)}")
    if set((stats_data.get("queue_sizes") or {}).keys()) != {"quality", "review"}:
        errors.append("stats.json queue_sizes must contain quality and review")
    if not isinstance(stats_data.get("research_lines"), list):
        errors.append("stats.json research_lines must be a list")

    if inbox_data.get("count") != len(inbox_data.get("items") or []):
        errors.append("inbox.json count must match items length")
    inbox_items_for_dedupe = inbox_data.get("items") if isinstance(inbox_data.get("items"), list) else []
    inbox_ids = {str(item.get("id") or "") for item in inbox_items_for_dedupe if isinstance(item, dict)}

    if dedupe_data.get("count") != len(report_slugs):
        errors.append(f"dedupe.json count {dedupe_data.get('count')} != markdown report count {len(report_slugs)}")
    if dedupe_data.get("inbox_count") != len(inbox_items_for_dedupe):
        errors.append("dedupe.json inbox_count must match inbox.json items length")
    required_dedupe = {"report_groups", "inbox_groups", "summary", "csv_columns", "commands", "links"}
    missing_dedupe = sorted(required_dedupe - set(dedupe_data))
    if missing_dedupe:
        errors.append(f"dedupe.json missing keys: {', '.join(missing_dedupe)}")
    report_groups = dedupe_data.get("report_groups")
    if not isinstance(report_groups, list):
        errors.append("dedupe.json report_groups must be a list")
        report_groups = []
    inbox_groups = dedupe_data.get("inbox_groups")
    if not isinstance(inbox_groups, list):
        errors.append("dedupe.json inbox_groups must be a list")
        inbox_groups = []
    if dedupe_data.get("duplicate_report_count") != len(report_groups):
        errors.append("dedupe.json duplicate_report_count must match report_groups length")
    if dedupe_data.get("inbox_duplicate_count") != len(inbox_groups):
        errors.append("dedupe.json inbox_duplicate_count must match inbox_groups length")
    if dedupe_data.get("group_count") != len(report_groups) + len(inbox_groups):
        errors.append("dedupe.json group_count must match report_groups + inbox_groups")
    for label, groups in (("report_groups", report_groups), ("inbox_groups", inbox_groups)):
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                errors.append(f"dedupe.json {label}[{index}] must be an object")
                continue
            for key in ("id", "scope", "kind", "key", "severity", "slugs", "item_ids", "recommended_action"):
                if key not in group:
                    errors.append(f"dedupe.json {label}[{index}] missing {key}")
            unknown_slugs = sorted(str(slug) for slug in group.get("slugs", []) if str(slug) not in report_slugs)
            if unknown_slugs:
                errors.append(f"dedupe.json {label}[{index}] references unknown slugs: {unknown_slugs}")
            unknown_items = sorted(str(item_id) for item_id in group.get("item_ids", []) if str(item_id) not in inbox_ids)
            if unknown_items:
                errors.append(f"dedupe.json {label}[{index}] references unknown inbox ids: {unknown_items}")
    dedupe_columns = dedupe_data.get("csv_columns")
    if not isinstance(dedupe_columns, list) or not {"scope", "kind", "key", "severity"}.issubset(set(dedupe_columns)):
        errors.append("dedupe.json csv_columns must include scope, kind, key, and severity")
    if not isinstance(dedupe_data.get("commands"), list) or not any("check_quality.py" in str(command) for command in dedupe_data.get("commands", [])):
        errors.append("dedupe.json commands must include check_quality.py")
    dedupe_links = dedupe_data.get("links")
    if not isinstance(dedupe_links, dict) or not {"quality", "inbox", "actions", "library"}.issubset(dedupe_links):
        errors.append("dedupe.json links must include quality, inbox, actions, and library")

    if registry_data.get("count") != len(report_slugs):
        errors.append(f"registry.json count {registry_data.get('count')} != markdown report count {len(report_slugs)}")
    required_registry = {"label_count", "labels", "summary", "field_counts", "csv_columns", "commands", "links"}
    missing_registry = sorted(required_registry - set(registry_data))
    if missing_registry:
        errors.append(f"registry.json missing keys: {', '.join(missing_registry)}")
    registry_labels = registry_data.get("labels")
    if not isinstance(registry_labels, list):
        errors.append("registry.json labels must be a list")
        registry_labels = []
    if registry_data.get("label_count") != len(registry_labels):
        errors.append("registry.json label_count must match labels length")
    valid_registry_severities = {"high", "medium", "low", "ok"}
    for index, item in enumerate(registry_labels):
        if not isinstance(item, dict):
            errors.append(f"registry.json labels[{index}] must be an object")
            continue
        for key in ("id", "label", "fields", "field_names", "severity", "signals", "slugs", "definitions", "definition_status", "description", "recommended_action"):
            if key not in item:
                errors.append(f"registry.json labels[{index}] missing {key}")
        if item.get("severity") not in valid_registry_severities:
            errors.append(f"registry.json labels[{index}] has invalid severity")
        if not isinstance(item.get("fields"), list):
            errors.append(f"registry.json labels[{index}].fields must be a list")
        if not isinstance(item.get("field_names"), list):
            errors.append(f"registry.json labels[{index}].field_names must be a list")
        if not isinstance(item.get("definitions"), list):
            errors.append(f"registry.json labels[{index}].definitions must be a list")
        unknown_slugs = sorted(str(slug) for slug in item.get("slugs", []) if str(slug) not in report_slugs)
        if unknown_slugs:
            errors.append(f"registry.json labels[{index}] references unknown slugs: {unknown_slugs}")
    registry_columns = registry_data.get("csv_columns")
    if not isinstance(registry_columns, list) or not {"label", "severity", "fields", "recommended_action"}.issubset(set(registry_columns)):
        errors.append("registry.json csv_columns must include label, severity, fields, and recommended_action")
    if not isinstance(registry_data.get("commands"), list) or not any("export_taxonomy_registry.py" in str(command) for command in registry_data.get("commands", [])):
        errors.append("registry.json commands must include export_taxonomy_registry.py")
    registry_links = registry_data.get("links")
    if not isinstance(registry_links, dict) or not {"taxonomy", "facets", "quality", "library"}.issubset(registry_links):
        errors.append("registry.json links must include taxonomy, facets, quality, and library")

    if facets_data.get("count") != len(report_slugs):
        errors.append(f"facets.json count {facets_data.get('count')} != markdown report count {len(report_slugs)}")
    required_facets = {"field_count", "value_count", "summary", "fields", "values", "csv_columns", "commands", "links"}
    missing_facets = sorted(required_facets - set(facets_data))
    if missing_facets:
        errors.append(f"facets.json missing keys: {', '.join(missing_facets)}")
    facet_fields = facets_data.get("fields")
    if not isinstance(facet_fields, list):
        errors.append("facets.json fields must be a list")
        facet_fields = []
    facet_values = facets_data.get("values")
    if not isinstance(facet_values, list):
        errors.append("facets.json values must be a list")
        facet_values = []
    if facets_data.get("field_count") != len(facet_fields):
        errors.append("facets.json field_count must match fields length")
    if facets_data.get("value_count") != len(facet_values):
        errors.append("facets.json value_count must match values length")
    valid_facet_fields = {"domains", "tracks", "problems", "topics", "methods", "research_line", "line_role", "status", "reading_stage", "review_stage"}
    valid_facet_actions = {"stable", "watch", "merge_candidate", "split_candidate", "unused_config"}
    valid_facet_severities = {"none", "low", "medium", "high"}
    seen_facet_fields: set[str] = set()
    for index, item in enumerate(facet_fields):
        if not isinstance(item, dict):
            errors.append(f"facets.json fields[{index}] must be an object")
            continue
        for key in ("field", "label", "english", "query_key", "is_list", "used_count", "unused_count", "href"):
            if key not in item:
                errors.append(f"facets.json fields[{index}] missing {key}")
        field = str(item.get("field") or "")
        if field not in valid_facet_fields:
            errors.append(f"facets.json fields[{index}] has unknown field {field!r}")
        seen_facet_fields.add(field)
        if not isinstance(item.get("is_list"), bool):
            errors.append(f"facets.json fields[{index}].is_list must be boolean")
    missing_expected_facet_fields = sorted(valid_facet_fields - seen_facet_fields)
    if missing_expected_facet_fields:
        errors.append(f"facets.json fields missing expected fields: {', '.join(missing_expected_facet_fields)}")
    for index, item in enumerate(facet_values):
        if not isinstance(item, dict):
            errors.append(f"facets.json values[{index}] must be an object")
            continue
        for key in ("field", "value", "count", "share", "configured", "action", "severity", "href", "sample_slugs", "recommendation"):
            if key not in item:
                errors.append(f"facets.json values[{index}] missing {key}")
        if item.get("field") not in valid_facet_fields:
            errors.append(f"facets.json values[{index}] has unknown field {item.get('field')!r}")
        if item.get("action") not in valid_facet_actions:
            errors.append(f"facets.json values[{index}] has invalid action")
        if item.get("severity") not in valid_facet_severities:
            errors.append(f"facets.json values[{index}] has invalid severity")
        if not isinstance(item.get("configured"), bool):
            errors.append(f"facets.json values[{index}].configured must be boolean")
        unknown_slugs = sorted(str(slug) for slug in item.get("sample_slugs", []) if str(slug) not in report_slugs)
        if unknown_slugs:
            errors.append(f"facets.json values[{index}] references unknown slugs: {unknown_slugs}")
    facet_columns = facets_data.get("csv_columns")
    if not isinstance(facet_columns, list) or not {"field", "value", "action", "severity", "recommendation"}.issubset(set(facet_columns)):
        errors.append("facets.json csv_columns must include field, value, action, severity, and recommendation")
    if not isinstance(facets_data.get("commands"), list) or not any("export_taxonomy_actions.py" in str(command) for command in facets_data.get("commands", [])):
        errors.append("facets.json commands must include export_taxonomy_actions.py")
    facet_links = facets_data.get("links")
    if not isinstance(facet_links, dict) or not {"html", "library", "taxonomy", "registry", "quality", "actions"}.issubset(facet_links):
        errors.append("facets.json links must include html, library, taxonomy, registry, quality, and actions")

    if manifest_data.get("count") != len(report_slugs):
        errors.append(f"manifest.json count {manifest_data.get('count')} != markdown report count {len(report_slugs)}")
    required_manifest = {
        "publish_ready",
        "publish_checks",
        "quality_score",
        "coverage",
        "queue_sizes",
        "pages",
        "data_files",
        "contract_files",
        "artifact_inventory",
        "commands",
    }
    missing_manifest = sorted(required_manifest - set(manifest_data))
    if missing_manifest:
        errors.append(f"manifest.json missing keys: {', '.join(missing_manifest)}")
    manifest_pages = {str(item.get("href") or "") for item in manifest_data.get("pages", []) if isinstance(item, dict)}
    expected_manifest_pages = {page for page in REQUIRED_PAGES if page.endswith(".html")}
    missing_manifest_pages = sorted(expected_manifest_pages - manifest_pages)
    if missing_manifest_pages:
        errors.append(f"manifest.json pages missing entries: {', '.join(missing_manifest_pages)}")
    manifest_data_files = {str(item.get("href") or "") for item in manifest_data.get("data_files", []) if isinstance(item, dict)}
    expected_data_files = {page for page in REQUIRED_PAGES if page.endswith(".json")}
    missing_manifest_files = sorted(expected_data_files - manifest_data_files)
    if missing_manifest_files:
        errors.append(f"manifest.json data_files missing entries: {', '.join(missing_manifest_files)}")
    manifest_contract_files = {str(item.get("href") or "") for item in manifest_data.get("contract_files", []) if isinstance(item, dict)}
    expected_contract_files = {
        "guides/metadata.schema.json",
        "guides/taxonomy.json",
        "guides/facets.schema.json",
        "guides/batch.schema.json",
        "guides/actions.schema.json",
        "guides/catalog.schema.json",
        "guides/manifest.schema.json",
        "guides/workflow.schema.json",
        "guides/status.schema.json",
        "guides/views.schema.json",
    }
    missing_contract_files = sorted(expected_contract_files - manifest_contract_files)
    if missing_contract_files:
        errors.append(f"manifest.json contract_files missing entries: {', '.join(missing_contract_files)}")
    artifact_inventory = manifest_data.get("artifact_inventory")
    if not isinstance(artifact_inventory, list):
        errors.append("manifest.json artifact_inventory must be a list")
    else:
        artifact_hrefs = set()
        for index, artifact in enumerate(artifact_inventory):
            if not isinstance(artifact, dict):
                errors.append(f"manifest.json artifact_inventory[{index}] must be an object")
                continue
            href = str(artifact.get("href") or "")
            artifact_hrefs.add(href)
            if not href:
                errors.append(f"manifest.json artifact_inventory[{index}] missing href")
            if artifact.get("kind") not in {"page", "data", "contract"}:
                errors.append(f"manifest.json artifact_inventory[{index}] has invalid kind")
            status = artifact.get("status")
            if status not in {"ok", "missing", "generated_after_inventory"}:
                errors.append(f"manifest.json artifact_inventory[{index}] has invalid status")
            if artifact.get("exists") is not True and status != "missing":
                errors.append(f"manifest.json artifact_inventory[{index}] exists must be true unless missing")
            if status == "ok":
                if not isinstance(artifact.get("size_bytes"), int) or artifact.get("size_bytes") <= 0:
                    errors.append(f"manifest.json artifact_inventory[{index}] size_bytes must be a positive integer")
                if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256") or "")):
                    errors.append(f"manifest.json artifact_inventory[{index}] sha256 must be 64 lowercase hex characters")
                if artifact.get("hash_mode") not in {"raw", "normalized"}:
                    errors.append(f"manifest.json artifact_inventory[{index}] hash_mode must be raw or normalized")
        expected_artifacts = manifest_pages | manifest_data_files | manifest_contract_files
        missing_artifacts = sorted(expected_artifacts - artifact_hrefs)
        if missing_artifacts:
            errors.append(f"manifest.json artifact_inventory missing entries: {', '.join(missing_artifacts)}")
    required_inbox = {"count", "statuses", "priorities", "duplicates", "items"}
    missing_inbox = sorted(required_inbox - set(inbox_data))
    if missing_inbox:
        errors.append(f"inbox.json missing keys: {', '.join(missing_inbox)}")
    if not isinstance(inbox_data.get("items"), list):
        errors.append("inbox.json items must be a list")

    if snapshot_data.get("count") != len(report_slugs):
        errors.append(f"snapshot.json count {snapshot_data.get('count')} != markdown report count {len(report_slugs)}")
    required_snapshot = {
        "snapshot_id",
        "publish_ready",
        "publish_checks",
        "quality_score",
        "coverage",
        "queue_sizes",
        "risk_queue_sizes",
        "action_groups",
        "governance_policy",
        "research_lines",
        "artifact_summary",
        "links",
    }
    missing_snapshot = sorted(required_snapshot - set(snapshot_data))
    if missing_snapshot:
        errors.append(f"snapshot.json missing keys: {', '.join(missing_snapshot)}")
    if not re.fullmatch(r"[0-9a-f]{16}", str(snapshot_data.get("snapshot_id") or "")):
        errors.append("snapshot.json snapshot_id must be 16 lowercase hex characters")
    if not isinstance(snapshot_data.get("risk_queue_sizes"), dict):
        errors.append("snapshot.json risk_queue_sizes must be an object")
    if not isinstance(snapshot_data.get("action_groups"), list):
        errors.append("snapshot.json action_groups must be a list")
    if not isinstance(snapshot_data.get("research_lines"), list):
        errors.append("snapshot.json research_lines must be a list")
    artifact_summary = snapshot_data.get("artifact_summary") or {}
    if not isinstance(artifact_summary, dict):
        errors.append("snapshot.json artifact_summary must be an object")
    elif not isinstance(artifact_summary.get("hashes"), list):
        errors.append("snapshot.json artifact_summary.hashes must be a list")


def validate_taxonomy_config(report_dir: Path, errors: list[str], warnings: list[str]) -> dict[str, Any]:
    config_path = report_dir / "guides" / "taxonomy.json"
    if not config_path.exists():
        return {}

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/taxonomy.json: invalid JSON: {exc}")
        return {}

    if not isinstance(config, dict):
        errors.append("guides/taxonomy.json: root must be an object")
        return {}

    known_fields = {
        "$schema",
        "label_aliases",
        "shared_views",
        "research_line_owners",
        "label_definitions",
        "governance_policy",
        "active_status_workflow",
        "status_workflows",
        *TAXONOMY_CONFIG_LIST_FIELDS,
    }
    unknown_fields = sorted(set(config) - known_fields)
    if unknown_fields:
        warnings.append(f"guides/taxonomy.json: unknown fields ignored: {', '.join(unknown_fields)}")

    schema_ref = config.get("$schema")
    if schema_ref is not None:
        if not isinstance(schema_ref, str) or not schema_ref.strip():
            errors.append("guides/taxonomy.json: $schema must be a non-empty string")
        elif "://" not in schema_ref:
            schema_path = (config_path.parent / schema_ref).resolve()
            try:
                schema_path.relative_to(config_path.parent.resolve())
            except ValueError:
                errors.append("guides/taxonomy.json: $schema must stay inside guides/")
            else:
                if not schema_path.exists():
                    errors.append(f"guides/taxonomy.json: $schema target does not exist: {schema_ref}")

    aliases = config.get("label_aliases", {})
    if aliases is not None and not isinstance(aliases, dict):
        errors.append("guides/taxonomy.json: label_aliases must be an object")
    elif isinstance(aliases, dict):
        for alias, canonical in aliases.items():
            if not isinstance(alias, str) or not alias.strip():
                errors.append("guides/taxonomy.json: label_aliases keys must be non-empty strings")
            if not isinstance(canonical, str) or not canonical.strip():
                errors.append(f"guides/taxonomy.json: alias '{alias}' must map to a non-empty string")

    for field in TAXONOMY_CONFIG_LIST_FIELDS:
        validate_string_list(config.get(field, []), f"guides/taxonomy.json: {field}", errors, allow_none=True)

    active_workflow = config.get("active_status_workflow", "")
    if active_workflow is not None and active_workflow != "" and (
        not isinstance(active_workflow, str) or not active_workflow.strip()
    ):
        errors.append("guides/taxonomy.json: active_status_workflow must be a non-empty string")

    workflows = config.get("status_workflows", {})
    if workflows is not None and workflows != {} and not isinstance(workflows, dict):
        errors.append("guides/taxonomy.json: status_workflows must be an object")
    elif isinstance(workflows, dict):
        active_name = active_workflow.strip() if isinstance(active_workflow, str) else ""
        if active_name and active_name not in workflows:
            errors.append(f"guides/taxonomy.json: active_status_workflow '{active_name}' is not defined in status_workflows")
        for name, workflow in workflows.items():
            if not isinstance(name, str) or not name.strip():
                errors.append("guides/taxonomy.json: status_workflows keys must be non-empty strings")
                continue
            if not isinstance(workflow, dict):
                errors.append(f"guides/taxonomy.json: status_workflows.{name} must be an object")
                continue
            unknown_workflow_fields = sorted(set(workflow) - {"status_values", "reading_stage_values", "review_stage_values"})
            if unknown_workflow_fields:
                errors.append(
                    f"guides/taxonomy.json: status_workflows.{name} has unknown keys: "
                    f"{', '.join(unknown_workflow_fields)}"
                )
            for field in ("status_values", "reading_stage_values", "review_stage_values"):
                validate_string_list(
                    workflow.get(field, []),
                    f"guides/taxonomy.json: status_workflows.{name}.{field}",
                    errors,
                    allow_none=False,
                )

    owners = config.get("research_line_owners", {})
    if owners is not None and owners != {} and not isinstance(owners, dict):
        errors.append("guides/taxonomy.json: research_line_owners must be an object")
    elif isinstance(owners, dict):
        for line, owner_config in owners.items():
            if not isinstance(line, str) or not line.strip():
                errors.append("guides/taxonomy.json: research_line_owners keys must be non-empty strings")
                continue
            if not isinstance(owner_config, dict):
                errors.append(f"guides/taxonomy.json: research_line_owners.{line} must be an object")
                continue
            unknown_owner_fields = sorted(set(owner_config) - {"owner", "team", "cadence", "note"})
            if unknown_owner_fields:
                errors.append(
                    f"guides/taxonomy.json: research_line_owners.{line} has unknown keys: "
                    f"{', '.join(unknown_owner_fields)}"
                )
            if not owner_config:
                errors.append(f"guides/taxonomy.json: research_line_owners.{line} must not be empty")
            for field in ("owner", "team", "cadence", "note"):
                value = owner_config.get(field)
                if value is not None and (not isinstance(value, str) or not value.strip()):
                    errors.append(f"guides/taxonomy.json: research_line_owners.{line}.{field} must be a non-empty string")

    label_definitions = config.get("label_definitions", {})
    allowed_definition_fields = {
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
    }
    if label_definitions is not None and label_definitions != {} and not isinstance(label_definitions, dict):
        errors.append("guides/taxonomy.json: label_definitions must be an object")
    elif isinstance(label_definitions, dict):
        unknown_definition_fields = sorted(set(label_definitions) - allowed_definition_fields)
        if unknown_definition_fields:
            errors.append(
                "guides/taxonomy.json: label_definitions has unknown fields: "
                f"{', '.join(unknown_definition_fields)}"
            )
        for field, values in label_definitions.items():
            if field not in allowed_definition_fields:
                continue
            if not isinstance(values, dict):
                errors.append(f"guides/taxonomy.json: label_definitions.{field} must be an object")
                continue
            for label, definition in values.items():
                if not isinstance(label, str) or not label.strip():
                    errors.append(f"guides/taxonomy.json: label_definitions.{field} keys must be non-empty strings")
                    continue
                if not isinstance(definition, dict):
                    errors.append(f"guides/taxonomy.json: label_definitions.{field}.{label} must be an object")
                    continue
                unknown_keys = sorted(set(definition) - {"description", "owner", "status", "note"})
                if unknown_keys:
                    errors.append(
                        f"guides/taxonomy.json: label_definitions.{field}.{label} has unknown keys: "
                        f"{', '.join(unknown_keys)}"
                    )
                if not definition:
                    errors.append(f"guides/taxonomy.json: label_definitions.{field}.{label} must not be empty")
                status = definition.get("status")
                if status is not None and status not in {"active", "watch", "deprecated"}:
                    errors.append(
                        f"guides/taxonomy.json: label_definitions.{field}.{label}.status must be one of active, watch, deprecated"
                    )
                for key in ("description", "owner", "note"):
                    value = definition.get(key)
                    if value is not None and (not isinstance(value, str) or not value.strip()):
                        errors.append(f"guides/taxonomy.json: label_definitions.{field}.{label}.{key} must be a non-empty string")

    shared_views = config.get("shared_views", [])
    if shared_views is not None and not isinstance(shared_views, list):
        errors.append("guides/taxonomy.json: shared_views must be a list")
    elif isinstance(shared_views, list):
        seen_names: set[str] = set()
        for index, view in enumerate(shared_views):
            if not isinstance(view, dict):
                errors.append(f"guides/taxonomy.json: shared_views[{index}] must be an object")
                continue
            name = view.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"guides/taxonomy.json: shared_views[{index}].name must be a non-empty string")
            else:
                normalized_name = name.strip().lower()
                if normalized_name in seen_names:
                    errors.append(f"guides/taxonomy.json: shared_views has duplicate name '{name}'")
                seen_names.add(normalized_name)
            page = view.get("page", "all")
            if page not in SHARED_VIEW_PAGES:
                errors.append(f"guides/taxonomy.json: shared_views[{index}].page must be one of all, index, library")
            state = view.get("state")
            if not isinstance(state, dict) or not state:
                errors.append(f"guides/taxonomy.json: shared_views[{index}].state must be a non-empty object")
                continue
            unknown_state = sorted(set(str(key) for key in state) - SHARED_VIEW_STATE_KEYS)
            if unknown_state:
                errors.append(
                    f"guides/taxonomy.json: shared_views[{index}].state has unknown keys: {', '.join(unknown_state)}"
                )

    policy = config.get("governance_policy", {})
    if policy is not None and policy != {} and not isinstance(policy, dict):
        errors.append("guides/taxonomy.json: governance_policy must be an object")
    elif isinstance(policy, dict):
        unknown_sections = sorted(set(policy) - set(GOVERNANCE_POLICY_FIELDS))
        if unknown_sections:
            errors.append(f"guides/taxonomy.json: governance_policy has unknown sections: {', '.join(unknown_sections)}")
        for section, fields in GOVERNANCE_POLICY_FIELDS.items():
            values = policy.get(section, {})
            if values is None or values == {}:
                continue
            if not isinstance(values, dict):
                errors.append(f"guides/taxonomy.json: governance_policy.{section} must be an object")
                continue
            unknown_keys = sorted(set(values) - set(fields))
            if unknown_keys:
                errors.append(
                    f"guides/taxonomy.json: governance_policy.{section} has unknown keys: {', '.join(unknown_keys)}"
                )
            for key, expected_type in fields.items():
                if key not in values:
                    continue
                value = values[key]
                if expected_type is int:
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(
                            f"guides/taxonomy.json: governance_policy.{section}.{key} must be a non-negative integer"
                        )
                elif not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    errors.append(
                        f"guides/taxonomy.json: governance_policy.{section}.{key} must be a non-negative number"
                    )
    return config


def validate_taxonomy_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "taxonomy.schema.json"
    if not schema_path.exists():
        warnings.append("guides/taxonomy.schema.json missing; editor schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/taxonomy.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/taxonomy.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/taxonomy.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/taxonomy.schema.json: type must be object")
    if not isinstance(schema.get("properties"), dict):
        errors.append("guides/taxonomy.schema.json: properties must be an object")
    if "status_workflows" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.status_workflows is required")
    if "shared_views" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.shared_views is required")
    if "research_line_owners" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.research_line_owners is required")
    if "label_definitions" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.label_definitions is required")
    if "governance_policy" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.governance_policy is required")


def validate_views_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "views.schema.json"
    if not schema_path.exists():
        warnings.append("guides/views.schema.json missing; external view-directory schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/views.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/views.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/views.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/views.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/views.schema.json: properties must be an object")
        properties = {}
    for key in ("views", "commands", "links"):
        if key not in properties:
            errors.append(f"guides/views.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/views.schema.json: $defs must be an object")
        defs = {}
    view_def = defs.get("view")
    if not isinstance(view_def, dict):
        errors.append("guides/views.schema.json: $defs.view is required")
        return
    required = set(view_def.get("required") or [])
    for key in ("id", "name", "source", "kind", "href", "state", "slugs", "shared_view", "empty"):
        if key not in required:
            errors.append(f"guides/views.schema.json: $defs.view.required missing {key}")
    view_properties = view_def.get("properties")
    if not isinstance(view_properties, dict):
        errors.append("guides/views.schema.json: $defs.view.properties must be an object")
        return
    source_enum = set((view_properties.get("source") or {}).get("enum") or [])
    if not {"configured", "system", "generated"}.issubset(source_enum):
        errors.append("guides/views.schema.json: source enum must include configured, system, generated")
    kind_enum = set((view_properties.get("kind") or {}).get("enum") or [])
    if not {"shared", "queue", "research_line", "workflow_status"}.issubset(kind_enum):
        errors.append("guides/views.schema.json: kind enum must include shared, queue, research_line, workflow_status")


def validate_facets_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "facets.schema.json"
    if not schema_path.exists():
        warnings.append("guides/facets.schema.json missing; external facet-directory schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/facets.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/facets.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/facets.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/facets.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/facets.schema.json: properties must be an object")
        properties = {}
    for key in ("fields", "values", "summary", "commands", "links"):
        if key not in properties:
            errors.append(f"guides/facets.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/facets.schema.json: $defs must be an object")
        defs = {}
    field_def = defs.get("facet_field")
    if not isinstance(field_def, dict):
        errors.append("guides/facets.schema.json: $defs.facet_field is required")
    else:
        field_required = set(field_def.get("required") or [])
        for key in ("field", "label", "query_key", "is_list", "used_count", "href"):
            if key not in field_required:
                errors.append(f"guides/facets.schema.json: $defs.facet_field.required missing {key}")
    value_def = defs.get("facet_value")
    if not isinstance(value_def, dict):
        errors.append("guides/facets.schema.json: $defs.facet_value is required")
        return
    value_required = set(value_def.get("required") or [])
    for key in ("field", "value", "count", "configured", "action", "severity", "sample_slugs", "recommendation"):
        if key not in value_required:
            errors.append(f"guides/facets.schema.json: $defs.facet_value.required missing {key}")
    value_properties = value_def.get("properties")
    if not isinstance(value_properties, dict):
        errors.append("guides/facets.schema.json: $defs.facet_value.properties must be an object")
        return
    action_enum = set((value_properties.get("action") or {}).get("enum") or [])
    if not {"stable", "watch", "merge_candidate", "split_candidate", "unused_config"}.issubset(action_enum):
        errors.append("guides/facets.schema.json: action enum must include stable, watch, merge_candidate, split_candidate, unused_config")
    severity_enum = set((value_properties.get("severity") or {}).get("enum") or [])
    if not {"none", "low", "medium", "high"}.issubset(severity_enum):
        errors.append("guides/facets.schema.json: severity enum must include none, low, medium, high")


def validate_batch_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "batch.schema.json"
    if not schema_path.exists():
        warnings.append("guides/batch.schema.json missing; external batch-planning schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/batch.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/batch.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/batch.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/batch.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/batch.schema.json: properties must be an object")
        properties = {}
    for key in ("dimensions", "summary", "batches", "top_batches", "links"):
        if key not in properties:
            errors.append(f"guides/batch.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/batch.schema.json: $defs must be an object")
        defs = {}
    dimension_def = defs.get("dimension")
    if not isinstance(dimension_def, dict):
        errors.append("guides/batch.schema.json: $defs.dimension is required")
    else:
        dimension_required = set(dimension_def.get("required") or [])
        for key in ("key", "label", "query", "multi", "paper_key"):
            if key not in dimension_required:
                errors.append(f"guides/batch.schema.json: $defs.dimension.required missing {key}")
    batch_def = defs.get("batch")
    if not isinstance(batch_def, dict):
        errors.append("guides/batch.schema.json: $defs.batch is required")
        return
    batch_required = set(batch_def.get("required") or [])
    for key in ("id", "dimension", "value", "count", "severity", "priority", "recommended_action", "href", "export_command", "slugs", "sample_slugs", "sample_titles"):
        if key not in batch_required:
            errors.append(f"guides/batch.schema.json: $defs.batch.required missing {key}")
    batch_properties = batch_def.get("properties")
    if not isinstance(batch_properties, dict):
        errors.append("guides/batch.schema.json: $defs.batch.properties must be an object")
        return
    severity_enum = set((batch_properties.get("severity") or {}).get("enum") or [])
    if not {"high", "medium", "low"}.issubset(severity_enum):
        errors.append("guides/batch.schema.json: severity enum must include high, medium, low")


def validate_actions_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "actions.schema.json"
    if not schema_path.exists():
        warnings.append("guides/actions.schema.json missing; external action-queue schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/actions.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/actions.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/actions.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/actions.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/actions.schema.json: properties must be an object")
        properties = {}
    for key in ("summary", "actions", "csv_columns", "commands", "links"):
        if key not in properties:
            errors.append(f"guides/actions.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/actions.schema.json: $defs must be an object")
        defs = {}
    action_def = defs.get("action")
    if not isinstance(action_def, dict):
        errors.append("guides/actions.schema.json: $defs.action is required")
        return
    action_required = set(action_def.get("required") or [])
    for key in ("id", "group", "severity", "priority", "title", "detail", "href", "source", "slugs", "command"):
        if key not in action_required:
            errors.append(f"guides/actions.schema.json: $defs.action.required missing {key}")
    action_properties = action_def.get("properties")
    if not isinstance(action_properties, dict):
        errors.append("guides/actions.schema.json: $defs.action.properties must be an object")
        return
    group_enum = set((action_properties.get("group") or {}).get("enum") or [])
    if not {"review", "freshness", "metadata", "quality", "taxonomy", "dedupe", "inbox"}.issubset(group_enum):
        errors.append("guides/actions.schema.json: group enum must include review, freshness, metadata, quality, taxonomy, dedupe, inbox")
    severity_enum = set((action_properties.get("severity") or {}).get("enum") or [])
    if not {"high", "medium", "low", "none"}.issubset(severity_enum):
        errors.append("guides/actions.schema.json: severity enum must include high, medium, low, none")


def validate_catalog_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "catalog.schema.json"
    if not schema_path.exists():
        warnings.append("guides/catalog.schema.json missing; external integration-catalog schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/catalog.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/catalog.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/catalog.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/catalog.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/catalog.schema.json: properties must be an object")
        properties = {}
    for key in ("pages", "data_resources", "contracts", "integration_recipes", "recommended_bootstrap_files"):
        if key not in properties:
            errors.append(f"guides/catalog.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/catalog.schema.json: $defs must be an object")
        defs = {}
    for def_name, required_keys in {
        "page": ("title", "href", "kind", "description"),
        "data_resource": ("href", "description", "exists", "top_level_keys", "collections", "consumers"),
        "contract": ("href", "description"),
        "integration_recipe": ("name", "command", "uses", "outputs"),
    }.items():
        item_def = defs.get(def_name)
        if not isinstance(item_def, dict):
            errors.append(f"guides/catalog.schema.json: $defs.{def_name} is required")
            continue
        required = set(item_def.get("required") or [])
        for key in required_keys:
            if key not in required:
                errors.append(f"guides/catalog.schema.json: $defs.{def_name}.required missing {key}")
    page_def = defs.get("page")
    if isinstance(page_def, dict):
        page_properties = page_def.get("properties")
        if not isinstance(page_properties, dict):
            errors.append("guides/catalog.schema.json: $defs.page.properties must be an object")
        else:
            kind_enum = set((page_properties.get("kind") or {}).get("enum") or [])
            if not {"view", "ops", "workflow", "analysis", "planning"}.issubset(kind_enum):
                errors.append("guides/catalog.schema.json: page kind enum must include view, ops, workflow, analysis, planning")


def validate_manifest_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "manifest.schema.json"
    if not schema_path.exists():
        warnings.append("guides/manifest.schema.json missing; external release-manifest schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/manifest.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/manifest.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/manifest.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/manifest.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/manifest.schema.json: properties must be an object")
        properties = {}
    for key in ("publish_ready", "publish_checks", "artifact_inventory", "command_recipes", "governance_playbooks", "commands"):
        if key not in properties:
            errors.append(f"guides/manifest.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/manifest.schema.json: $defs must be an object")
        defs = {}
    for def_name, required_keys in {
        "page": ("title", "href", "kind", "description"),
        "file_ref": ("href", "description"),
        "artifact": ("href", "kind", "description", "exists", "status"),
        "command_recipe": ("id", "kind", "label", "command", "mutates"),
        "governance_playbook": ("id", "label", "description", "steps"),
    }.items():
        item_def = defs.get(def_name)
        if not isinstance(item_def, dict):
            errors.append(f"guides/manifest.schema.json: $defs.{def_name} is required")
            continue
        required = set(item_def.get("required") or [])
        for key in required_keys:
            if key not in required:
                errors.append(f"guides/manifest.schema.json: $defs.{def_name}.required missing {key}")
    artifact_def = defs.get("artifact")
    if isinstance(artifact_def, dict):
        artifact_properties = artifact_def.get("properties")
        if not isinstance(artifact_properties, dict):
            errors.append("guides/manifest.schema.json: $defs.artifact.properties must be an object")
        else:
            status_enum = set((artifact_properties.get("status") or {}).get("enum") or [])
            if not {"ok", "missing", "generated_after_inventory"}.issubset(status_enum):
                errors.append("guides/manifest.schema.json: artifact status enum must include ok, missing, generated_after_inventory")
            kind_enum = set((artifact_properties.get("kind") or {}).get("enum") or [])
            if not {"page", "data", "contract"}.issubset(kind_enum):
                errors.append("guides/manifest.schema.json: artifact kind enum must include page, data, contract")


def validate_status_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "status.schema.json"
    if not schema_path.exists():
        warnings.append("guides/status.schema.json missing; external status-selector schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/status.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/status.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/status.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/status.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/status.schema.json: properties must be an object")
        properties = {}
    for key in ("workflows", "papers", "defaults", "links", "commands"):
        if key not in properties:
            errors.append(f"guides/status.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/status.schema.json: $defs must be an object")
        defs = {}
    workflow_def = defs.get("workflow")
    if not isinstance(workflow_def, dict):
        errors.append("guides/status.schema.json: $defs.workflow is required")
        return
    workflow_required = set(workflow_def.get("required") or [])
    for key in ("name", "active", "status_values", "reading_stage_values", "review_stage_values", "fields"):
        if key not in workflow_required:
            errors.append(f"guides/status.schema.json: $defs.workflow.required missing {key}")
    field_def = defs.get("status_field")
    if not isinstance(field_def, dict):
        errors.append("guides/status.schema.json: $defs.status_field is required")
        return
    field_properties = field_def.get("properties")
    if not isinstance(field_properties, dict):
        errors.append("guides/status.schema.json: $defs.status_field.properties must be an object")
        return
    field_enum = set((field_properties.get("field") or {}).get("enum") or [])
    if not {"status", "reading_stage", "review_stage"}.issubset(field_enum):
        errors.append("guides/status.schema.json: status field enum must include status, reading_stage, review_stage")
    paper_def = defs.get("status_paper")
    if not isinstance(paper_def, dict):
        errors.append("guides/status.schema.json: $defs.status_paper is required")
        return
    paper_required = set(paper_def.get("required") or [])
    for key in ("slug", "status", "reading_stage", "review_stage", "href"):
        if key not in paper_required:
            errors.append(f"guides/status.schema.json: $defs.status_paper.required missing {key}")


def validate_workflow_schema_contract(report_dir: Path, errors: list[str], warnings: list[str]) -> None:
    schema_path = report_dir / "guides" / "workflow.schema.json"
    if not schema_path.exists():
        warnings.append("guides/workflow.schema.json missing; external workflow-audit schema hints are unavailable")
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"guides/workflow.schema.json: invalid JSON: {exc}")
        return

    if not isinstance(schema, dict):
        errors.append("guides/workflow.schema.json: root must be an object")
        return
    if not isinstance(schema.get("$schema"), str) or not schema.get("$schema", "").strip():
        errors.append("guides/workflow.schema.json: $schema must be a non-empty string")
    if schema.get("type") != "object":
        errors.append("guides/workflow.schema.json: type must be object")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append("guides/workflow.schema.json: properties must be an object")
        properties = {}
    for key in ("workflows", "active_unconfigured", "shared_workflow_views", "recommendations", "commands"):
        if key not in properties:
            errors.append(f"guides/workflow.schema.json: properties.{key} is required")
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        errors.append("guides/workflow.schema.json: $defs must be an object")
        defs = {}
    workflow_def = defs.get("workflow")
    if not isinstance(workflow_def, dict):
        errors.append("guides/workflow.schema.json: $defs.workflow is required")
        return
    workflow_required = set(workflow_def.get("required") or [])
    for key in ("name", "active", "status_values", "reading_stage_values", "review_stage_values", "fields"):
        if key not in workflow_required:
            errors.append(f"guides/workflow.schema.json: $defs.workflow.required missing {key}")
    field_def = defs.get("status_field")
    if not isinstance(field_def, dict):
        errors.append("guides/workflow.schema.json: $defs.status_field is required")
        return
    field_properties = field_def.get("properties")
    if not isinstance(field_properties, dict):
        errors.append("guides/workflow.schema.json: $defs.status_field.properties must be an object")
        return
    field_enum = set((field_properties.get("field") or {}).get("enum") or [])
    if not {"status", "reading_stage", "review_stage"}.issubset(field_enum):
        errors.append("guides/workflow.schema.json: status field enum must include status, reading_stage, review_stage")
    if "unconfigured_value" not in defs:
        errors.append("guides/workflow.schema.json: $defs.unconfigured_value is required")
    if "shared_workflow_view" not in defs:
        errors.append("guides/workflow.schema.json: $defs.shared_workflow_view is required")


def validate_string_list(value: Any, label: str, errors: list[str], allow_none: bool) -> None:
    if value is None and allow_none:
        return
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label} values must be non-empty strings")
            continue
        normalized = item.strip().lower()
        if normalized in seen:
            errors.append(f"{label} has duplicate value '{item}'")
        seen.add(normalized)


def active_taxonomy_config(config: dict[str, Any]) -> dict[str, Any]:
    workflows = config.get("status_workflows") or {}
    active_name = str(config.get("active_status_workflow") or "").strip()
    if active_name and isinstance(workflows, dict) and isinstance(workflows.get(active_name), dict):
        merged = config.copy()
        merged.update(workflows[active_name])
        return merged
    return config


def configured_set(config: dict[str, Any], field: str) -> set[str]:
    values = config.get(field, [])
    if not isinstance(values, list):
        return set()
    return {value.strip() for value in values if isinstance(value, str) and value.strip()}


def validate_controlled_taxonomy(
    reports: dict[str, dict[str, Any]],
    config: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    strict: bool,
) -> None:
    config = active_taxonomy_config(config)
    controlled = {
        "status": configured_set(config, "status_values"),
        "reading_stage": configured_set(config, "reading_stage_values"),
        "review_stage": configured_set(config, "review_stage_values"),
        "line_role": configured_set(config, "role_order"),
    }
    sink = errors if strict else warnings
    for slug, meta in reports.items():
        for field, allowed in controlled.items():
            if not allowed:
                continue
            value = str(meta.get(field) or "").strip()
            if not value or value == "Unassigned" or value in allowed:
                continue
            allowed_text = ", ".join(sorted(allowed))
            message = f"{slug}: {field} '{value}' is not in guides/taxonomy.json ({allowed_text})"
            if not strict:
                message += "; run with --strict-taxonomy to fail on this drift"
            sink.append(message)


def validate_pages(report_dir: Path, reports: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for page in REQUIRED_PAGES:
        if not (report_dir / page).exists():
            errors.append(f"missing generated page {page}")

    for slug, meta in reports.items():
        line = str(meta.get("research_line") or "").strip()
        if line and line != "Unassigned":
            line_page = report_dir / "lines" / f"{slugify_label(line)}.html"
            if not line_page.exists():
                errors.append(f"{slug}: missing research line page {line_page.relative_to(report_dir)}")

    html_paths = sorted(report_dir.glob("*.html")) + sorted((report_dir / "lines").glob("*.html"))
    for html_path in html_paths:
        parser = LinkParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        for link in parser.links:
            if should_skip_link(link):
                continue
            target = (html_path.parent / link.split("#", 1)[0].split("?", 1)[0]).resolve()
            try:
                target.relative_to(report_dir.resolve())
            except ValueError:
                continue
            if not target.exists():
                errors.append(f"{html_path.relative_to(report_dir)}: broken local link {link}")


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def should_skip_link(link: str) -> bool:
    if not link or link.startswith("#"):
        return True
    lowered = link.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("data:")
        or lowered.startswith("javascript:")
    )


def main() -> int:
    args = parse_args()
    report_dir = Path(args.report_dir).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir = report_dir.resolve()

    errors: list[str] = []
    warnings: list[str] = []

    if not report_dir.exists():
        errors.append(f"report directory does not exist: {report_dir}")
    else:
        schema = load_metadata_schema(report_dir, errors, warnings)
        inbox_schema = load_inbox_schema(report_dir, errors, warnings)
        reports = validate_reports(report_dir, schema, errors, warnings)
        validate_taxonomy_schema_contract(report_dir, errors, warnings)
        validate_facets_schema_contract(report_dir, errors, warnings)
        validate_batch_schema_contract(report_dir, errors, warnings)
        validate_actions_schema_contract(report_dir, errors, warnings)
        validate_catalog_schema_contract(report_dir, errors, warnings)
        validate_manifest_schema_contract(report_dir, errors, warnings)
        validate_workflow_schema_contract(report_dir, errors, warnings)
        validate_status_schema_contract(report_dir, errors, warnings)
        validate_views_schema_contract(report_dir, errors, warnings)
        config = validate_taxonomy_config(report_dir, errors, warnings)
        validate_controlled_taxonomy(reports, config, errors, warnings, args.strict_taxonomy)
        validate_inbox_csv(report_dir, inbox_schema, errors, warnings)
        validate_json(report_dir, reports, errors)
        validate_pages(report_dir, reports, errors)

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        print(f"Wiki validation failed: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1

    print(f"Wiki validation passed for {len(paper_markdown_paths(report_dir))} papers in {report_dir}")
    if warnings:
        print(f"Warnings: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
