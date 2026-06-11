#!/usr/bin/env python3
"""Validate generated AutoPaperReader wiki artifacts.

The validator is intentionally standard-library only so it can run in CI or on
fresh clones before publishing a large paper library.
"""

from __future__ import annotations

import argparse
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

REQUIRED_PAGES = {
    "index.html",
    "library.html",
    "review.html",
    "dashboard.html",
    "taxonomy.html",
    "tags.html",
    "papers.json",
    "search_index.json",
    "quality.json",
    "review.json",
    "lines/index.html",
}

TAXONOMY_CONFIG_LIST_FIELDS = {
    "role_order",
    "status_values",
    "reading_stage_values",
    "review_stage_values",
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


def validate_reports(report_dir: Path, errors: list[str], warnings: list[str]) -> dict[str, dict[str, Any]]:
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

        missing = sorted(key for key in REQUIRED_META if key not in meta or is_empty(meta.get(key)))
        if missing:
            errors.append(f"{md_path.name}: missing required metadata: {', '.join(missing)}")

        for key in ("authors", "domains", "tracks", "problems", "topics", "methods"):
            if key in meta and not as_list(meta.get(key)):
                errors.append(f"{md_path.name}: metadata '{key}' must be a non-empty list")

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

    papers_data = json.loads(papers_path.read_text(encoding="utf-8"))
    search_data = json.loads(search_path.read_text(encoding="utf-8"))
    quality_data = json.loads(quality_path.read_text(encoding="utf-8"))
    review_data = json.loads(review_path.read_text(encoding="utf-8"))
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
    unknown_quality_slugs = sorted((quality_slugs | quality_issue_slugs) - report_slugs)
    if quality_data.get("count") != len(report_slugs):
        errors.append(f"quality.json count {quality_data.get('count')} != markdown report count {len(report_slugs)}")
    if unknown_quality_slugs:
        errors.append(f"quality.json references unknown slugs: {unknown_quality_slugs}")
    required_quality = {"quality_score", "coverage", "queues", "issues"}
    missing_quality = sorted(required_quality - set(quality_data))
    if missing_quality:
        errors.append(f"quality.json missing keys: {', '.join(missing_quality)}")

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

    known_fields = {"label_aliases", *TAXONOMY_CONFIG_LIST_FIELDS}
    unknown_fields = sorted(set(config) - known_fields)
    if unknown_fields:
        warnings.append(f"guides/taxonomy.json: unknown fields ignored: {', '.join(unknown_fields)}")

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
        values = config.get(field, [])
        if values is None:
            continue
        if not isinstance(values, list):
            errors.append(f"guides/taxonomy.json: {field} must be a list")
            continue
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"guides/taxonomy.json: {field} values must be non-empty strings")
                continue
            normalized = value.strip().lower()
            if normalized in seen:
                errors.append(f"guides/taxonomy.json: {field} has duplicate value '{value}'")
            seen.add(normalized)
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
        reports = validate_reports(report_dir, errors, warnings)
        config = validate_taxonomy_config(report_dir, errors, warnings)
        validate_controlled_taxonomy(reports, config, errors, warnings, args.strict_taxonomy)
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
