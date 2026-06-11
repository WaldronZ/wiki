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
    "library.html",
    "board.html",
    "workflow.html",
    "pivot.html",
    "compare.html",
    "taxonomy_map.html",
    "scale.html",
    "catalog.html",
    "inbox.html",
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
    "quality.json",
    "review.json",
    "freshness.json",
    "taxonomy_actions.json",
    "workflow.json",
    "pivot.json",
    "compare.json",
    "taxonomy_map.json",
    "scale.json",
    "catalog.json",
    "snapshot.json",
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
    workflow_path = report_dir / "workflow.json"
    pivot_path = report_dir / "pivot.json"
    compare_path = report_dir / "compare.json"
    taxonomy_map_path = report_dir / "taxonomy_map.json"
    scale_path = report_dir / "scale.json"
    catalog_path = report_dir / "catalog.json"
    stats_path = report_dir / "stats.json"
    inbox_path = report_dir / "inbox.json"
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
    if not workflow_path.exists():
        errors.append("missing workflow.json")
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
    if not scale_path.exists():
        errors.append("missing scale.json")
        return
    if not catalog_path.exists():
        errors.append("missing catalog.json")
        return
    if not stats_path.exists():
        errors.append("missing stats.json")
        return
    if not inbox_path.exists():
        errors.append("missing inbox.json")
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
    workflow_data = json.loads(workflow_path.read_text(encoding="utf-8"))
    pivot_data = json.loads(pivot_path.read_text(encoding="utf-8"))
    compare_data = json.loads(compare_path.read_text(encoding="utf-8"))
    taxonomy_map_data = json.loads(taxonomy_map_path.read_text(encoding="utf-8"))
    scale_data = json.loads(scale_path.read_text(encoding="utf-8"))
    catalog_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    stats_data = json.loads(stats_path.read_text(encoding="utf-8"))
    inbox_data = json.loads(inbox_path.read_text(encoding="utf-8"))
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
        for key in ("href", "description", "exists", "top_level_keys", "collections", "consumers"):
            if key not in item:
                errors.append(f"catalog.json data_resources[{index}] missing {key}")
        if not isinstance(item.get("collections"), list):
            errors.append(f"catalog.json data_resources[{index}].collections must be a list")
    catalog_contracts = catalog_data.get("contracts")
    if not isinstance(catalog_contracts, list):
        errors.append("catalog.json contracts must be a list")
        catalog_contracts = []
    catalog_contract_hrefs = {str(item.get("href") or "") for item in catalog_contracts if isinstance(item, dict)}
    if "guides/taxonomy.json" not in catalog_contract_hrefs:
        errors.append("catalog.json contracts missing guides/taxonomy.json")
    if not isinstance(catalog_data.get("integration_recipes"), list) or not catalog_data.get("integration_recipes"):
        errors.append("catalog.json integration_recipes must be a non-empty list")
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
    expected_contract_files = {"guides/metadata.schema.json", "guides/taxonomy.json"}
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
    if "governance_policy" not in (schema.get("properties") or {}):
        errors.append("guides/taxonomy.schema.json: properties.governance_policy is required")


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
