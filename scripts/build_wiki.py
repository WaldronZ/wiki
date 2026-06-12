#!/usr/bin/env python3
"""Build a lightweight paper wiki from markdown reports.

The script intentionally uses only the Python standard library so the paper
reader workflow can refresh the wiki after every newly generated report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import itertools
import json
import math
import re
import shlex
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"
GENERATED_FIXED_PATHS = (
    "papers.json",
    "search_index.json",
    "stats.json",
    "intake.json",
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
    "manifest.json",
    "index.html",
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
    "actions.html",
    "command.html",
    "snapshot.html",
    "collections.html",
    "balance.html",
    "coverage.html",
    "facets.html",
    "related.html",
    "taxonomy.html",
    "timeline.html",
    "matrix.html",
    "gaps.html",
    "tags.html",
    "lines/index.html",
)

ARXIV_RE = re.compile(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)")
URL_RE = re.compile(r"https?://[^\s\]\)<>\"']+")
KEYWORD_TOPICS = {
    "LLM": ["llm", "large language model", "大语言模型", "language model"],
    "Transformer": ["transformer", "self-attention", "attention"],
    "RAG": ["retrieval-augmented", "rag", "retrieval augmented", "检索增强"],
    "Reasoning": ["reasoning", "chain-of-thought", "cot", "推理"],
    "Alignment": ["alignment", "rlhf", "preference", "对齐"],
    "Multimodal": ["multimodal", "vision-language", "视觉语言", "多模态"],
    "Diffusion": ["diffusion", "score matching", "扩散模型"],
    "Agent": ["agent", "tool use", "工具调用"],
    "Efficient Training": ["efficient", "lora", "quantization", "蒸馏", "量化"],
}

DEFAULT_LABEL_ALIASES = {
    "attention kernel": "Attention Kernels",
    "diffusion language models": "Diffusion Language Models",
    "gpu kernel optimization": "GPU Kernel Optimization",
    "gpu systems": "GPU Systems",
    "inference optimization": "Inference Optimization",
    "kv cache": "KV Cache",
    "llm inference acceleration": "LLM Inference",
    "llm serving": "LLM Serving",
    "parallel decoding": "Parallel Decoding",
    "serving systems": "LLM Serving",
    "speculative decoding": "Speculative Decoding",
    "transformer": "Transformer",
}

DEFAULT_ROLE_ORDER = [
    "foundation",
    "baseline",
    "main",
    "system",
    "variant",
    "followup",
    "survey",
]

DEFAULT_STATUS_VALUES = ["unread", "skimmed", "reading", "read", "archived"]
DEFAULT_READING_STAGE_VALUES = ["skim", "normal_read", "deep_read", "code_checked"]
DEFAULT_REVIEW_STAGE_VALUES = ["fresh", "due", "reviewed"]
DEFAULT_GOVERNANCE_POLICY: dict[str, Any] = {
    "taxonomy_load": {
        "min_structure_labels": 3,
        "min_tags": 3,
        "max_tags": 10,
        "max_methods": 8,
    },
    "taxonomy_actions": {
        "singleton_max_count": 1,
        "watch_share": 0.4,
        "watch_min_count": 4,
        "split_share": 0.6,
        "split_min_count": 5,
    },
    "taxonomy_balance": {
        "high_score_below": 45,
        "medium_score_below": 70,
        "singleton_medium_count": 3,
        "unused_medium_count": 3,
    },
    "coverage": {
        "high_score_below": 70,
        "medium_score_below": 90,
        "missing_high_min": 2,
    },
}
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

LABEL_ALIASES = DEFAULT_LABEL_ALIASES.copy()
ROLE_ORDER = {role: index for index, role in enumerate(DEFAULT_ROLE_ORDER)}
STATUS_VALUES = DEFAULT_STATUS_VALUES.copy()
READING_STAGE_VALUES = DEFAULT_READING_STAGE_VALUES.copy()
REVIEW_STAGE_VALUES = DEFAULT_REVIEW_STAGE_VALUES.copy()
STATUS_WORKFLOWS: dict[str, dict[str, list[str]]] = {}
SHARED_VIEWS: list[dict[str, Any]] = []
ACTIVE_STATUS_WORKFLOW = ""
GOVERNANCE_POLICY: dict[str, Any] = json.loads(json.dumps(DEFAULT_GOVERNANCE_POLICY))
RESEARCH_LINE_OWNERS: dict[str, dict[str, str]] = {}
LABEL_DEFINITIONS: dict[str, dict[str, dict[str, str]]] = {}
QUICK_OPEN_PAPERS: list[dict[str, str]] = []
TAXONOMY_LABEL_FIELDS = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build docs/index.html and docs/papers.json")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing <slug>.md and <slug>.html reports.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated wiki artifacts are up to date without leaving file changes behind.",
    )
    return parser.parse_args()


def load_taxonomy_config(report_dir: Path) -> None:
    """Load optional taxonomy normalization config for this report directory."""
    global LABEL_ALIASES, ROLE_ORDER, STATUS_VALUES, READING_STAGE_VALUES, REVIEW_STAGE_VALUES, STATUS_WORKFLOWS, SHARED_VIEWS, ACTIVE_STATUS_WORKFLOW, GOVERNANCE_POLICY, RESEARCH_LINE_OWNERS, LABEL_DEFINITIONS

    LABEL_ALIASES = DEFAULT_LABEL_ALIASES.copy()
    ROLE_ORDER = {role: index for index, role in enumerate(DEFAULT_ROLE_ORDER)}
    STATUS_VALUES = DEFAULT_STATUS_VALUES.copy()
    READING_STAGE_VALUES = DEFAULT_READING_STAGE_VALUES.copy()
    REVIEW_STAGE_VALUES = DEFAULT_REVIEW_STAGE_VALUES.copy()
    STATUS_WORKFLOWS = {}
    SHARED_VIEWS = []
    ACTIVE_STATUS_WORKFLOW = ""
    GOVERNANCE_POLICY = json.loads(json.dumps(DEFAULT_GOVERNANCE_POLICY))
    RESEARCH_LINE_OWNERS = {}
    LABEL_DEFINITIONS = {}

    config_path = report_dir / "guides" / "taxonomy.json"
    if not config_path.exists():
        return

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid taxonomy config {config_path}: {exc}") from exc

    aliases = config.get("label_aliases") or {}
    if isinstance(aliases, dict):
        LABEL_ALIASES.update(
            {
                str(alias).strip().lower(): str(canonical).strip()
                for alias, canonical in aliases.items()
                if str(alias).strip() and str(canonical).strip()
            }
        )

    role_order = config.get("role_order") or []
    if isinstance(role_order, list) and role_order:
        ROLE_ORDER = {
            str(role).strip(): index
            for index, role in enumerate(role_order)
            if str(role).strip()
        }

    workflow_name, workflow_config = configured_status_workflow(config)
    ACTIVE_STATUS_WORKFLOW = workflow_name
    STATUS_VALUES = configured_values(workflow_config, "status_values", DEFAULT_STATUS_VALUES)
    READING_STAGE_VALUES = configured_values(workflow_config, "reading_stage_values", DEFAULT_READING_STAGE_VALUES)
    REVIEW_STAGE_VALUES = configured_values(workflow_config, "review_stage_values", DEFAULT_REVIEW_STAGE_VALUES)
    STATUS_WORKFLOWS = configured_status_workflows(config)
    current_workflow_name = ACTIVE_STATUS_WORKFLOW or "default"
    STATUS_WORKFLOWS.setdefault(
        current_workflow_name,
        {
            "status_values": STATUS_VALUES.copy(),
            "reading_stage_values": READING_STAGE_VALUES.copy(),
            "review_stage_values": REVIEW_STAGE_VALUES.copy(),
        },
    )
    SHARED_VIEWS = configured_shared_views(config)
    GOVERNANCE_POLICY = configured_governance_policy(config)
    RESEARCH_LINE_OWNERS = configured_research_line_owners(config)
    LABEL_DEFINITIONS = configured_label_definitions(config)


def configured_values(config: dict[str, Any], key: str, defaults: list[str]) -> list[str]:
    values = config.get(key)
    if not isinstance(values, list) or not values:
        return defaults.copy()
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return cleaned or defaults.copy()


def configured_status_workflow(config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    workflows = config.get("status_workflows") or {}
    active_name = str(config.get("active_status_workflow") or "").strip()
    if active_name and isinstance(workflows, dict):
        active_workflow = workflows.get(active_name)
        if isinstance(active_workflow, dict):
            merged = config.copy()
            merged.update(active_workflow)
            return active_name, merged
    return active_name, config


def configured_status_workflows(config: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    workflows = config.get("status_workflows") or {}
    if not isinstance(workflows, dict):
        return {}
    cleaned: dict[str, dict[str, list[str]]] = {}
    for name, workflow in workflows.items():
        workflow_name = str(name).strip()
        if not workflow_name or not isinstance(workflow, dict):
            continue
        merged = config.copy()
        merged.update(workflow)
        cleaned[workflow_name] = {
            "status_values": configured_values(merged, "status_values", DEFAULT_STATUS_VALUES),
            "reading_stage_values": configured_values(merged, "reading_stage_values", DEFAULT_READING_STAGE_VALUES),
            "review_stage_values": configured_values(merged, "review_stage_values", DEFAULT_REVIEW_STAGE_VALUES),
        }
    return cleaned


def configured_shared_views(config: dict[str, Any]) -> list[dict[str, Any]]:
    views = config.get("shared_views") or []
    if not isinstance(views, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for view in views:
        if not isinstance(view, dict):
            continue
        name = str(view.get("name") or "").strip()
        state = view.get("state") or {}
        page = str(view.get("page") or "all").strip()
        if not name or page not in VIEW_PAGES or not isinstance(state, dict):
            continue
        normalized_state = {
            str(key): str(value)
            for key, value in state.items()
            if str(key) in VIEW_STATE_KEYS and str(value).strip()
        }
        if normalized_state:
            cleaned.append({"name": name, "page": page, "state": normalized_state})
    return cleaned


def configured_governance_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = json.loads(json.dumps(DEFAULT_GOVERNANCE_POLICY))
    overrides = config.get("governance_policy") or {}
    if not isinstance(overrides, dict):
        return policy
    for section, defaults in DEFAULT_GOVERNANCE_POLICY.items():
        section_overrides = overrides.get(section) or {}
        if not isinstance(section_overrides, dict):
            continue
        for key, default in defaults.items():
            value = section_overrides.get(key)
            if isinstance(default, int) and isinstance(value, int) and value >= 0:
                policy[section][key] = value
            elif isinstance(default, float) and isinstance(value, (int, float)) and value >= 0:
                policy[section][key] = float(value)
    return policy


def configured_research_line_owners(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    owners = config.get("research_line_owners") or {}
    if not isinstance(owners, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for line, owner_config in owners.items():
        line_name = str(line).strip()
        if not line_name or not isinstance(owner_config, dict):
            continue
        item = {
            key: str(owner_config.get(key) or "").strip()
            for key in ("owner", "team", "cadence", "note")
            if str(owner_config.get(key) or "").strip()
        }
        if item:
            cleaned[line_name] = item
    return cleaned


def configured_label_definitions(config: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    definitions = config.get("label_definitions") or {}
    if not isinstance(definitions, dict):
        return {}
    cleaned: dict[str, dict[str, dict[str, str]]] = {}
    for field, values in definitions.items():
        field_name = str(field).strip()
        if field_name not in TAXONOMY_LABEL_FIELDS or not isinstance(values, dict):
            continue
        field_items: dict[str, dict[str, str]] = {}
        for label, definition in values.items():
            label_name = normalize_label(str(label or "").strip())
            if not label_name or not isinstance(definition, dict):
                continue
            item = {
                key: str(definition.get(key) or "").strip()
                for key in ("description", "owner", "status", "note")
                if str(definition.get(key) or "").strip()
            }
            if item:
                field_items[label_name] = item
        if field_items:
            cleaned[field_name] = field_items
    return cleaned


def label_definition(field: str, value: str) -> dict[str, str]:
    label = normalize_label(str(value or "").strip())
    if not label:
        return {}
    return LABEL_DEFINITIONS.get(field, {}).get(label, {}).copy()


def research_line_owner(line: str) -> dict[str, str]:
    return RESEARCH_LINE_OWNERS.get(str(line or "").strip(), {})


def shared_views_for(page: str) -> list[dict[str, Any]]:
    return [
        {"name": view["name"], "state": view["state"]}
        for view in SHARED_VIEWS
        if view.get("page") in {"all", page}
    ]


def control_options() -> dict[str, Any]:
    workflow_name = ACTIVE_STATUS_WORKFLOW or "default"
    status_workflows = STATUS_WORKFLOWS or {
        workflow_name: {
            "status_values": STATUS_VALUES.copy(),
            "reading_stage_values": READING_STAGE_VALUES.copy(),
            "review_stage_values": REVIEW_STAGE_VALUES.copy(),
        }
    }
    return {
        "active_status_workflow": ACTIVE_STATUS_WORKFLOW,
        "status": STATUS_VALUES.copy(),
        "reading_stage": READING_STAGE_VALUES.copy(),
        "review_stage": REVIEW_STAGE_VALUES.copy(),
        "status_workflows": {
            name: {
                "status_values": values.get("status_values", []).copy(),
                "reading_stage_values": values.get("reading_stage_values", []).copy(),
                "review_stage_values": values.get("review_stage_values", []).copy(),
            }
            for name, values in status_workflows.items()
        },
        "line_role": list(ROLE_ORDER.keys()),
        "shared_views": SHARED_VIEWS.copy(),
        "governance_policy": json.loads(json.dumps(GOVERNANCE_POLICY)),
        "research_line_owners": json.loads(json.dumps(RESEARCH_LINE_OWNERS)),
        "label_definitions": json.loads(json.dumps(LABEL_DEFINITIONS)),
    }


def split_cell_list(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    delimiter = ";" if ";" in text else "|" if "|" in text else ","
    return [item.strip() for item in text.split(delimiter) if item.strip()]


def normalize_inbox_status(value: str) -> str:
    status = str(value or "").strip().lower()
    return status or "queued"


def normalize_inbox_priority(value: str) -> str:
    priority = str(value or "").strip().lower()
    return priority or "normal"


def load_inbox_items(report_dir: Path, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inbox_path = report_dir / "inbox.csv"
    if not inbox_path.exists():
        return []

    known_arxiv_ids = {
        str(paper.get("arxiv_id") or "").split("v")[0].strip()
        for paper in papers
        if paper.get("arxiv_id")
    }
    known_links = {
        str(paper.get(key) or "").strip()
        for paper in papers
        for key in ("arxiv_url", "html_path", "md_path", "code_url")
        if paper.get(key)
    }
    known_titles = {
        str(paper.get(key) or "").strip().lower()
        for paper in papers
        for key in ("title", "title_zh", "title_en")
        if paper.get(key)
    }

    rows: list[dict[str, Any]] = []
    with inbox_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, raw in enumerate(reader, start=1):
            item = {str(key or "").strip(): str(value or "").strip() for key, value in raw.items()}
            title = item.get("title") or item.get("name") or item.get("paper") or ""
            link = item.get("link") or item.get("url") or item.get("arxiv_url") or ""
            arxiv_id = item.get("arxiv_id") or ""
            if not arxiv_id and link:
                match = ARXIV_RE.search(link)
                if match:
                    arxiv_id = match.group(1)
            if not title and not link and not arxiv_id:
                continue
            duplicate = bool(
                (arxiv_id and arxiv_id.split("v")[0] in known_arxiv_ids)
                or (link and link in known_links)
                or (title and title.lower() in known_titles)
            )
            rows.append(
                {
                    "id": item.get("id") or f"inbox-{index}",
                    "title": title or arxiv_id or link,
                    "link": link,
                    "arxiv_id": arxiv_id,
                    "status": normalize_inbox_status(item.get("status") or ""),
                    "priority": normalize_inbox_priority(item.get("priority") or ""),
                    "tags": split_cell_list(item.get("tags") or item.get("topics") or ""),
                    "note": item.get("note") or item.get("notes") or "",
                    "added_at": item.get("added_at") or item.get("created_at") or "",
                    "duplicate": duplicate,
                }
            )
    return rows


def inbox_counts(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(str(item.get(field) or "").strip() for item in items)
    counter.pop("", None)
    return dict(sorted(counter.items(), key=lambda pair: (-pair[1], pair[0].lower())))


def write_inbox_json(report_dir: Path, items: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(items),
        "statuses": inbox_counts(items, "status"),
        "priorities": inbox_counts(items, "priority"),
        "duplicates": [item["id"] for item in items if item.get("duplicate")],
        "items": items,
    }
    (report_dir / "inbox.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dedupe_paper_payload(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or "",
        "title_zh": paper.get("title_zh") or paper.get("title") or "",
        "arxiv_id": paper.get("arxiv_id") or "",
        "href": paper.get("html_path") or paper.get("md_path") or f"{paper['slug']}.html",
        "research_line": paper.get("research_line") or "Unassigned",
        "status": paper.get("status") or "",
        "year": paper.get("year") or "",
        "importance": paper.get("importance") or "",
        "has_code": bool(paper.get("has_code")),
    }


def dedupe_item_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id") or "",
        "title": item.get("title") or item.get("arxiv_id") or item.get("link") or "Untitled",
        "link": item.get("link") or "",
        "arxiv_id": item.get("arxiv_id") or "",
        "status": item.get("status") or "",
        "priority": item.get("priority") or "",
        "tags": item.get("tags") or [],
        "note": item.get("note") or "",
        "added_at": item.get("added_at") or "",
        "duplicate": bool(item.get("duplicate")),
    }


def dedupe_indexes(papers: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    indexes: dict[str, dict[str, dict[str, Any]]] = {
        "arxiv_id": {},
        "link": {},
        "title": {},
    }
    for paper in papers:
        arxiv_id = str(paper.get("arxiv_id") or "").split("v")[0].strip().lower()
        if arxiv_id:
            indexes["arxiv_id"][arxiv_id] = paper
        for key in ("arxiv_url", "html_path", "md_path", "code_url"):
            link = str(paper.get(key) or "").strip().rstrip("/").lower()
            if link:
                indexes["link"][link] = paper
        for key in ("title", "title_zh", "title_en"):
            title_key = normalize_intake_key(str(paper.get(key) or ""))
            if title_key:
                indexes["title"][title_key] = paper
    return indexes


def dedupe_match_papers(item: dict[str, Any], indexes: dict[str, dict[str, dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
    arxiv_id = str(item.get("arxiv_id") or "").split("v")[0].strip().lower()
    link = str(item.get("link") or "").strip().rstrip("/").lower()
    title_key = normalize_intake_key(str(item.get("title") or ""))
    matches: dict[str, dict[str, Any]] = {}
    reason = ""
    for candidate_reason, candidate_key in (("arxiv_id", arxiv_id), ("link", link), ("title", title_key)):
        if candidate_key and candidate_key in indexes[candidate_reason]:
            paper = indexes[candidate_reason][candidate_key]
            matches[paper["slug"]] = paper
            reason = reason or candidate_reason
    return reason, [matches[slug] for slug in sorted(matches)]


def build_dedupe_report(papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    report_groups = []
    seen_report_sets: set[tuple[str, ...]] = set()
    for index, group in enumerate(quality["duplicate_reports"], start=1):
        slugs = tuple(sorted(str(slug) for slug in group.get("slugs", [])))
        if slugs in seen_report_sets:
            continue
        seen_report_sets.add(slugs)
        report_groups.append(
            {
                "id": f"report-{len(report_groups) + 1}",
                "scope": "library",
                "kind": group.get("reason") or "unknown",
                "key": group.get("value") or "",
                "count": len(slugs),
                "severity": "high",
                "slugs": list(slugs),
                "papers": [dedupe_paper_payload(paper) for paper in group.get("papers", [])],
                "item_ids": [],
                "items": [],
                "matched_slugs": list(slugs),
                "recommended_action": "保留主报告，合并补充内容后删除或重命名重复报告。",
                "href": "quality.html",
            }
        )

    indexes = dedupe_indexes(papers)
    inbox_groups: list[dict[str, Any]] = []
    seen_inbox_group_ids: set[str] = set()
    for item in inbox_items:
        reason, matched = dedupe_match_papers(item, indexes)
        if not matched and not item.get("duplicate"):
            continue
        group_key = (
            str(item.get("arxiv_id") or "").split("v")[0].strip().lower()
            or str(item.get("link") or "").strip().rstrip("/").lower()
            or normalize_intake_key(str(item.get("title") or ""))
            or str(item.get("id") or "")
        )
        group_id = f"inbox-library-{reason or 'known'}-{normalized_duplicate_key(group_key)}"
        if group_id in seen_inbox_group_ids:
            continue
        seen_inbox_group_ids.add(group_id)
        inbox_groups.append(
            {
                "id": group_id,
                "scope": "inbox",
                "kind": f"library_{reason or 'duplicate'}",
                "key": group_key,
                "count": 1 + len(matched),
                "severity": "medium",
                "slugs": [paper["slug"] for paper in matched],
                "papers": [dedupe_paper_payload(paper) for paper in matched],
                "item_ids": [item.get("id") or ""],
                "items": [dedupe_item_payload(item)],
                "matched_slugs": [paper["slug"] for paper in matched],
                "recommended_action": "若候选已在库中，标记为跳过；若只是同题不同版本，把备注合并到已有报告。",
                "href": "inbox.html",
            }
        )

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in inbox_items:
        candidates = {
            "arxiv_id": str(item.get("arxiv_id") or "").split("v")[0].strip().lower(),
            "link": str(item.get("link") or "").strip().rstrip("/").lower(),
            "title": normalize_intake_key(str(item.get("title") or "")),
        }
        for kind, value in candidates.items():
            if value:
                buckets[(kind, value)].append(item)
    for (kind, value), items in sorted(buckets.items(), key=lambda pair: (pair[0][0], pair[0][1])):
        unique = {str(item.get("id") or ""): item for item in items}
        if len(unique) <= 1:
            continue
        item_ids = sorted(unique)
        group_id = f"inbox-self-{kind}-{normalized_duplicate_key(value)}"
        inbox_groups.append(
            {
                "id": group_id,
                "scope": "inbox",
                "kind": f"inbox_{kind}",
                "key": value,
                "count": len(item_ids),
                "severity": "medium",
                "slugs": [],
                "papers": [],
                "item_ids": item_ids,
                "items": [dedupe_item_payload(unique[item_id]) for item_id in item_ids],
                "matched_slugs": [],
                "recommended_action": "保留一个候选项，把其余备注合并后从 inbox.csv 移除。",
                "href": "inbox.html",
            }
        )

    all_groups = report_groups + inbox_groups
    severity_counts = Counter(group["severity"] for group in all_groups)
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "inbox_count": len(inbox_items),
        "duplicate_report_count": len(report_groups),
        "inbox_duplicate_count": len(inbox_groups),
        "group_count": len(all_groups),
        "report_groups": report_groups,
        "inbox_groups": inbox_groups,
        "summary": {
            "high": severity_counts.get("high", 0),
            "medium": severity_counts.get("medium", 0),
            "low": severity_counts.get("low", 0),
            "clean_reports": len(report_groups) == 0,
            "clean_inbox": len(inbox_groups) == 0,
        },
        "csv_columns": ["scope", "kind", "key", "severity", "count", "slugs", "item_ids", "recommended_action"],
        "commands": [
            "python3 scripts/check_quality.py docs",
            "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv",
            "python3 scripts/apply_library_metadata.py docs --input <dedupe_patch.csv>",
            "python3 scripts/apply_inbox_items.py docs --input <candidate_csv> --write",
        ],
        "links": {
            "quality": "quality.html",
            "inbox": "inbox.html",
            "actions": "actions.html",
            "library": "library.html",
        },
    }


def write_dedupe_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_dedupe_report(papers, inbox_items)
    (report_dir / "dedupe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_intake_key(value: str) -> str:
    text = str(value or "").lower()
    text = URL_RE.sub(" ", text)
    text = ARXIV_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_intake_link(value: str) -> str:
    return str(value or "").strip().rstrip("/").lower()


def intake_arxiv_key(value: str) -> str:
    match = ARXIV_RE.search(str(value or ""))
    return match.group(1) if match else ""


def intake_existing_paper(paper: dict[str, Any]) -> dict[str, Any]:
    title_values = [
        str(paper.get(key) or "")
        for key in ("title", "title_zh", "title_en")
        if paper.get(key)
    ]
    links = [
        str(paper.get(key) or "")
        for key in ("arxiv_url", "html_path", "md_path", "code_url")
        if paper.get(key)
    ]
    arxiv_id = str(paper.get("arxiv_id") or "")
    if arxiv_id:
        links.append(f"https://arxiv.org/abs/{arxiv_id}")
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or paper["slug"],
        "title_zh": paper.get("title_zh") or "",
        "title_en": paper.get("title_en") or "",
        "arxiv_id": arxiv_id,
        "arxiv_key": arxiv_id.split("v")[0] if arxiv_id else "",
        "title_keys": sorted({normalize_intake_key(value) for value in title_values if normalize_intake_key(value)}),
        "link_keys": sorted({normalize_intake_link(value) for value in links if normalize_intake_link(value)}),
        "href": paper_href(paper),
        "research_line": paper.get("research_line") or "Unassigned",
        "status": paper.get("status") or "",
        "year": paper.get("year") or "",
    }


def intake_existing_inbox_item(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or "")
    link = str(item.get("link") or "")
    arxiv_id = str(item.get("arxiv_id") or intake_arxiv_key(link))
    return {
        "id": item.get("id") or "",
        "title": title,
        "link": link,
        "arxiv_id": arxiv_id,
        "arxiv_key": arxiv_id.split("v")[0] if arxiv_id else "",
        "title_key": normalize_intake_key(title),
        "link_key": normalize_intake_link(link),
        "status": item.get("status") or "queued",
        "priority": item.get("priority") or "normal",
        "tags": item.get("tags") or [],
        "duplicate": bool(item.get("duplicate")),
    }


def build_intake_payload(papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    csv_columns = ["title", "link", "status", "priority", "tags", "note", "added_at"]
    today = dt.date.today().isoformat()
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "inbox_count": len(inbox_items),
        "existing_papers": [intake_existing_paper(paper) for paper in papers],
        "inbox_items": [intake_existing_inbox_item(item) for item in inbox_items],
        "csv_columns": csv_columns,
        "defaults": {
            "status": "queued",
            "priority": "normal",
            "tags": "",
            "note": "",
            "added_at": today,
        },
        "statuses": ["new_candidate", "library_duplicate", "inbox_duplicate", "paste_duplicate"],
        "patterns": {
            "arxiv_id": ARXIV_RE.pattern,
            "url": URL_RE.pattern,
        },
        "examples": [
            "https://arxiv.org/abs/1706.03762",
            "2307.08691 FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning",
            "Paper title | https://arxiv.org/abs/0000.00000",
        ],
        "commands": [
            "python3 scripts/apply_inbox_items.py docs --input <candidate_inbox.csv>",
            "python3 scripts/apply_inbox_items.py docs --input <candidate_inbox.csv> --write",
            "python3 scripts/build_wiki.py docs",
        ],
        "links": {
            "inbox": "inbox.html",
            "routing": "routing.html",
            "quality": "quality.html",
            "schema": "guides/inbox.schema.json",
        },
    }


def write_intake_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_intake_payload(papers, inbox_items)
    (report_dir / "intake.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    """Parse a small frontmatter subset: scalars and indented dash lists."""
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


def as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def normalize_label(label: str) -> str:
    label = re.sub(r"\s+", " ", str(label).strip())
    if not label:
        return ""
    return LABEL_ALIASES.get(label.lower(), label)


def normalize_labels(labels: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for label in labels:
        normalized = normalize_label(label)
        if normalized:
            seen.setdefault(normalized.lower(), normalized)
    return sorted(seen.values(), key=str.lower)


def infer_list_field(meta: dict[str, Any], key: str) -> list[str]:
    return normalize_labels(as_list(meta.get(key)))


def first_match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def infer_title(body: str, meta: dict[str, Any], slug: str) -> tuple[str, str, str]:
    raw_title = str(meta.get("title") or "").strip()
    if not raw_title:
        raw_title = first_match(r"^#\s+(.+?)\s*$", body, re.MULTILINE) or slug

    title_zh = str(meta.get("title_zh") or "").strip()
    title_en = str(meta.get("title_en") or "").strip()

    if not title_zh and not title_en:
        match = re.match(r"(.+?)[（(](.+?)[）)]$", raw_title)
        if match:
            title_zh = match.group(1).strip()
            title_en = match.group(2).strip()
        else:
            title_zh = raw_title

    return raw_title, title_zh or raw_title, title_en


def infer_arxiv_id(slug: str, body: str, meta: dict[str, Any]) -> str:
    if meta.get("arxiv_id"):
        return str(meta["arxiv_id"]).strip()
    if slug != "index":
        match = ARXIV_RE.search(slug)
        if match:
            return match.group(1)
    match = ARXIV_RE.search(body)
    return match.group(1) if match else ""


def infer_year(arxiv_id: str, body: str, meta: dict[str, Any]) -> int | None:
    if meta.get("year"):
        try:
            return int(str(meta["year"]))
        except ValueError:
            pass
    if arxiv_id:
        yy = int(arxiv_id[:2])
        current_yy = dt.datetime.now().year % 100
        return 2000 + yy if yy <= current_yy else 1900 + yy
    match = re.search(r"\b(19\d{2}|20\d{2})\b", body)
    return int(match.group(1)) if match else None


def infer_url(body: str, arxiv_id: str, meta: dict[str, Any], key: str) -> str:
    if meta.get(key):
        return str(meta[key]).strip()
    if key == "arxiv_url" and arxiv_id:
        return f"https://arxiv.org/abs/{arxiv_id}"
    urls = URL_RE.findall(body)
    if key == "code_url":
        for url in urls:
            if "github.com" in url.lower() or "gitlab.com" in url.lower():
                return url.rstrip(".,;")
    return ""


def infer_authors(body: str, meta: dict[str, Any]) -> list[str]:
    authors = as_list(meta.get("authors"))
    if authors:
        return authors
    line = first_match(r"(?im)^\s*[-*]?\s*(?:作者|Authors?)[:：]\s*(.+)$", body)
    if not line:
        return []
    return [part.strip() for part in re.split(r"[,，、;/；]| and ", line) if part.strip()]


def infer_topics(body: str, meta: dict[str, Any]) -> list[str]:
    topics = as_list(meta.get("topics")) + as_list(meta.get("tags"))
    if topics:
        return normalize_labels(topics)
    lowered = body.lower()
    inferred = []
    for topic, needles in KEYWORD_TOPICS.items():
        if any(needle.lower() in lowered for needle in needles):
            inferred.append(topic)
    return normalize_labels(inferred or ["Uncategorized"])


def infer_methods(meta: dict[str, Any]) -> list[str]:
    return infer_list_field(meta, "methods")


def infer_research_line(meta: dict[str, Any]) -> str:
    value = str(meta.get("research_line") or "").strip()
    return normalize_label(value) if value else "Unassigned"


def infer_excerpt(body: str, meta: dict[str, Any]) -> str:
    if meta.get("summary"):
        return str(meta["summary"]).strip()
    contribution = first_match(
        r"(?s)^##\s*(?:2\.\s*)?核心贡献概述\s*(.+?)(?:\n##\s|\Z)",
        body,
        re.MULTILINE,
    )
    source = contribution or body
    lines = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "---")):
            continue
        line = re.sub(r"^[-*]\s*", "", line)
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
        if len(" ".join(lines)) > 160:
            break
    excerpt = " ".join(lines)
    return excerpt[:220] + ("..." if len(excerpt) > 220 else "")


def markdown_to_search_text(body: str) -> str:
    text = re.sub(r"(?s)<div class=\"math-display\">.*?</div>", " ", body)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[`*_>#|\\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def infer_essence(body: str, meta: dict[str, Any]) -> str:
    if meta.get("essence"):
        return str(meta["essence"]).strip()
    section = first_match(
        r"(?s)^##\s*(?:3\.\s*)?一句话精髓(?:（写给外行）)?\s*(.+?)(?:\n##\s|\Z)",
        body,
        re.MULTILINE,
    )
    for raw in section.splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            return re.sub(r"^[-*]\s*", "", line)
    return ""


def reading_time_minutes(body: str) -> int:
    text = markdown_to_search_text(body)
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9_./+-]+", text))
    units = cjk_chars + latin_words
    return max(1, round(units / 650))


def public_paper(paper: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in paper.items() if not key.startswith("_")}


def slugify_label(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def paper_href(paper: dict[str, Any], prefix: str = "") -> str:
    return prefix + (paper["html_path"] or paper["md_path"])


def page_query_href(page: str, **params: str) -> str:
    clean = {key: value for key, value in params.items() if value}
    query = urlencode(clean)
    return f"{page}?{query}" if query else page


def list_has(values: Any, expected: str) -> bool:
    return expected in [str(value) for value in (values or [])]


def matches_view_state(paper: dict[str, Any], state: dict[str, Any], today: str | None = None) -> bool:
    today = today or dt.date.today().isoformat()
    for key, raw_value in state.items():
        value = str(raw_value or "").strip()
        if not value or key in {"sort", "size", "page"}:
            continue
        if key == "q":
            haystack = " ".join(
                str(part)
                for part in [
                    paper.get("slug"),
                    paper.get("title"),
                    paper.get("title_zh"),
                    paper.get("title_en"),
                    paper.get("arxiv_id"),
                    paper.get("excerpt"),
                    paper.get("essence"),
                    paper.get("research_line"),
                    paper.get("line_role"),
                    paper.get("status"),
                    paper.get("reading_stage"),
                    paper.get("review_stage"),
                    paper.get("_search_text"),
                    *paper.get("authors", []),
                    *paper.get("domains", []),
                    *paper.get("tracks", []),
                    *paper.get("problems", []),
                    *paper.get("topics", []),
                    *paper.get("methods", []),
                ]
                if part
            ).lower()
            if value.lower() not in haystack:
                return False
        elif key == "domain" and not list_has(paper.get("domains"), value):
            return False
        elif key == "track" and not list_has(paper.get("tracks"), value):
            return False
        elif key == "problem" and not list_has(paper.get("problems"), value):
            return False
        elif key == "topic" and not list_has(paper.get("topics"), value):
            return False
        elif key == "method" and not list_has(paper.get("methods"), value):
            return False
        elif key == "line" and str(paper.get("research_line") or "") != value:
            return False
        elif key == "role" and str(paper.get("line_role") or "") != value:
            return False
        elif key == "status" and str(paper.get("status") or "") != value:
            return False
        elif key == "stage" and str(paper.get("reading_stage") or "") != value:
            return False
        elif key == "reviewStage" and str(paper.get("review_stage") or "") != value:
            return False
        elif key == "review":
            has_next_review = bool(paper.get("next_review"))
            is_due = bool(has_next_review and str(paper.get("next_review")) <= today)
            if value == "none" and has_next_review:
                return False
            if value != "none" and not is_due:
                return False
        elif key == "code":
            has_code = bool(paper.get("has_code"))
            if value == "yes" and not has_code:
                return False
            if value == "no" and has_code:
                return False
        elif key == "importance":
            try:
                min_importance = int(value or 0)
            except ValueError:
                return False
            if int(paper.get("importance") or 0) < min_importance:
                return False
    return True


def view_target_page(view: dict[str, Any]) -> str:
    page = str(view.get("page") or "library")
    return "index.html" if page == "index" else "library.html"


def view_href(view: dict[str, Any]) -> str:
    state = {
        str(key): str(value)
        for key, value in (view.get("state") or {}).items()
        if str(value).strip()
    }
    return page_query_href(view_target_page(view), **state)


def role_rank(role: str) -> int:
    return ROLE_ORDER.get(role, 20)


def percent(part: int | float, total: int | float) -> str:
    if not total:
        return "0%"
    return f"{round(float(part) * 100 / float(total))}%"


def format_bytes(size: int | float) -> str:
    value = float(size or 0)
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def build_paper(md_path: Path, report_dir: Path) -> dict[str, Any]:
    text = md_path.read_text(encoding="utf-8")
    meta, body = strip_frontmatter(text)
    slug = str(meta.get("slug") or md_path.stem).strip()
    raw_title, title_zh, title_en = infer_title(body, meta, slug)
    arxiv_id = infer_arxiv_id(slug, body, meta)
    html_path = md_path.with_suffix(".html")
    stat = md_path.stat()

    paper = {
        "slug": slug,
        "title": raw_title,
        "title_zh": title_zh,
        "title_en": title_en,
        "authors": infer_authors(body, meta),
        "year": infer_year(arxiv_id, body, meta),
        "arxiv_id": arxiv_id,
        "arxiv_url": infer_url(body, arxiv_id, meta, "arxiv_url"),
        "code_url": infer_url(body, arxiv_id, meta, "code_url"),
        "domains": infer_list_field(meta, "domains"),
        "tracks": infer_list_field(meta, "tracks"),
        "problems": infer_list_field(meta, "problems"),
        "topics": infer_topics(body, meta),
        "methods": infer_methods(meta),
        "research_line": infer_research_line(meta),
        "line_role": str(meta.get("line_role") or "").strip(),
        "status": str(meta.get("status") or "read"),
        "reading_stage": str(meta.get("reading_stage") or "").strip(),
        "review_stage": str(meta.get("review_stage") or "").strip(),
        "last_reviewed": str(meta.get("last_reviewed") or "").strip(),
        "next_review": str(meta.get("next_review") or "").strip(),
        "importance": meta.get("importance"),
        "confidence": meta.get("confidence"),
        "reproducibility": meta.get("reproducibility"),
        "has_code": bool(meta.get("has_code")) or "## 10. 代码实现观察" in body or "代码仓库" in body,
        "md_path": md_path.relative_to(report_dir).as_posix(),
        "html_path": html_path.relative_to(report_dir).as_posix() if html_path.exists() else "",
        "excerpt": infer_excerpt(body, meta),
        "essence": infer_essence(body, meta),
        "reading_time_min": reading_time_minutes(body),
        "created_at": dt.datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
        "updated_at": dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "_search_text": markdown_to_search_text(body)[:50000],
    }
    return paper


def collect_papers(report_dir: Path) -> list[dict[str, Any]]:
    papers = []
    for md_path in sorted(report_dir.glob("*.md")):
        if md_path.name.startswith(".") or md_path.stem in {"index", "README"}:
            continue
        papers.append(build_paper(md_path, report_dir))
    papers.sort(key=lambda item: (item.get("year") or 0, item["updated_at"]), reverse=True)
    return papers


def list_counts(papers: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for paper in papers:
        for field in fields:
            counter.update(paper.get(field, []))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0].lower())))


def scalar_counts(papers: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for paper in papers:
        value = str(paper.get(field) or "").strip()
        if value and value != "Unassigned":
            counter[value] += 1
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0].lower())))


def configured_scalar_counts(papers: list[dict[str, Any]], field: str, values: list[str]) -> dict[str, int]:
    counts = scalar_counts(papers, field)
    for value in values:
        counts.setdefault(value, 0)
    return dict(sorted(counts.items(), key=lambda item: (item[1] == 0, -item[1], item[0].lower())))


def tag_counts(papers: list[dict[str, Any]]) -> dict[str, int]:
    return list_counts(papers, ("topics", "methods"))


def taxonomy_counts(papers: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "domains": list_counts(papers, ("domains",)),
        "tracks": list_counts(papers, ("tracks",)),
        "problems": list_counts(papers, ("problems",)),
        "topics": list_counts(papers, ("topics",)),
        "methods": list_counts(papers, ("methods",)),
        "research_lines": scalar_counts(papers, "research_line"),
        "line_roles": scalar_counts(papers, "line_role"),
        "statuses": configured_scalar_counts(papers, "status", STATUS_VALUES),
        "reading_stages": configured_scalar_counts(papers, "reading_stage", READING_STAGE_VALUES),
        "review_stages": configured_scalar_counts(papers, "review_stage", REVIEW_STAGE_VALUES),
    }


def taxonomy_drift_items(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = {
        "status": STATUS_VALUES,
        "reading_stage": READING_STAGE_VALUES,
        "review_stage": REVIEW_STAGE_VALUES,
        "line_role": list(ROLE_ORDER.keys()),
    }
    drift: list[dict[str, Any]] = []
    for paper in papers:
        for field, allowed in specs.items():
            value = str(paper.get(field) or "").strip()
            if not value or value == "Unassigned":
                continue
            if value not in allowed:
                drift.append(
                    {
                        "slug": paper["slug"],
                        "title": paper["title"],
                        "title_zh": paper["title_zh"],
                        "field": field,
                        "value": value,
                        "allowed": allowed,
                    }
                )
    return drift


def label_fingerprint(label: str) -> str:
    text = str(label or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    tokens = []
    for token in text.split():
        if len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        tokens.append(token)
    return " ".join(tokens)


def label_alias_suggestions(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    list_fields = ("domains", "tracks", "problems", "topics", "methods")
    scalar_fields = ("research_line",)

    def record(field: str, value: str, slug: str) -> None:
        label = str(value or "").strip()
        key = label_fingerprint(label)
        if not label or not key or label == "Unassigned":
            return
        bucket = grouped[key].setdefault(label, {"count": 0, "fields": set(), "slugs": set()})
        bucket["count"] += 1
        bucket["fields"].add(field)
        bucket["slugs"].add(slug)

    for paper in papers:
        slug = str(paper.get("slug") or "")
        for field in list_fields:
            for value in paper.get(field, []):
                record(field, value, slug)
        for field in scalar_fields:
            record(field, str(paper.get(field) or ""), slug)

    suggestions: list[dict[str, Any]] = []
    for key, labels in grouped.items():
        if len(labels) <= 1:
            continue
        canonical = sorted(
            labels,
            key=lambda label: (
                -int(labels[label]["count"]),
                label.islower(),
                len(label),
                label.lower(),
            ),
        )[0]
        alias_values = [label for label in sorted(labels, key=str.lower) if label != canonical]
        if not alias_values:
            continue
        aliases = {alias: canonical for alias in alias_values}
        fields = sorted({field for item in labels.values() for field in item["fields"]})
        slugs = sorted({slug for item in labels.values() for slug in item["slugs"]})
        suggestions.append(
            {
                "fingerprint": key,
                "canonical": canonical,
                "aliases": aliases,
                "fields": fields,
                "slugs": slugs,
                "labels": [
                    {
                        "value": label,
                        "count": int(labels[label]["count"]),
                        "fields": sorted(labels[label]["fields"]),
                        "slugs": sorted(labels[label]["slugs"]),
                    }
                    for label in sorted(labels, key=lambda label: (-int(labels[label]["count"]), label.lower()))
                ],
            }
        )

    return sorted(
        suggestions,
        key=lambda item: (-len(item["aliases"]), -sum(label["count"] for label in item["labels"]), item["canonical"].lower()),
    )


def normalized_duplicate_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"www\.", "", text)
    text = re.sub(r"[\s_./:-]+", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def duplicate_report_groups(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        candidates = {
            "arxiv_id": str(paper.get("arxiv_id") or "").split("v")[0].strip().lower(),
            "title_en": normalized_duplicate_key(paper.get("title_en") or paper.get("title")),
            "title_zh": normalized_duplicate_key(paper.get("title_zh")),
            "code_url": normalized_duplicate_key(paper.get("code_url")),
        }
        for reason, value in candidates.items():
            if value:
                buckets[(reason, value)].append(paper)

    groups: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for (reason, value), items in buckets.items():
        unique = {paper["slug"]: paper for paper in items}
        if len(unique) <= 1:
            continue
        slugs = tuple(sorted(unique))
        fingerprint = (reason, slugs)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        papers_payload = [
            {
                "slug": paper["slug"],
                "title": paper["title"],
                "title_zh": paper["title_zh"],
                "arxiv_id": paper.get("arxiv_id") or "",
                "html_path": paper.get("html_path") or paper.get("md_path"),
            }
            for paper in sorted(unique.values(), key=lambda item: item["slug"])
        ]
        groups.append(
            {
                "reason": reason,
                "value": value,
                "slugs": list(slugs),
                "papers": papers_payload,
            }
        )
    return sorted(groups, key=lambda item: (item["reason"], item["value"]))


def paper_quality_issue(paper: dict[str, Any], today: str) -> dict[str, Any]:
    missing_fields: list[str] = []
    weak_fields: list[str] = []

    for field in ("domains", "tracks", "problems", "topics", "methods"):
        if not paper.get(field):
            missing_fields.append(field)
    for field in ("research_line", "line_role", "status", "reading_stage"):
        value = str(paper.get(field) or "").strip()
        if not value or value == "Unassigned":
            missing_fields.append(field)
    for field in ("importance", "confidence", "reproducibility"):
        if paper.get(field) in {None, ""}:
            missing_fields.append(field)

    if not paper.get("next_review"):
        weak_fields.append("next_review")
    if not paper.get("review_stage"):
        weak_fields.append("review_stage")
    if not paper.get("has_code"):
        weak_fields.append("has_code")
    if int(paper.get("confidence") or 0) <= 2:
        weak_fields.append("confidence")
    if int(paper.get("reproducibility") or 0) <= 2:
        weak_fields.append("reproducibility")

    due_review = bool(paper.get("next_review") and str(paper.get("next_review")) <= today)
    score = max(0, 100 - len(missing_fields) * 10 - len(weak_fields) * 4 - (8 if due_review else 0))

    return {
        "slug": paper["slug"],
        "title": paper["title"],
        "title_zh": paper["title_zh"],
        "research_line": paper.get("research_line") or "Unassigned",
        "importance": paper.get("importance"),
        "score": score,
        "missing_fields": missing_fields,
        "weak_fields": weak_fields,
        "due_review": due_review,
        "has_code": bool(paper.get("has_code")),
    }


def paper_taxonomy_load_issue(paper: dict[str, Any]) -> dict[str, Any] | None:
    policy = GOVERNANCE_POLICY["taxonomy_load"]
    structure_count = sum(len(paper.get(field, []) or []) for field in ("domains", "tracks", "problems"))
    topic_count = len(paper.get("topics", []) or [])
    method_count = len(paper.get("methods", []) or [])
    tag_count = topic_count + method_count
    signals: list[str] = []
    if structure_count < int(policy["min_structure_labels"]):
        signals.append("sparse_structure")
    if tag_count < int(policy["min_tags"]):
        signals.append("sparse_tags")
    if tag_count > int(policy["max_tags"]):
        signals.append("dense_tags")
    if method_count > int(policy["max_methods"]):
        signals.append("method_overload")
    if not signals:
        return None

    if any(signal.startswith("sparse") for signal in signals):
        recommendation = "补齐 domain / track / problem 或 topic / method，让这篇论文能被多入口检索。"
    else:
        recommendation = "检查 topic / method 是否过细，保留最能区分论文的标签。"
    return {
        "slug": paper["slug"],
        "title": paper["title"],
        "title_zh": paper["title_zh"],
        "html_path": paper.get("html_path") or f"{paper['slug']}.html",
        "research_line": paper.get("research_line") or "Unassigned",
        "structure_count": structure_count,
        "topic_count": topic_count,
        "method_count": method_count,
        "tag_count": tag_count,
        "signals": signals,
        "policy": policy.copy(),
        "recommendation": recommendation,
    }


def build_quality_report(papers: list[dict[str, Any]]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    issues = [paper_quality_issue(paper, today) for paper in papers]
    taxonomy_drift = taxonomy_drift_items(papers)
    alias_suggestions = label_alias_suggestions(papers)
    duplicate_groups = duplicate_report_groups(papers)
    taxonomy_load = [
        item
        for item in (paper_taxonomy_load_issue(paper) for paper in papers)
        if item is not None
    ]
    papers_with_issues = [
        issue
        for issue in issues
        if issue["missing_fields"] or issue["weak_fields"] or issue["due_review"]
    ]
    total = len(papers)
    complete_taxonomy = total - sum(1 for issue in issues if issue["missing_fields"])
    with_review_plan = sum(1 for paper in papers if paper.get("next_review"))
    with_code = sum(1 for paper in papers if paper.get("has_code"))
    line_counts = scalar_counts(papers, "research_line")

    queues = {
        "missing_required_metadata": [issue["slug"] for issue in issues if issue["missing_fields"]],
        "needs_review_plan": [paper["slug"] for paper in papers if not paper.get("next_review")],
        "due_review": [issue["slug"] for issue in issues if issue["due_review"]],
        "no_code_observation": [paper["slug"] for paper in papers if not paper.get("has_code")],
        "taxonomy_drift": sorted({item["slug"] for item in taxonomy_drift}),
        "duplicate_reports": sorted({slug for group in duplicate_groups for slug in group["slugs"]}),
        "taxonomy_sparse": sorted(
            {
                item["slug"]
                for item in taxonomy_load
                if any(str(signal).startswith("sparse") for signal in item["signals"])
            }
        ),
        "taxonomy_dense": sorted(
            {
                item["slug"]
                for item in taxonomy_load
                if any(str(signal).startswith("dense") or str(signal).endswith("overload") for signal in item["signals"])
            }
        ),
        "high_importance": [
            paper["slug"]
            for paper in sorted(papers, key=lambda p: (-(p.get("importance") or 0), p["title"]))
            if int(paper.get("importance") or 0) >= 5
        ],
    }

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": total,
        "quality_score": round(sum(issue["score"] for issue in issues) / total, 1) if total else 100,
        "coverage": {
            "taxonomy": percent(complete_taxonomy, total),
            "review_plan": percent(with_review_plan, total),
            "code_observation": percent(with_code, total),
            "research_lines": len(line_counts),
        },
        "queues": queues,
        "issues": papers_with_issues,
        "taxonomy_load": taxonomy_load,
        "governance_policy": json.loads(json.dumps(GOVERNANCE_POLICY)),
        "taxonomy_drift": taxonomy_drift,
        "label_alias_suggestions": alias_suggestions,
        "duplicate_reports": duplicate_groups,
    }


def write_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "controls": control_options(),
        "tags": tag_counts(papers),
        "taxonomy": taxonomy_counts(papers),
        "papers": [public_paper(paper) for paper in papers],
    }
    (report_dir / "papers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_quality_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_quality_report(papers)
    (report_dir / "quality.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def top_counts(counts: dict[str, int], limit: int = 12) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in list(counts.items())[:limit]
    ]


def build_stats_report(papers: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    taxonomy = taxonomy_counts(papers)
    total = len(papers)
    years = Counter(str(paper.get("year") or "unknown") for paper in papers)
    code_count = sum(1 for paper in papers if paper.get("has_code"))
    importance_counts = Counter(str(paper.get("importance") or "unknown") for paper in papers)

    line_items = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)
    for line, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        code_items = sum(1 for paper in items if paper.get("has_code"))
        owner = research_line_owner(line)
        line_items.append(
            {
                "name": line,
                "count": len(items),
                "owner": owner.get("owner", ""),
                "team": owner.get("team", ""),
                "cadence": owner.get("cadence", ""),
                "owner_note": owner.get("note", ""),
                "roles": scalar_counts(items, "line_role"),
                "code_coverage": percent(code_items, len(items)),
                "avg_importance": round(
                    sum(int(paper.get("importance") or 0) for paper in items) / len(items),
                    1,
                ),
            }
        )

    queue_sizes = {
        "quality": {name: len(slugs) for name, slugs in quality["queues"].items()},
        "review": {name: len(slugs) for name, slugs in review["queues"].items()},
    }

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": total,
        "quality_score": quality["quality_score"],
        "controls": control_options(),
        "coverage": {
            **quality["coverage"],
            "code": percent(code_count, total),
        },
        "queue_sizes": queue_sizes,
        "taxonomy": {
            "domains": top_counts(taxonomy["domains"]),
            "tracks": top_counts(taxonomy["tracks"]),
            "problems": top_counts(taxonomy["problems"]),
            "topics": top_counts(taxonomy["topics"]),
            "methods": top_counts(taxonomy["methods"]),
            "research_lines": top_counts(taxonomy["research_lines"]),
            "statuses": top_counts(taxonomy["statuses"]),
            "reading_stages": top_counts(taxonomy["reading_stages"]),
            "review_stages": top_counts(taxonomy["review_stages"]),
        },
        "distributions": {
            "years": dict(sorted(years.items(), key=lambda item: item[0], reverse=True)),
            "importance": dict(sorted(importance_counts.items(), key=lambda item: item[0], reverse=True)),
        },
        "taxonomy_balance": taxonomy_balance_report(papers),
        "research_lines": line_items,
        "shared_views": len(SHARED_VIEWS),
    }


def write_stats_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_stats_report(papers)
    (report_dir / "stats.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


WORKFLOW_FIELD_SPECS = {
    "status": {
        "label": "阅读状态",
        "config_key": "status_values",
        "paper_key": "status",
        "query_key": "status",
    },
    "reading_stage": {
        "label": "阅读阶段",
        "config_key": "reading_stage_values",
        "paper_key": "reading_stage",
        "query_key": "stage",
    },
    "review_stage": {
        "label": "复习阶段",
        "config_key": "review_stage_values",
        "paper_key": "review_stage",
        "query_key": "reviewStage",
    },
}


def workflow_field_distribution(
    papers: list[dict[str, Any]],
    workflow_name: str,
    field_name: str,
    configured_values: list[str],
) -> dict[str, Any]:
    spec = WORKFLOW_FIELD_SPECS[field_name]
    paper_key = str(spec["paper_key"])
    query_key = str(spec["query_key"])
    configured = [str(value).strip() for value in configured_values if str(value).strip()]
    configured_set = set(configured)
    counts: Counter[str] = Counter()
    slugs_by_value: dict[str, list[str]] = defaultdict(list)
    empty_slugs: list[str] = []

    for paper in papers:
        value = str(paper.get(paper_key) or "").strip()
        if not value:
            empty_slugs.append(str(paper["slug"]))
            continue
        counts[value] += 1
        slugs_by_value[value].append(str(paper["slug"]))

    def value_payload(value: str, configured_value: bool) -> dict[str, Any]:
        definition = label_definition(field_name, value)
        return {
            "value": value,
            "count": int(counts.get(value, 0)),
            "configured": configured_value,
            "definition": definition,
            "definition_status": definition.get("status", ""),
            "description": definition.get("description", ""),
            "owner_name": definition.get("owner", ""),
            "href": page_query_href("library.html", workflow=workflow_name, **{query_key: value}),
        }

    values = [
        value_payload(value, True)
        for value in configured
    ]
    unconfigured = [
        {
            **value_payload(value, False),
            "slugs": sorted(slugs_by_value[value]),
        }
        for value in sorted(counts, key=lambda item: (-counts[item], item.lower()))
        if value not in configured_set
    ]
    all_values = values + unconfigured
    return {
        "field": field_name,
        "label": spec["label"],
        "configured_count": len(configured),
        "used_configured_count": sum(1 for value in configured if counts.get(value, 0)),
        "defined_count": sum(1 for item in all_values if item.get("definition")),
        "deprecated_count": sum(1 for item in all_values if item.get("definition_status") == "deprecated"),
        "empty_count": len(empty_slugs),
        "empty_slugs": sorted(empty_slugs),
        "values": values,
        "unconfigured": unconfigured,
    }


def build_workflow_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    controls = control_options()
    workflows = controls.get("status_workflows") or {}
    active = str(controls.get("active_status_workflow") or next(iter(workflows), "default"))
    workflow_items: list[dict[str, Any]] = []

    for name, workflow in workflows.items():
        name_text = str(name)
        fields = {
            field_name: workflow_field_distribution(
                papers,
                name_text,
                field_name,
                list(workflow.get(str(spec["config_key"]), []) or []),
            )
            for field_name, spec in WORKFLOW_FIELD_SPECS.items()
        }
        unconfigured_total = sum(len(field["unconfigured"]) for field in fields.values())
        empty_total = sum(int(field["empty_count"]) for field in fields.values())
        definition_total = sum(int(field["defined_count"]) for field in fields.values())
        deprecated_total = sum(int(field["deprecated_count"]) for field in fields.values())
        workflow_items.append(
            {
                "name": name_text,
                "active": name_text == active,
                "status_values": list(workflow.get("status_values", []) or []),
                "reading_stage_values": list(workflow.get("reading_stage_values", []) or []),
                "review_stage_values": list(workflow.get("review_stage_values", []) or []),
                "fields": fields,
                "unconfigured_total": unconfigured_total,
                "empty_total": empty_total,
                "definition_total": definition_total,
                "deprecated_total": deprecated_total,
                "board_href": page_query_href("board.html", workflow=name_text),
                "library_href": page_query_href("library.html", workflow=name_text),
            }
        )

    active_item = next((item for item in workflow_items if item["active"]), workflow_items[0] if workflow_items else {})
    active_unconfigured = []
    for field in (active_item.get("fields") or {}).values():
        for item in field.get("unconfigured", []):
            active_unconfigured.append(
                {
                    "field": field["field"],
                    "label": field["label"],
                    **item,
                }
            )

    shared_workflow_views = [
        {
            "name": view["name"],
            "page": view.get("page") or "all",
            "workflow": (view.get("state") or {}).get("workflow", ""),
            "href": view_href(view),
            "state": view.get("state") or {},
        }
        for view in SHARED_VIEWS
        if (view.get("state") or {}).get("workflow")
    ]

    recommendations: list[str] = []
    if not workflow_items:
        recommendations.append("在 docs/guides/taxonomy.json 增加 status_workflows，给不同阅读模式保存命名状态体系。")
    if active_unconfigured:
        recommendations.append("当前激活 workflow 存在未配置状态值，建议在 taxonomy.html 调整 workflow 或批量迁移旧状态。")
    missing_review = int((active_item.get("fields") or {}).get("review_stage", {}).get("empty_count") or 0)
    if missing_review:
        recommendations.append(f"有 {missing_review} 篇论文缺 review_stage，可在 library.html 批量补齐复习阶段。")
    empty_statuses = [
        value["value"]
        for value in (active_item.get("fields") or {}).get("status", {}).get("values", [])
        if int(value["count"]) == 0
    ]
    if empty_statuses:
        recommendations.append(f"当前 workflow 有 {len(empty_statuses)} 个空 status，可保留为候选列，或在 workflow 中移除。")
    deprecated_total = int(active_item.get("deprecated_total") or 0)
    if deprecated_total:
        recommendations.append(f"当前 workflow 有 {deprecated_total} 个 deprecated 状态/阶段定义，建议迁移或移出 active workflow。")
    if not recommendations:
        recommendations.append("当前状态工作流和论文 frontmatter 对齐良好。")

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "active_status_workflow": active,
        "workflow_count": len(workflow_items),
        "workflows": workflow_items,
        "active_unconfigured": active_unconfigured,
        "shared_workflow_views": shared_workflow_views,
        "recommendations": recommendations,
        "commands": [
            "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json>",
            "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write",
            "python3 scripts/apply_library_metadata.py docs --input <status_patch.csv>",
            "python3 scripts/validate_wiki.py docs --strict-taxonomy",
        ],
    }


def write_workflow_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_workflow_payload(papers)
    (report_dir / "workflow.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def status_selector_paper(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper["title"],
        "title_zh": paper.get("title_zh") or "",
        "research_line": paper.get("research_line") or "Unassigned",
        "line_role": paper.get("line_role") or "",
        "status": paper.get("status") or "",
        "reading_stage": paper.get("reading_stage") or "",
        "review_stage": paper.get("review_stage") or "",
        "importance": paper.get("importance") or "",
        "has_code": bool(paper.get("has_code")),
        "href": paper_href(paper),
    }


def build_status_selector_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    workflow = build_workflow_payload(papers)
    defaults = {
        "workflow": workflow["active_status_workflow"],
        "status": "",
        "reading_stage": "",
        "review_stage": "",
    }
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "active_status_workflow": workflow["active_status_workflow"],
        "workflow_count": workflow["workflow_count"],
        "workflows": workflow["workflows"],
        "papers": [status_selector_paper(paper) for paper in papers],
        "defaults": defaults,
        "links": {
            "index": "index.html",
            "library": "library.html",
            "board": "board.html",
            "workflow": "workflow.html",
            "taxonomy": "taxonomy.html",
        },
        "commands": [
            "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json>",
            "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write",
            "python3 scripts/apply_shared_views.py docs --input <status_shared_view.json>",
            "python3 scripts/apply_shared_views.py docs --input <status_shared_view.json> --write",
            "python3 scripts/apply_library_metadata.py docs --input <status_patch.csv>",
            "python3 scripts/apply_library_metadata.py docs --input <status_patch.csv> --write",
        ],
    }


def write_status_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_status_selector_payload(papers)
    (report_dir / "status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


BATCH_DIMENSIONS = [
    {"key": "research_line", "label": "研究线", "query": "line", "multi": False, "paper_key": "research_line"},
    {"key": "line_role", "label": "研究角色", "query": "role", "multi": False, "paper_key": "line_role"},
    {"key": "domain", "label": "Domain", "query": "domain", "multi": True, "paper_key": "domains"},
    {"key": "track", "label": "Track", "query": "track", "multi": True, "paper_key": "tracks"},
    {"key": "problem", "label": "Problem", "query": "problem", "multi": True, "paper_key": "problems"},
    {"key": "topic", "label": "Topic", "query": "topic", "multi": True, "paper_key": "topics"},
    {"key": "method", "label": "Method", "query": "method", "multi": True, "paper_key": "methods"},
    {"key": "status", "label": "Status", "query": "status", "multi": False, "paper_key": "status"},
    {"key": "reading_stage", "label": "Reading stage", "query": "stage", "multi": False, "paper_key": "reading_stage"},
    {"key": "review_stage", "label": "Review stage", "query": "reviewStage", "multi": False, "paper_key": "review_stage"},
    {"key": "code", "label": "Code", "query": "code", "multi": False, "paper_key": "has_code"},
]


def paper_missing_taxonomy(paper: dict[str, Any]) -> bool:
    return any(
        not paper.get(field)
        for field in ("domains", "tracks", "problems", "topics", "methods", "line_role")
    ) or str(paper.get("research_line") or "") == "Unassigned"


def batch_dimension_values(paper: dict[str, Any], dimension: dict[str, Any]) -> list[str]:
    key = str(dimension["key"])
    paper_key = str(dimension["paper_key"])
    if key == "code":
        return ["yes" if paper.get("has_code") else "no"]
    if dimension.get("multi"):
        values = [str(value).strip() for value in paper.get(paper_key, []) if str(value).strip()]
        return values or ["未设置"]
    value = str(paper.get(paper_key) or "").strip()
    return [value or "未设置"]


def batch_href(dimension: dict[str, Any], value: str) -> str:
    if value == "未设置" or value == "unset":
        return "library.html"
    key = str(dimension["key"])
    query = str(dimension["query"])
    if key == "code":
        return page_query_href("library.html", code=value)
    return page_query_href("library.html", **{query: value})


def batch_severity(count: int, missing_review: int, due_review: int, missing_taxonomy: int, no_code: int) -> str:
    if not count:
        return "low"
    review_gap = (missing_review + due_review) / count
    taxonomy_gap = missing_taxonomy / count
    code_gap = no_code / count
    if due_review or taxonomy_gap >= 0.5 or review_gap >= 0.5:
        return "high"
    if taxonomy_gap >= 0.25 or review_gap >= 0.25 or code_gap >= 0.5:
        return "medium"
    return "low"


def batch_action(missing_review: int, due_review: int, missing_taxonomy: int, no_code: int, high_importance: int) -> str:
    if due_review:
        return f"先复习到期论文 {due_review} 篇"
    if missing_review:
        return f"补 next_review {missing_review} 篇"
    if missing_taxonomy:
        return f"补 taxonomy {missing_taxonomy} 篇"
    if no_code:
        return f"补代码观察 {no_code} 篇"
    if high_importance:
        return f"整理重点论文 {high_importance} 篇"
    return "保持观察"


def command_report_dir(report_dir: Path) -> Path:
    if report_dir.is_relative_to(ROOT):
        return report_dir.relative_to(ROOT)
    return report_dir


def batch_export_command(dimension: dict[str, Any], value: str, report_dir: Path) -> str:
    if value in {"未设置", "unset"}:
        return ""
    arg_by_dimension = {
        "research_line": "--line",
        "track": "--track",
        "topic": "--topic",
        "method": "--method",
        "status": "--status",
    }
    option = arg_by_dimension.get(str(dimension["key"]))
    if not option:
        return ""
    slug = slugify_label(f"{dimension['key']}-{value}") or "batch"
    command_dir = command_report_dir(report_dir)
    output_path = command_dir / "exports" / f"{slug}-reading-list.md"
    return (
        f"python3 scripts/export_reading_list.py {shlex.quote(str(command_dir))} {option} {shlex.quote(value)} "
        f"--output {shlex.quote(str(output_path))}"
    )


def batch_record(
    dimension: dict[str, Any],
    value: str,
    items: list[dict[str, Any]],
    today: str,
    report_dir: Path,
) -> dict[str, Any]:
    count = len(items)
    missing_review = sum(1 for paper in items if not paper.get("next_review"))
    due_review = sum(1 for paper in items if paper.get("next_review") and str(paper.get("next_review")) <= today)
    missing_taxonomy = sum(1 for paper in items if paper_missing_taxonomy(paper))
    no_code = sum(1 for paper in items if not paper.get("has_code"))
    high_importance = sum(1 for paper in items if int(paper.get("importance") or 0) >= 5)
    latest_year = max((int(paper.get("year") or 0) for paper in items), default=0)
    severity = batch_severity(count, missing_review, due_review, missing_taxonomy, no_code)
    priority = (
        {"high": 90, "medium": 60, "low": 30}.get(severity, 0)
        + due_review * 8
        + missing_review * 4
        + missing_taxonomy * 5
        + high_importance * 3
        + min(count, 20)
    )
    samples = sorted(
        items,
        key=lambda paper: (-(int(paper.get("importance") or 0)), -(int(paper.get("year") or 0)), paper["title"]),
    )[:6]
    return {
        "id": f"{dimension['key']}::{value}",
        "dimension": dimension["key"],
        "dimension_label": dimension["label"],
        "value": value,
        "count": count,
        "severity": severity,
        "priority": priority,
        "latest_year": latest_year or "",
        "high_importance": high_importance,
        "missing_review": missing_review,
        "due_review": due_review,
        "missing_taxonomy": missing_taxonomy,
        "no_code": no_code,
        "recommended_action": batch_action(missing_review, due_review, missing_taxonomy, no_code, high_importance),
        "href": batch_href(dimension, value),
        "export_command": batch_export_command(dimension, value, report_dir),
        "slugs": sorted(str(paper["slug"]) for paper in items),
        "sample_slugs": [paper["slug"] for paper in samples],
        "sample_titles": [paper.get("title_zh") or paper.get("title") or paper["slug"] for paper in samples],
    }


def build_batch_payload(papers: list[dict[str, Any]], report_dir: Path) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    batches: list[dict[str, Any]] = []
    for dimension in BATCH_DIMENSIONS:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for paper in papers:
            for value in batch_dimension_values(paper, dimension):
                grouped[value].append(paper)
        for value, items in grouped.items():
            batches.append(batch_record(dimension, value, items, today, report_dir))
    batches.sort(key=lambda item: (-int(item["priority"]), str(item["dimension"]), str(item["value"]).lower()))
    summary = {
        "high": sum(1 for item in batches if item["severity"] == "high"),
        "medium": sum(1 for item in batches if item["severity"] == "medium"),
        "low": sum(1 for item in batches if item["severity"] == "low"),
        "missing_review": sum(int(item["missing_review"]) for item in batches),
        "missing_taxonomy": sum(int(item["missing_taxonomy"]) for item in batches),
    }
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "report_dir": str(command_report_dir(report_dir)),
        "dimension_count": len(BATCH_DIMENSIONS),
        "batch_count": len(batches),
        "dimensions": BATCH_DIMENSIONS,
        "summary": summary,
        "batches": batches,
        "top_batches": batches[:12],
        "links": {
            "library": "library.html",
            "actions": "actions.html",
            "quality": "quality.html",
            "review": "review.html",
            "facets": "facets.html",
            "scale": "scale.html",
        },
    }


def write_batch_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_batch_payload(papers, report_dir)
    (report_dir / "batch.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


PIVOT_DIMENSIONS = {
    "research_line": {"label": "研究线", "query": "line", "multi": False},
    "domain": {"label": "Domain", "query": "domain", "multi": True, "paper_key": "domains"},
    "track": {"label": "Track", "query": "track", "multi": True, "paper_key": "tracks"},
    "problem": {"label": "Problem", "query": "problem", "multi": True, "paper_key": "problems"},
    "topic": {"label": "Topic", "query": "topic", "multi": True, "paper_key": "topics"},
    "method": {"label": "Method", "query": "method", "multi": True, "paper_key": "methods"},
    "status": {"label": "Status", "query": "status", "multi": False},
    "reading_stage": {"label": "Reading Stage", "query": "stage", "multi": False},
    "review_stage": {"label": "Review Stage", "query": "reviewStage", "multi": False},
    "year": {"label": "Year", "query": "year", "multi": False},
    "importance": {"label": "Importance", "query": "importance", "multi": False},
    "has_code": {"label": "Code", "query": "code", "multi": False},
}


def paper_dimension_values(paper: dict[str, Any], dimension: str) -> list[str]:
    spec = PIVOT_DIMENSIONS[dimension]
    if spec.get("multi"):
        values = [str(value).strip() for value in paper.get(str(spec.get("paper_key") or dimension), []) if str(value).strip()]
    elif dimension == "year":
        values = [str(paper.get("year") or "unknown")]
    elif dimension == "importance":
        values = [str(paper.get("importance") or "unknown")]
    elif dimension == "has_code":
        values = ["yes" if paper.get("has_code") else "no"]
    else:
        values = [str(paper.get(dimension) or "").strip()]
    values = [value for value in values if value and value != "Unassigned"]
    return values or ["Unassigned"]


def build_pivot_matrix(papers: list[dict[str, Any]], row_dimension: str, column_dimension: str, limit: int = 12) -> dict[str, Any]:
    cells: dict[tuple[str, str], set[str]] = defaultdict(set)
    row_counts: Counter[str] = Counter()
    column_counts: Counter[str] = Counter()
    for paper in papers:
        row_values = paper_dimension_values(paper, row_dimension)
        column_values = paper_dimension_values(paper, column_dimension)
        for row in row_values:
            row_counts[row] += 1
        for column in column_values:
            column_counts[column] += 1
        for row in row_values:
            for column in column_values:
                cells[(row, column)].add(str(paper["slug"]))

    rows = [value for value, _ in row_counts.most_common(limit)]
    columns = [value for value, _ in column_counts.most_common(limit)]
    cell_payload = [
        {
            "row": row,
            "column": column,
            "count": len(slugs),
            "slugs": sorted(slugs),
        }
        for (row, column), slugs in sorted(cells.items(), key=lambda item: (-len(item[1]), item[0][0].lower(), item[0][1].lower()))
        if row in rows and column in columns
    ]
    return {
        "row_dimension": row_dimension,
        "column_dimension": column_dimension,
        "rows": [{"value": value, "count": int(row_counts[value])} for value in rows],
        "columns": [{"value": value, "count": int(column_counts[value])} for value in columns],
        "cells": cell_payload,
        "non_empty_cells": len(cell_payload),
    }


def build_pivot_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    paper_payload = []
    for paper in papers:
        dimensions = {
            name: paper_dimension_values(paper, name)
            for name in PIVOT_DIMENSIONS
        }
        paper_payload.append(
            {
                "slug": paper["slug"],
                "title": paper.get("title") or "",
                "title_zh": paper.get("title_zh") or paper.get("title") or "",
                "href": paper.get("html_path") or paper.get("md_path") or "",
                "dimensions": dimensions,
            }
        )
    presets = [
        ("research_line", "method"),
        ("track", "status"),
        ("year", "topic"),
        ("domain", "problem"),
    ]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "dimensions": [
            {
                "key": key,
                "label": str(spec["label"]),
                "query": str(spec["query"]),
                "multi": bool(spec.get("multi")),
            }
            for key, spec in PIVOT_DIMENSIONS.items()
        ],
        "papers": paper_payload,
        "presets": [build_pivot_matrix(papers, row, column) for row, column in presets],
    }


def write_pivot_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_pivot_payload(papers)
    (report_dir / "pivot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


TAXONOMY_MAP_FIELDS = [
    {"key": "research_line", "label": "Research line", "query": "line"},
    {"key": "domain", "label": "Domain", "query": "domain"},
    {"key": "track", "label": "Track", "query": "track"},
    {"key": "problem", "label": "Problem", "query": "problem"},
    {"key": "topic", "label": "Topic", "query": "topic"},
    {"key": "method", "label": "Method", "query": "method"},
]

TAXONOMY_MAP_FIELD_BY_KEY = {field["key"]: field for field in TAXONOMY_MAP_FIELDS}

TAXONOMY_MAP_EDGE_SPECS = [
    ("research_line", "domain"),
    ("domain", "track"),
    ("track", "problem"),
    ("problem", "topic"),
    ("topic", "method"),
    ("research_line", "track"),
    ("problem", "method"),
]


def taxonomy_map_values(paper: dict[str, Any], field: str) -> list[str]:
    if field == "research_line":
        value = str(paper.get("research_line") or "Unassigned").strip()
        return [value or "Unassigned"]
    mapping = {
        "domain": "domains",
        "track": "tracks",
        "problem": "problems",
        "topic": "topics",
        "method": "methods",
    }
    values = [str(value).strip() for value in paper.get(mapping[field], []) if str(value).strip()]
    return values or ["Unassigned"]


def taxonomy_node_id(field: str, value: str) -> str:
    return f"{field}:{value}"


def taxonomy_node_href(field: str, value: str) -> str:
    if value == "Unassigned":
        return "library.html"
    query = str(TAXONOMY_MAP_FIELD_BY_KEY[field]["query"])
    return page_query_href("library.html", **{query: value})


def taxonomy_edge_href(source_field: str, source_value: str, target_field: str, target_value: str) -> str:
    params: dict[str, str] = {}
    if source_value != "Unassigned":
        params[str(TAXONOMY_MAP_FIELD_BY_KEY[source_field]["query"])] = source_value
    if target_value != "Unassigned":
        params[str(TAXONOMY_MAP_FIELD_BY_KEY[target_field]["query"])] = target_value
    return page_query_href("library.html", **params) if params else "library.html"


def top_values_for_items(items: list[dict[str, Any]], field: str, limit: int = 6) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for paper in items:
        for value in taxonomy_map_values(paper, field):
            if value != "Unassigned":
                counts[value] += 1
    return [{"value": value, "count": count} for value, count in counts.most_common(limit)]


def build_taxonomy_map_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    node_slugs: dict[tuple[str, str], set[str]] = defaultdict(set)
    edge_slugs: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    slug_to_title = {str(paper["slug"]): paper.get("title_zh") or paper.get("title") or str(paper["slug"]) for paper in papers}

    for paper in papers:
        slug = str(paper["slug"])
        for field in TAXONOMY_MAP_FIELD_BY_KEY:
            for value in taxonomy_map_values(paper, field):
                node_slugs[(field, value)].add(slug)
        for source_field, target_field in TAXONOMY_MAP_EDGE_SPECS:
            for source_value in taxonomy_map_values(paper, source_field):
                for target_value in taxonomy_map_values(paper, target_field):
                    edge_slugs[(source_field, source_value, target_field, target_value)].add(slug)

    nodes = []
    for (field, value), slugs in sorted(node_slugs.items(), key=lambda item: (item[0][0], -len(item[1]), item[0][1].lower())):
        nodes.append(
            {
                "id": taxonomy_node_id(field, value),
                "field": field,
                "label": TAXONOMY_MAP_FIELD_BY_KEY[field]["label"],
                "value": value,
                "count": len(slugs),
                "href": taxonomy_node_href(field, value),
                "sample_slugs": sorted(slugs)[:8],
            }
        )

    edges = []
    for (source_field, source_value, target_field, target_value), slugs in sorted(
        edge_slugs.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][2], item[0][1].lower(), item[0][3].lower()),
    ):
        if source_value == "Unassigned" and target_value == "Unassigned":
            continue
        edges.append(
            {
                "source": taxonomy_node_id(source_field, source_value),
                "target": taxonomy_node_id(target_field, target_value),
                "source_field": source_field,
                "source_value": source_value,
                "target_field": target_field,
                "target_value": target_value,
                "count": len(slugs),
                "href": taxonomy_edge_href(source_field, source_value, target_field, target_value),
                "sample_slugs": sorted(slugs)[:10],
            }
        )

    line_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line_groups[str(paper.get("research_line") or "Unassigned")].append(paper)
    clusters = []
    for line, items in sorted(line_groups.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        clusters.append(
            {
                "research_line": line,
                "count": len(items),
                "href": page_query_href("library.html", line=line) if line != "Unassigned" else "library.html",
                "top_domains": top_values_for_items(items, "domain"),
                "top_tracks": top_values_for_items(items, "track"),
                "top_problems": top_values_for_items(items, "problem"),
                "top_topics": top_values_for_items(items, "topic"),
                "top_methods": top_values_for_items(items, "method"),
                "slugs": sorted(str(paper["slug"]) for paper in items),
            }
        )

    isolated_nodes = []
    connected = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    for node in nodes:
        if node["id"] not in connected and node["value"] != "Unassigned":
            isolated_nodes.append(node)

    recommendations = []
    overloaded_nodes = [node for node in nodes if node["field"] in {"topic", "method", "problem"} and node["count"] >= max(4, len(papers) // 2)]
    if overloaded_nodes:
        recommendations.append(
            f"有 {len(overloaded_nodes)} 个 topic/method/problem 节点覆盖面偏大，可在 taxonomy.html 或 facets.html 中考虑拆分。"
        )
    if isolated_nodes:
        recommendations.append(f"有 {len(isolated_nodes)} 个孤立分类节点，建议检查是否需要合并或补上上游分类。")
    unassigned_count = len(node_slugs.get(("research_line", "Unassigned"), set()))
    if unassigned_count:
        recommendations.append(f"有 {unassigned_count} 篇论文未进入研究线，建议先分配 research_line 再细化下游分类。")
    if not recommendations:
        recommendations.append("当前分类图谱连接正常，可以优先从强边和研究线簇继续扩展。")

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "field_order": TAXONOMY_MAP_FIELDS,
        "edge_specs": [
            {"source_field": source, "target_field": target}
            for source, target in TAXONOMY_MAP_EDGE_SPECS
        ],
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "isolated_nodes": isolated_nodes,
        "recommendations": recommendations,
        "slug_titles": slug_to_title,
    }


def write_taxonomy_map_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_taxonomy_map_payload(papers)
    (report_dir / "taxonomy_map.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


CLUSTER_LABEL_FIELDS = ("domains", "tracks", "problems", "topics", "methods")


def cluster_label_counter(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for field in CLUSTER_LABEL_FIELDS:
        counter = Counter(value for paper in items for value in paper.get(field, []) or [])
        grouped[field] = [{"value": value, "count": count} for value, count in counter.most_common(8)]
    return grouped


def cluster_split_candidates(items: list[dict[str, Any]], cluster_count: int) -> list[dict[str, Any]]:
    candidates = []
    for field in ("tracks", "problems", "topics", "methods"):
        counter = Counter(value for paper in items for value in paper.get(field, []) or [])
        for value, count in counter.most_common(5):
            if count <= 1 or count == cluster_count:
                continue
            share = round(count / cluster_count, 3) if cluster_count else 0
            candidates.append(
                {
                    "field": field,
                    "value": value,
                    "count": count,
                    "share": share,
                    "href": routing_label_href(field, value),
                }
            )
    return sorted(candidates, key=lambda item: (-int(item["count"]), str(item["field"]), str(item["value"])))[:8]


def cluster_risk(cluster_count: int, total: int, split_candidates: list[dict[str, Any]], role_count: int) -> tuple[str, list[str]]:
    reasons = []
    share = cluster_count / total if total else 0
    if cluster_count == 1:
        reasons.append("single-paper cluster")
    if share >= 0.5 and cluster_count >= 8:
        reasons.append("dominates library")
    if cluster_count >= 4 and split_candidates:
        reasons.append("split candidates available")
    if role_count <= 1 and cluster_count >= 3:
        reasons.append("thin line roles")
    if any("dominates" in reason for reason in reasons):
        return "high", reasons
    if reasons:
        return "medium", reasons
    return "low", ["healthy cluster"]


def build_clusters_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(papers)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "Unassigned").strip() or "Unassigned"
        grouped[line].append(paper)

    clusters = []
    for line, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        years = sorted(int(paper.get("year") or 0) for paper in items if paper.get("year"))
        statuses = Counter(str(paper.get("status") or "unknown") for paper in items)
        roles = Counter(str(paper.get("line_role") or "unclassified") for paper in items)
        labels = cluster_label_counter(items)
        splits = cluster_split_candidates(items, len(items))
        risk, reasons = cluster_risk(len(items), total, splits, len(roles))
        owner = research_line_owner(line)
        representatives = sorted(
            items,
            key=lambda paper: (-(int(paper.get("importance") or 0)), -(paper.get("year") or 0), paper["title"]),
        )[:6]
        clusters.append(
            {
                "id": slugify_label(line),
                "name": line,
                "research_line": line,
                "href": f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line),
                "count": len(items),
                "share": round(len(items) / total, 3) if total else 0,
                "risk": risk,
                "risk_reasons": reasons,
                "owner": owner.get("owner", ""),
                "team": owner.get("team", ""),
                "cadence": owner.get("cadence", ""),
                "year_span": [years[0], years[-1]] if years else [],
                "status_counts": [{"value": value, "count": count} for value, count in statuses.most_common()],
                "role_counts": [{"value": value, "count": count} for value, count in roles.most_common()],
                "top_labels": labels,
                "split_candidates": splits,
                "representative_slugs": [paper["slug"] for paper in representatives],
                "representative_papers": [
                    {
                        "slug": paper["slug"],
                        "title": paper.get("title_zh") or paper.get("title") or paper["slug"],
                        "href": paper_href(paper),
                        "importance": paper.get("importance") or "",
                        "year": paper.get("year") or "",
                    }
                    for paper in representatives
                ],
            }
        )

    singleton_clusters = [cluster for cluster in clusters if int(cluster["count"]) == 1]
    large_clusters = [cluster for cluster in clusters if float(cluster["share"]) >= 0.35 and int(cluster["count"]) >= 3]
    recommendations = []
    if large_clusters:
        recommendations.append("优先检查大簇的 split_candidates，把宽泛研究线拆成更稳定的子方向。")
    if singleton_clusters:
        recommendations.append("单论文簇需要判断是新兴方向、临时分类，还是应该并入已有研究线。")
    if not recommendations:
        recommendations.append("当前研究簇分布较稳，可以继续用 routing.html 给新论文分配到现有簇。")

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": total,
        "cluster_count": len(clusters),
        "largest_cluster_share": max((float(cluster["share"]) for cluster in clusters), default=0),
        "clusters": clusters,
        "recommendations": recommendations,
        "links": {
            "routing": "routing.html",
            "taxonomy_map": "taxonomy_map.html",
            "coverage": "coverage.html",
            "balance": "balance.html",
            "ownership": "ownership.html",
        },
    }


def write_clusters_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_clusters_payload(papers)
    (report_dir / "clusters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


ROADMAP_RECOMMENDED_ROLES = ["foundation", "baseline", "main", "system"]


def roadmap_paper_summary(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or paper["slug"],
        "title_zh": paper.get("title_zh") or "",
        "year": paper.get("year") or "",
        "role": paper.get("line_role") or "unclassified",
        "status": paper.get("status") or "",
        "importance": paper.get("importance") or "",
        "has_code": bool(paper.get("has_code")),
        "topics": paper.get("topics") or [],
        "methods": paper.get("methods") or [],
        "href": paper_href(paper),
    }


def roadmap_risk(score: int) -> str:
    if score < 55:
        return "high"
    if score < 78:
        return "medium"
    return "low"


def build_roadmap_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    taxonomy_load_by_slug = {item["slug"]: item for item in quality.get("taxonomy_load", [])}
    review_needs_plan = set(review.get("queues", {}).get("needs_plan", []))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)

    roadmaps: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    current_year = dt.date.today().year
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name == "Unassigned", name.lower())):
        items = sorted(grouped[line], key=lambda paper: (role_rank(str(paper.get("line_role") or "")), -(int(paper.get("year") or 0)), paper["title"]))
        owner_config = RESEARCH_LINE_OWNERS.get(line, {})
        role_counts = Counter(str(paper.get("line_role") or "unclassified") for paper in items)
        missing_roles = [role for role in ROADMAP_RECOMMENDED_ROLES if role_counts.get(role, 0) == 0]
        years = sorted({int(paper["year"]) for paper in items if isinstance(paper.get("year"), int)})
        latest_year = max(years) if years else None
        first_year = min(years) if years else None
        stale_years = current_year - latest_year if latest_year else None
        missing_taxonomy = [
            paper["slug"]
            for paper in items
            if not paper.get("domains")
            or not paper.get("tracks")
            or not paper.get("problems")
            or not paper.get("topics")
            or not paper.get("methods")
            or not paper.get("line_role")
        ]
        no_review = [paper["slug"] for paper in items if not paper.get("next_review")]
        no_code = [paper["slug"] for paper in items if not paper.get("has_code")]
        taxonomy_load = [paper["slug"] for paper in items if paper["slug"] in taxonomy_load_by_slug]
        needs_plan = [paper["slug"] for paper in items if paper["slug"] in review_needs_plan]
        score = 100
        score -= len(missing_roles) * 9
        score -= min(22, len(missing_taxonomy) * 7)
        score -= min(16, len(taxonomy_load) * 4)
        score -= min(18, len(no_review) * 4)
        score -= min(12, len(no_code) * 3)
        if stale_years is None:
            score -= 10
        elif stale_years >= 2:
            score -= min(18, stale_years * 4)
        score = max(0, score)
        risk = roadmap_risk(score)

        actions: list[dict[str, Any]] = []
        if missing_roles:
            actions.append({"type": "role_gap", "priority": 100 - score + len(missing_roles), "label": f"补齐角色：{', '.join(missing_roles)}", "href": page_query_href("library.html", line=line), "slugs": []})
        if stale_years is None:
            actions.append({"type": "year_gap", "priority": 82, "label": "补齐年份信息，建立时间线基准", "href": page_query_href("library.html", line=line), "slugs": [paper["slug"] for paper in items if not paper.get("year")][:8]})
        elif stale_years >= 2:
            actions.append({"type": "freshness_gap", "priority": min(95, 62 + stale_years * 6), "label": f"检索 {latest_year + 1}-{current_year} 后续工作", "href": page_query_href("freshness.html", line=line), "slugs": []})
        if needs_plan or no_review:
            targets = needs_plan or no_review
            actions.append({"type": "review_plan", "priority": min(90, 55 + len(targets) * 4), "label": f"补复习计划 {len(targets)} 篇", "href": page_query_href("review.html", line=line), "slugs": targets[:10]})
        if missing_taxonomy:
            actions.append({"type": "metadata_gap", "priority": min(88, 54 + len(missing_taxonomy) * 5), "label": f"补 taxonomy {len(missing_taxonomy)} 篇", "href": page_query_href("library.html", line=line), "slugs": missing_taxonomy[:10]})
        if taxonomy_load:
            actions.append({"type": "taxonomy_load", "priority": min(80, 46 + len(taxonomy_load) * 4), "label": f"审分类粒度 {len(taxonomy_load)} 篇", "href": page_query_href("quality.html", line=line), "slugs": taxonomy_load[:10]})
        if no_code:
            actions.append({"type": "code_observation", "priority": min(72, 42 + len(no_code) * 3), "label": f"补代码观察 {len(no_code)} 篇", "href": page_query_href("library.html", line=line), "slugs": no_code[:10]})
        if not actions:
            actions.append({"type": "maintain", "priority": 20, "label": "保持观察，等待新论文进入 intake", "href": "intake.html", "slugs": []})

        milestones = []
        for year in years:
            year_items = [paper for paper in items if paper.get("year") == year]
            representatives = sorted(year_items, key=lambda paper: (-(int(paper.get("importance") or 0)), role_rank(str(paper.get("line_role") or "")), paper["title"]))[:4]
            milestones.append(
                {
                    "year": year,
                    "count": len(year_items),
                    "roles": dict(sorted(Counter(str(paper.get("line_role") or "unclassified") for paper in year_items).items(), key=lambda pair: (role_rank(pair[0]), pair[0]))),
                    "representative_slugs": [paper["slug"] for paper in representatives],
                }
            )

        representative_papers = sorted(items, key=lambda paper: (-(int(paper.get("importance") or 0)), role_rank(str(paper.get("line_role") or "")), -(int(paper.get("year") or 0)), paper["title"]))[:5]
        top_topics = Counter(topic for paper in items for topic in paper.get("topics", []))
        top_methods = Counter(method for paper in items for method in paper.get("methods", []))
        roadmap = {
            "id": slugify_label(line),
            "line": line,
            "href": f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line="Unassigned"),
            "library_href": page_query_href("library.html", line=line),
            "count": len(items),
            "owner": owner_config.get("owner") or "unassigned",
            "team": owner_config.get("team") or "",
            "cadence": owner_config.get("cadence") or "",
            "risk": risk,
            "score": score,
            "first_year": first_year,
            "latest_year": latest_year,
            "year_span": (latest_year - first_year + 1) if first_year and latest_year else 0,
            "role_counts": dict(sorted(role_counts.items(), key=lambda pair: (role_rank(pair[0]), pair[0]))),
            "missing_roles": missing_roles,
            "top_topics": top_counts(dict(top_topics.most_common(8)), 8),
            "top_methods": top_counts(dict(top_methods.most_common(8)), 8),
            "milestones": milestones,
            "representative_papers": [roadmap_paper_summary(paper) for paper in representative_papers],
            "queues": {
                "missing_taxonomy": missing_taxonomy,
                "taxonomy_load": taxonomy_load,
                "needs_review_plan": needs_plan,
                "no_review": no_review,
                "no_code_observation": no_code,
            },
            "actions": actions,
        }
        roadmaps.append(roadmap)
        for action in actions:
            action_items.append({"line": line, "risk": risk, "score": score, **action})

    action_items = sorted(action_items, key=lambda item: (-int(item["priority"]), item["line"], item["type"]))
    risk_counts = dict(sorted(Counter(item["risk"] for item in roadmaps).items()))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "line_count": len(roadmaps),
        "risk_counts": risk_counts,
        "recommended_roles": ROADMAP_RECOMMENDED_ROLES,
        "roadmaps": roadmaps,
        "actions": action_items,
        "links": {
            "library": "library.html",
            "lines": "lines/index.html",
            "clusters": "clusters.html",
            "gaps": "gaps.html",
            "timeline": "timeline.html",
            "matrix": "matrix.html",
            "intake": "intake.html",
        },
    }


def write_roadmap_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_roadmap_payload(papers)
    (report_dir / "roadmap.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


SCALE_CORE_RESOURCES = [
    "papers.json",
    "search_index.json",
    "stats.json",
    "quality.json",
    "review.json",
    "freshness.json",
    "taxonomy_actions.json",
    "actions.json",
    "workflow.json",
    "pivot.json",
    "compare.json",
    "taxonomy_map.json",
    "inbox.json",
]


def scale_resource_sizes(report_dir: Path) -> list[dict[str, Any]]:
    resources = []
    for href in SCALE_CORE_RESOURCES:
        path = report_dir / href
        resources.append(
            {
                "href": href,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    return resources


def scale_project_bytes(current_bytes: int, current_count: int, target_count: int) -> int:
    if current_count <= 0:
        return 0
    return int(round((current_bytes / current_count) * target_count))


def scale_risk_item(
    severity: str,
    area: str,
    signal: str,
    recommendation: str,
    href: str,
    command: str = "",
) -> dict[str, Any]:
    rank = {"high": 90, "medium": 60, "low": 30, "none": 0}.get(severity, 0)
    return {
        "severity": severity,
        "rank": rank,
        "area": area,
        "signal": signal,
        "recommendation": recommendation,
        "href": href,
        "command": command,
    }


def build_scale_payload(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(papers)
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    freshness = build_freshness_report(papers)
    actions = build_action_center(papers, inbox_items)
    taxonomy_map = build_taxonomy_map_payload(papers)
    stats = build_stats_report(papers)
    resources = scale_resource_sizes(report_dir)
    controls = control_options()
    status_workflows = controls.get("status_workflows") or {}
    active_status_workflow = controls.get("active_status_workflow") or next(iter(status_workflows), "")
    active_workflow = status_workflows.get(active_status_workflow, {}) if isinstance(status_workflows, dict) else {}
    status_workflow = {
        "active": active_status_workflow,
        "workflow_count": len(status_workflows) if isinstance(status_workflows, dict) else 0,
        "status_count": len(active_workflow.get("status_values") or controls.get("status") or []),
        "reading_stage_count": len(active_workflow.get("reading_stage_values") or controls.get("reading_stage") or []),
        "review_stage_count": len(active_workflow.get("review_stage_values") or controls.get("review_stage") or []),
        "href": "workflow.html",
    }
    resource_by_href = {item["href"]: item for item in resources}
    search_bytes = int(resource_by_href.get("search_index.json", {}).get("size_bytes") or 0)
    papers_bytes = int(resource_by_href.get("papers.json", {}).get("size_bytes") or 0)
    taxonomy_map_bytes = int(resource_by_href.get("taxonomy_map.json", {}).get("size_bytes") or 0)
    action_count = int(actions.get("count") or 0)
    line_count = len(stats.get("research_lines", []))
    largest_line = max((int(line.get("count") or 0) for line in stats.get("research_lines", [])), default=0)
    largest_line_share = round(largest_line / count, 3) if count else 0
    taxonomy_node_count = len(taxonomy_map.get("nodes", []))
    taxonomy_edge_count = len(taxonomy_map.get("edges", []))
    taxonomy_edges_per_paper = round(taxonomy_edge_count / count, 1) if count else 0
    queue_sizes = {
        "quality": {name: len(slugs) for name, slugs in quality["queues"].items()},
        "review": {name: len(slugs) for name, slugs in review["queues"].items()},
        "freshness": {name: len(slugs) for name, slugs in freshness["queues"].items()},
        "actions": action_count,
        "inbox": len(inbox_items),
    }

    bottlenecks: list[dict[str, Any]] = []
    review_gap = int(queue_sizes["review"].get("needs_plan", 0))
    taxonomy_sparse = int(queue_sizes["quality"].get("taxonomy_sparse", 0))
    taxonomy_dense = int(queue_sizes["quality"].get("taxonomy_dense", 0))
    taxonomy_drift = int(queue_sizes["quality"].get("taxonomy_drift", 0))
    duplicate_reports = int(queue_sizes["quality"].get("duplicate_reports", 0))
    no_code = int(queue_sizes["quality"].get("no_code_observation", 0))
    stale = int(queue_sizes["freshness"].get("stale", 0))

    if review_gap:
        severity = "high" if review_gap / max(count, 1) >= 0.35 else "medium"
        bottlenecks.append(
            scale_risk_item(
                severity,
                "review",
                f"{review_gap} 篇论文缺 next_review",
                "先用 review.html 或 apply_review_plan.py 建立复习节奏，避免大库里旧论文沉底。",
                "review.html",
                "python3 scripts/apply_review_plan.py docs --write",
            )
        )
    if taxonomy_sparse or taxonomy_dense or taxonomy_drift:
        severity = "high" if taxonomy_drift or taxonomy_dense else "medium"
        bottlenecks.append(
            scale_risk_item(
                severity,
                "taxonomy",
                f"sparse={taxonomy_sparse}, dense={taxonomy_dense}, drift={taxonomy_drift}",
                "优先处理 taxonomy drift，再用分类图谱和 facets 拆分过载节点、合并长尾标签。",
                "facets.html",
                "python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv",
            )
        )
    if duplicate_reports:
        bottlenecks.append(
            scale_risk_item(
                "high",
                "dedupe",
                f"{duplicate_reports} 个重复报告相关条目",
                "发布前先处理重复报告，避免开源协作里同一论文被多份报告分裂。",
                "quality.html",
            )
        )
    if action_count > max(24, count * 8):
        bottlenecks.append(
            scale_risk_item(
                "medium",
                "operations",
                f"{action_count} 个统一行动项",
                "行动队列已经偏长，建议导出项目任务并按 owner/status 分派。",
                "actions.html",
                "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv",
            )
        )
    if no_code / max(count, 1) >= 0.5:
        bottlenecks.append(
            scale_risk_item(
                "medium",
                "reproducibility",
                f"{no_code} 篇论文缺代码观察或代码线索",
                "对高重要性论文优先补代码观察，降低后续复现实验和桌面端检索的不确定性。",
                "library.html?code=no&sort=importance",
            )
        )
    if stale:
        bottlenecks.append(
            scale_risk_item(
                "medium",
                "freshness",
                f"{stale} 篇报告已过期",
                "用 freshness.html 处理过期报告，避免旧结论被当作当前事实。",
                "freshness.html",
            )
        )
    if largest_line_share >= 0.6 and count >= 5:
        bottlenecks.append(
            scale_risk_item(
                "low",
                "portfolio",
                f"最大研究线占比 {largest_line_share:.0%}",
                "研究线集中度较高；如果继续增长，可用 collections 和 matrix 拆出子线或阶段队列。",
                "collections.html",
            )
        )
    if taxonomy_edges_per_paper >= 35:
        bottlenecks.append(
            scale_risk_item(
                "low",
                "taxonomy_graph",
                f"平均每篇 {taxonomy_edges_per_paper} 条分类边",
                "分类图谱边密度偏高，后续可限制 topic/method 数或提高标签合并频率。",
                "taxonomy_map.html",
            )
        )
    if int(status_workflow["workflow_count"]) <= 1 and count >= 100:
        bottlenecks.append(
            scale_risk_item(
                "low",
                "workflow",
                "当前只有 1 套状态体系",
                "论文过百后建议保留 personal / research / implementation 等多套 status_workflows，并按场景动态切换。",
                "workflow.html",
                "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write",
            )
        )
    if not bottlenecks:
        bottlenecks.append(
            scale_risk_item(
                "none",
                "readiness",
                "当前没有明显规模瓶颈",
                "保持质量门、分类图谱和复习计划的周期性检查即可。",
                "dashboard.html",
            )
        )

    penalty = 0
    penalty += min(25, int(review_gap / max(count, 1) * 60))
    penalty += min(20, taxonomy_sparse + taxonomy_dense * 2 + taxonomy_drift * 4)
    penalty += min(20, int(action_count / max(count, 1)))
    penalty += min(15, duplicate_reports * 5)
    penalty += min(10, int(no_code / max(count, 1) * 20))
    readiness_score = max(0, 100 - penalty)
    if readiness_score >= 85:
        readiness_label = "ready"
    elif readiness_score >= 70:
        readiness_label = "watch"
    else:
        readiness_label = "needs_governance"

    capacity_projection = []
    for target in (100, 500, 1000, 5000):
        capacity_projection.append(
            {
                "paper_count": target,
                "search_index_bytes": scale_project_bytes(search_bytes, count, target),
                "papers_json_bytes": scale_project_bytes(papers_bytes, count, target),
                "taxonomy_map_bytes": scale_project_bytes(taxonomy_map_bytes, count, target),
                "estimated_actions": scale_project_bytes(action_count, count, target),
                "recommended_mode": "static wiki" if target <= 500 else ("split indexes" if target <= 1000 else "desktop cache / paged indexes"),
            }
        )

    scale_tiers = [
        {"tier": "personal", "paper_range": "0-100", "mode": "单目录静态 wiki", "priority": "保持 frontmatter 完整和复习计划"},
        {"tier": "serious_library", "paper_range": "100-500", "mode": "静态 wiki + 强制质量门", "priority": "拆分过载 taxonomy，固定共享视图"},
        {"tier": "large_library", "paper_range": "500-1000", "mode": "分片索引 + 项目化治理", "priority": "按研究线 owner / 队列治理行动项"},
        {"tier": "desktop_scale", "paper_range": "1000+", "mode": "桌面缓存或分页索引", "priority": "将 search/action/taxonomy graph 改为增量同步"},
    ]

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": count,
        "readiness_score": readiness_score,
        "readiness_label": readiness_label,
        "line_count": line_count,
        "largest_line_share": largest_line_share,
        "taxonomy_node_count": taxonomy_node_count,
        "taxonomy_edge_count": taxonomy_edge_count,
        "taxonomy_edges_per_paper": taxonomy_edges_per_paper,
        "status_workflow": status_workflow,
        "resource_sizes": resources,
        "queue_sizes": queue_sizes,
        "bottlenecks": sorted(bottlenecks, key=lambda item: (-int(item["rank"]), item["area"], item["signal"])),
        "capacity_projection": capacity_projection,
        "scale_tiers": scale_tiers,
        "links": {
            "dashboard": "dashboard.html",
            "quality": "quality.html",
            "taxonomy_map": "taxonomy_map.html",
            "actions": "actions.html",
            "release": "release.html",
            "catalog": "catalog.html",
        },
    }


def write_scale_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_scale_payload(report_dir, papers, inbox_items)
    (report_dir / "scale.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_ownership_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    freshness = build_freshness_report(papers)
    stale_slugs = set(freshness.get("queues", {}).get("stale", []))
    due_freshness_slugs = set(freshness.get("queues", {}).get("due", []))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "Unassigned").strip() or "Unassigned"
        grouped[line].append(paper)

    line_rows: list[dict[str, Any]] = []
    owner_rows: dict[str, dict[str, Any]] = {}
    for line, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        owner = research_line_owner(line)
        owner_name = owner.get("owner") or "Unassigned"
        owner_key = owner_name if owner_name != "Unassigned" else f"Unassigned:{line}"
        team = owner.get("team", "")
        missing_taxonomy = [
            paper
            for paper in items
            if not paper.get("domains")
            or not paper.get("tracks")
            or not paper.get("topics")
            or not paper.get("methods")
            or paper.get("research_line") == "Unassigned"
            or not paper.get("line_role")
        ]
        needs_review_plan = [paper for paper in items if not paper.get("next_review")]
        due_review = [paper for paper in items if paper.get("next_review") and str(paper.get("next_review")) <= today]
        no_code = [paper for paper in items if not paper.get("has_code")]
        stale = [paper for paper in items if paper.get("slug") in stale_slugs]
        freshness_due = [paper for paper in items if paper.get("slug") in due_freshness_slugs]
        queue_counts = {
            "missing_taxonomy": len(missing_taxonomy),
            "needs_review_plan": len(needs_review_plan),
            "due_review": len(due_review),
            "freshness_due": len(freshness_due),
            "stale": len(stale),
            "no_code_observation": len(no_code),
        }
        risk_points = (
            queue_counts["missing_taxonomy"] * 3
            + queue_counts["needs_review_plan"] * 2
            + queue_counts["due_review"] * 2
            + queue_counts["stale"] * 2
            + queue_counts["no_code_observation"]
        )
        risk = "high" if risk_points >= max(4, len(items) * 3) else "medium" if risk_points else "low"
        code_count = sum(1 for paper in items if paper.get("has_code"))
        avg_importance = round(sum(int(paper.get("importance") or 0) for paper in items) / len(items), 1) if items else 0
        line_row = {
            "line": line,
            "href": f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line),
            "owner": owner_name,
            "team": team,
            "cadence": owner.get("cadence", ""),
            "note": owner.get("note", ""),
            "count": len(items),
            "avg_importance": avg_importance,
            "code_coverage": percent(code_count, len(items)),
            "risk": risk,
            "risk_points": risk_points,
            "queues": queue_counts,
            "sample_slugs": [str(paper["slug"]) for paper in items[:6]],
        }
        line_rows.append(line_row)
        owner_row = owner_rows.setdefault(
            owner_key,
            {
                "owner": owner_name,
                "team": team,
                "line_count": 0,
                "paper_count": 0,
                "risk_points": 0,
                "queues": Counter(),
                "lines": [],
            },
        )
        if not owner_row.get("team") and team:
            owner_row["team"] = team
        owner_row["line_count"] += 1
        owner_row["paper_count"] += len(items)
        owner_row["risk_points"] += risk_points
        owner_row["queues"].update(queue_counts)
        owner_row["lines"].append(line_row)

    owners: list[dict[str, Any]] = []
    for owner in owner_rows.values():
        queue_counts = dict(owner["queues"])
        risk_points = int(owner["risk_points"])
        paper_count = int(owner["paper_count"])
        owner["risk"] = "high" if risk_points >= max(6, paper_count * 3) else "medium" if risk_points else "low"
        owner["queues"] = queue_counts
        owner["lines"] = sorted(owner["lines"], key=lambda item: (-int(item["risk_points"]), item["line"].lower()))
        owners.append(owner)
    owners.sort(key=lambda item: (-int(item["risk_points"]), -int(item["paper_count"]), str(item["owner"]).lower()))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "owner_count": len(owners),
        "unassigned_line_count": sum(1 for line in line_rows if line["owner"] == "Unassigned"),
        "owners": owners,
        "lines": sorted(line_rows, key=lambda item: (-int(item["risk_points"]), item["line"].lower())),
        "links": {
            "dashboard": "dashboard.html",
            "coverage": "coverage.html",
            "actions": "actions.html",
            "taxonomy": "taxonomy.html",
            "stats": "stats.json",
        },
    }


def write_ownership_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_ownership_payload(papers)
    (report_dir / "ownership.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


ROUTING_STOPWORDS = {
    "about",
    "across",
    "after",
    "also",
    "among",
    "based",
    "baseline",
    "between",
    "from",
    "into",
    "large",
    "model",
    "models",
    "paper",
    "using",
    "with",
    "without",
    "this",
    "that",
    "their",
    "these",
    "those",
    "through",
    "toward",
    "towards",
    "where",
    "which",
    "while",
}


def routing_tokenize(text: str) -> Counter:
    tokens: Counter[str] = Counter()
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]{1,}|[\u4e00-\u9fff]{2,}", str(text or "")):
        token = raw.lower().strip(".+-")
        if not token:
            continue
        if re.fullmatch(r"[a-z0-9.+-]+", token):
            token = label_fingerprint(token)
            parts = [part for part in token.split() if part and part not in ROUTING_STOPWORDS]
            for part in parts:
                if len(part) >= 3 or part in {"ai", "kv"}:
                    tokens[part] += 1
            if len(parts) > 1:
                phrase = " ".join(parts)
                tokens[phrase] += 2
        elif len(token) >= 2:
            tokens[token] += 1
    return tokens


def routing_label_terms(label: str, weight: int = 5) -> Counter:
    counter = routing_tokenize(label)
    return Counter({term: value * weight for term, value in counter.items()})


def routing_paper_terms(paper: dict[str, Any]) -> Counter:
    terms = Counter()
    text_parts = [
        paper.get("title"),
        paper.get("title_en"),
        paper.get("title_zh"),
        paper.get("excerpt"),
        paper.get("essence"),
        str(paper.get("_search_text") or "")[:6000],
    ]
    for part in text_parts:
        terms.update(routing_tokenize(str(part or "")))
    for field, weight in (
        ("domains", 7),
        ("tracks", 7),
        ("problems", 6),
        ("topics", 5),
        ("methods", 5),
    ):
        for value in paper.get(field, []) or []:
            terms.update(routing_label_terms(str(value), weight))
    for value, weight in ((paper.get("research_line"), 8), (paper.get("line_role"), 3)):
        if value:
            terms.update(routing_label_terms(str(value), weight))
    return terms


def routing_terms_payload(counter: Counter, limit: int = 40) -> list[dict[str, Any]]:
    return [
        {"term": str(term), "weight": int(weight)}
        for term, weight in counter.most_common(limit)
        if str(term).strip()
    ]


def routing_label_href(field: str, value: str) -> str:
    key = {
        "domains": "domain",
        "tracks": "track",
        "problems": "problem",
        "topics": "topic",
        "methods": "method",
    }.get(field, "q")
    return page_query_href("library.html", **{key: value})


def build_routing_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    paper_terms = {paper["slug"]: routing_paper_terms(paper) for paper in papers}
    label_fields = ("domains", "tracks", "problems", "topics", "methods")
    line_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    label_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "Unassigned").strip() or "Unassigned"
        line_groups[line].append(paper)
        for field in label_fields:
            for value in paper.get(field, []) or []:
                label_groups[(field, str(value))].append(paper)

    line_profiles = []
    for line, items in sorted(line_groups.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        terms = Counter()
        labels = Counter()
        for paper in items:
            terms.update(paper_terms[paper["slug"]])
            for field in label_fields:
                labels.update(str(value) for value in paper.get(field, []) or [])
        terms.update(routing_label_terms(line, 10))
        owner = research_line_owner(line)
        sample_papers = sorted(items, key=lambda paper: (-(int(paper.get("importance") or 0)), -(paper.get("year") or 0), paper["title"]))[:6]
        line_profiles.append(
            {
                "line": line,
                "count": len(items),
                "href": f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line),
                "owner": owner.get("owner", ""),
                "team": owner.get("team", ""),
                "top_labels": [{"label": label, "count": count} for label, count in labels.most_common(12)],
                "terms": routing_terms_payload(terms, 48),
                "sample_slugs": [paper["slug"] for paper in sample_papers],
            }
        )

    label_profiles = []
    for (field, value), items in sorted(label_groups.items(), key=lambda item: (item[0][0], item[0][1].lower())):
        terms = routing_label_terms(value, 10)
        for paper in items:
            terms.update(paper_terms[paper["slug"]])
        label_profiles.append(
            {
                "field": field,
                "value": value,
                "count": len(items),
                "href": routing_label_href(field, value),
                "terms": routing_terms_payload(terms, 36),
                "sample_slugs": [paper["slug"] for paper in items[:6]],
            }
        )

    paper_signatures = []
    for paper in papers:
        paper_signatures.append(
            {
                "slug": paper["slug"],
                "title": paper.get("title_zh") or paper.get("title") or paper["slug"],
                "title_en": paper.get("title_en") or "",
                "href": paper_href(paper),
                "year": paper.get("year"),
                "research_line": paper.get("research_line") or "Unassigned",
                "domains": paper.get("domains", []),
                "tracks": paper.get("tracks", []),
                "problems": paper.get("problems", []),
                "topics": paper.get("topics", []),
                "methods": paper.get("methods", []),
                "terms": routing_terms_payload(paper_terms[paper["slug"]], 50),
            }
        )

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "line_count": len(line_profiles),
        "label_count": len(label_profiles),
        "paper_count": len(paper_signatures),
        "tokenizer": {
            "version": 1,
            "stopwords": sorted(ROUTING_STOPWORDS),
            "description": "Lowercase latin terms, split punctuation, keep CJK runs, boost existing taxonomy labels.",
        },
        "weights": {
            "research_line": 8,
            "taxonomy_label": 5,
            "label_profile": 10,
            "paper_text": 1,
        },
        "line_profiles": line_profiles,
        "label_profiles": label_profiles,
        "paper_signatures": paper_signatures,
        "input_contract": {
            "title": "Paper title or method name",
            "abstract": "Abstract, introduction snippet, or user notes",
            "keywords": "Optional comma-separated hints such as model, task, method, codebase",
        },
        "links": {
            "library": "library.html",
            "taxonomy": "taxonomy.html",
            "inbox": "inbox.html",
            "quality": "quality.html",
        },
    }


def write_routing_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_routing_payload(papers)
    (report_dir / "routing.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


COMPARE_FIELDS = [
    {"key": "title_zh", "label": "中文标题", "group": "identity"},
    {"key": "title_en", "label": "英文标题", "group": "identity"},
    {"key": "year", "label": "年份", "group": "identity"},
    {"key": "arxiv_id", "label": "arXiv", "group": "identity"},
    {"key": "research_line", "label": "研究线", "group": "taxonomy"},
    {"key": "line_role", "label": "研究线角色", "group": "taxonomy"},
    {"key": "domains", "label": "Domains", "group": "taxonomy"},
    {"key": "tracks", "label": "Tracks", "group": "taxonomy"},
    {"key": "problems", "label": "Problems", "group": "taxonomy"},
    {"key": "topics", "label": "Topics", "group": "taxonomy"},
    {"key": "methods", "label": "Methods", "group": "taxonomy"},
    {"key": "status", "label": "状态", "group": "workflow"},
    {"key": "reading_stage", "label": "阅读阶段", "group": "workflow"},
    {"key": "review_stage", "label": "复习阶段", "group": "workflow"},
    {"key": "next_review", "label": "下次复习", "group": "workflow"},
    {"key": "importance", "label": "重要性", "group": "score"},
    {"key": "confidence", "label": "置信度", "group": "score"},
    {"key": "reproducibility", "label": "可复现性", "group": "score"},
    {"key": "has_code", "label": "代码", "group": "evidence"},
    {"key": "code_url", "label": "代码链接", "group": "evidence"},
    {"key": "excerpt", "label": "摘要", "group": "notes"},
    {"key": "essence", "label": "一句话精髓", "group": "notes"},
]


def compare_paper_payload(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "href": paper.get("html_path") or paper.get("md_path") or "",
        "title": paper.get("title") or "",
        "title_zh": paper.get("title_zh") or paper.get("title") or "",
        "title_en": paper.get("title_en") or paper.get("title") or "",
        "year": paper.get("year") or "",
        "arxiv_id": paper.get("arxiv_id") or "",
        "arxiv_url": paper.get("arxiv_url") or "",
        "code_url": paper.get("code_url") or "",
        "authors": paper.get("authors", []),
        "research_line": paper.get("research_line") or "Unassigned",
        "line_role": paper.get("line_role") or "",
        "domains": paper.get("domains", []),
        "tracks": paper.get("tracks", []),
        "problems": paper.get("problems", []),
        "topics": paper.get("topics", []),
        "methods": paper.get("methods", []),
        "status": paper.get("status") or "",
        "reading_stage": paper.get("reading_stage") or "",
        "review_stage": paper.get("review_stage") or "",
        "next_review": paper.get("next_review") or "",
        "importance": paper.get("importance") or "",
        "confidence": paper.get("confidence") or "",
        "reproducibility": paper.get("reproducibility") or "",
        "has_code": bool(paper.get("has_code")),
        "excerpt": paper.get("excerpt") or "",
        "essence": paper.get("essence") or "",
    }


def build_compare_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_by_importance = sorted(
        papers,
        key=lambda paper: (-(int(paper.get("importance") or 0)), -(int(paper.get("year") or 0)), paper["title"]),
    )
    suggested_sets: list[dict[str, Any]] = [
        {
            "name": "高优先级论文",
            "kind": "priority",
            "slugs": [paper["slug"] for paper in sorted_by_importance if int(paper.get("importance") or 0) >= 5][:8],
        },
        {
            "name": "缺复习计划",
            "kind": "workflow",
            "slugs": [paper["slug"] for paper in papers if not paper.get("next_review")][:12],
        },
    ]
    grouped_lines: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_tracks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped_lines[str(paper.get("research_line") or "Unassigned")].append(paper)
        for track in paper.get("tracks", []) or []:
            grouped_tracks[str(track)].append(paper)
    for line, items in sorted(grouped_lines.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        if line == "Unassigned" or len(items) < 2:
            continue
        suggested_sets.append(
            {
                "name": f"研究线：{line}",
                "kind": "research_line",
                "slugs": [paper["slug"] for paper in sorted(items, key=lambda p: (role_rank(str(p.get("line_role") or "")), -(int(p.get("year") or 0)), p["title"]))][:10],
            }
        )
    for track, items in sorted(grouped_tracks.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        if len(items) < 2:
            continue
        suggested_sets.append(
            {
                "name": f"方向：{track}",
                "kind": "track",
                "slugs": [paper["slug"] for paper in sorted(items, key=lambda p: (-(int(p.get("importance") or 0)), p["title"]))][:10],
            }
        )
    suggested_sets = [item for item in suggested_sets if item["slugs"]]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "fields": COMPARE_FIELDS,
        "papers": [compare_paper_payload(paper) for paper in papers],
        "suggested_sets": suggested_sets,
        "controls": control_options(),
    }


def write_compare_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_compare_payload(papers)
    (report_dir / "compare.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


DATA_CONSUMER_HINTS = {
    "papers.json": ["frontend", "desktop", "search", "filters"],
    "search_index.json": ["search", "desktop"],
    "stats.json": ["dashboard", "ops", "analytics"],
    "quality.json": ["quality-gate", "ops", "writeback"],
    "review.json": ["review", "scheduler", "writeback"],
    "freshness.json": ["freshness", "maintenance"],
    "taxonomy_actions.json": ["taxonomy", "project-management", "writeback"],
    "actions.json": ["tasks", "project-management", "exports"],
    "command.json": ["command-center", "desktop", "navigation", "ops"],
    "workflow.json": ["workflow", "desktop", "filters"],
    "status.json": ["workflow", "runtime-selector", "desktop"],
    "views.json": ["saved-views", "shared-views", "workflow", "desktop"],
    "batch.json": ["batch-planning", "classification", "ops", "desktop"],
    "collections.json": ["collections", "shared-views", "queues", "desktop"],
    "coverage.json": ["coverage", "taxonomy", "project-management", "desktop"],
    "gaps.json": ["research-gaps", "planning", "project-management", "desktop"],
    "pivot.json": ["analytics", "classification", "desktop"],
    "compare.json": ["comparison", "curation", "desktop"],
    "taxonomy_map.json": ["taxonomy", "graph", "desktop"],
    "clusters.json": ["taxonomy", "clusters", "curation"],
    "roadmap.json": ["research-lines", "planning", "desktop"],
    "scale.json": ["ops", "capacity-planning", "desktop"],
    "ownership.json": ["ops", "owners", "project-management"],
    "routing.json": ["taxonomy", "intake", "classification"],
    "onboarding.json": ["open-source", "contributors", "desktop"],
    "snapshot.json": ["release", "audit", "desktop"],
    "intake.json": ["intake", "dedupe", "bulk-import"],
    "inbox.json": ["intake", "dedupe"],
    "dedupe.json": ["dedupe", "quality", "curation", "desktop"],
    "registry.json": ["taxonomy", "registry", "curation", "desktop"],
    "manifest.json": ["release", "audit", "ci"],
}

CATALOG_STATIC_SIZE_RESOURCES = {"catalog.json", "manifest.json"}


def summarize_json_resource(report_dir: Path, href: str, description: str) -> dict[str, Any]:
    path = report_dir / href
    payload: dict[str, Any] | None = None
    error = ""
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            error = str(exc)
    top_level_keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    collections = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                collections.append({"key": key, "type": "list", "count": len(value)})
            elif isinstance(value, dict):
                collections.append({"key": key, "type": "object", "count": len(value)})
    return {
        "href": href,
        "description": description,
        "exists": path.exists(),
        "size_bytes": 0 if href in CATALOG_STATIC_SIZE_RESOURCES else (path.stat().st_size if path.exists() else 0),
        "top_level_keys": top_level_keys,
        "collections": collections,
        "declared_count": payload.get("count") if isinstance(payload, dict) else None,
        "generated_at": payload.get("generated_at") if isinstance(payload, dict) else "",
        "consumers": DATA_CONSUMER_HINTS.get(href, []),
        "error": error,
    }


def build_catalog_payload(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    pages = wiki_pages_manifest()
    data_files = data_files_manifest()
    contracts = contract_files_manifest()
    data_resources = [
        summarize_json_resource(report_dir, item["href"], item["description"])
        for item in data_files
        if item["href"] != "catalog.json"
    ]
    catalog_self = {
        "href": "catalog.json",
        "description": "机器数据、页面入口和契约字段目录",
        "exists": True,
        "size_bytes": 0,
        "top_level_keys": [
            "generated_at",
            "count",
            "inbox_count",
            "page_count",
            "data_file_count",
            "contract_count",
            "pages",
            "data_resources",
            "contracts",
            "integration_recipes",
            "recommended_bootstrap_files",
        ],
        "collections": [],
        "declared_count": len(papers),
        "generated_at": "",
        "consumers": ["desktop", "api", "open-source-onboarding"],
        "error": "",
    }
    data_resources.append(catalog_self)
    integration_recipes = [
        {
            "name": "Build local wiki",
            "command": "python3 scripts/build_wiki.py docs",
            "uses": ["docs/*.md", "docs/guides/taxonomy.json"],
            "outputs": ["docs/index.html", "docs/papers.json", "docs/manifest.json"],
        },
        {
            "name": "Validate publish readiness",
            "command": "python3 scripts/check_quality.py docs",
            "uses": ["docs/manifest.json", "docs/quality.json", "docs/workflow.json"],
            "outputs": ["terminal quality gate result"],
        },
        {
            "name": "Desktop sync bootstrap",
            "command": "read docs/catalog.json, docs/papers.json, docs/search_index.json",
            "uses": ["catalog.json", "papers.json", "search_index.json", "workflow.json", "status.json", "views.json", "batch.json", "collections.json", "coverage.json", "gaps.json"],
            "outputs": ["local searchable paper library"],
        },
        {
            "name": "Project task export",
            "command": "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv",
            "uses": ["actions.json", "taxonomy_actions.json", "review.json"],
            "outputs": ["docs/exports/actions-project.csv"],
        },
        {
            "name": "Taxonomy registry export",
            "command": "python3 scripts/export_taxonomy_registry.py docs --format project --severity high --severity medium --output docs/exports/taxonomy-registry-project.csv",
            "uses": ["registry.json", "papers.json"],
            "outputs": ["docs/exports/taxonomy-registry-project.csv"],
        },
    ]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "inbox_count": len(inbox_items),
        "page_count": len(pages),
        "data_file_count": len(data_files),
        "contract_count": len(contracts),
        "pages": pages,
        "data_resources": data_resources,
        "contracts": contracts,
        "integration_recipes": integration_recipes,
        "recommended_bootstrap_files": ["command.json", "catalog.json", "manifest.json", "papers.json", "search_index.json", "workflow.json", "status.json", "views.json", "batch.json", "collections.json", "coverage.json", "gaps.json"],
    }


def write_catalog_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_catalog_payload(report_dir, papers, inbox_items)
    (report_dir / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_catalog_placeholders(report_dir: Path) -> None:
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": 0,
        "inbox_count": 0,
        "page_count": 0,
        "data_file_count": 0,
        "contract_count": 0,
        "pages": [],
        "data_resources": [],
        "contracts": [],
        "integration_recipes": [],
        "recommended_bootstrap_files": ["command.json", "catalog.json", "manifest.json", "papers.json", "search_index.json", "workflow.json", "status.json", "views.json", "batch.json", "collections.json", "coverage.json", "gaps.json"],
    }
    (report_dir / "catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (report_dir / "catalog.html").write_text(
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>数据目录</title></head>"
        "<body><h1>数据目录</h1><p>Catalog placeholder; rebuilt by scripts/build_wiki.py.</p></body></html>",
        encoding="utf-8",
    )


def repo_file_status(path: str, label: str, href: str | None = None) -> dict[str, Any]:
    return {
        "path": path,
        "label": label,
        "href": href or path,
        "exists": (ROOT / path).exists(),
    }


def build_onboarding_payload(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    readiness_checks = [
        repo_file_status("README.md", "Project overview", "../README.md"),
        repo_file_status("CONTRIBUTING.md", "Contribution guide", "../CONTRIBUTING.md"),
        repo_file_status("LICENSE", "Open-source license", "../LICENSE"),
        repo_file_status(".github/workflows/wiki-quality.yml", "CI quality gate", "../.github/workflows/wiki-quality.yml"),
        repo_file_status(".github/PULL_REQUEST_TEMPLATE.md", "Pull request template", "../.github/PULL_REQUEST_TEMPLATE.md"),
        repo_file_status(".github/ISSUE_TEMPLATE/paper-intake.yml", "Paper intake issue form", "../.github/ISSUE_TEMPLATE/paper-intake.yml"),
        repo_file_status(".github/ISSUE_TEMPLATE/taxonomy-governance.yml", "Taxonomy governance issue form", "../.github/ISSUE_TEMPLATE/taxonomy-governance.yml"),
        repo_file_status(".github/ISSUE_TEMPLATE/report-quality.yml", "Report quality issue form", "../.github/ISSUE_TEMPLATE/report-quality.yml"),
        repo_file_status("docs/guides/report.template.md", "Report template", "guides/report.template.md"),
        repo_file_status("docs/guides/metadata.schema.json", "Metadata schema", "guides/metadata.schema.json"),
        repo_file_status("docs/guides/inbox.schema.json", "Inbox schema", "guides/inbox.schema.json"),
        repo_file_status("docs/guides/taxonomy.schema.json", "Taxonomy schema", "guides/taxonomy.schema.json"),
        repo_file_status("docs/guides/facets.schema.json", "Facets schema", "guides/facets.schema.json"),
        repo_file_status("docs/guides/batch.schema.json", "Batch schema", "guides/batch.schema.json"),
        repo_file_status("docs/guides/actions.schema.json", "Actions schema", "guides/actions.schema.json"),
        repo_file_status("docs/guides/catalog.schema.json", "Catalog schema", "guides/catalog.schema.json"),
        repo_file_status("docs/guides/workflow.schema.json", "Workflow schema", "guides/workflow.schema.json"),
        repo_file_status("docs/guides/status.schema.json", "Status schema", "guides/status.schema.json"),
        repo_file_status("docs/guides/views.schema.json", "Views schema", "guides/views.schema.json"),
        repo_file_status("scripts/check_quality.py", "Local quality gate", "../scripts/check_quality.py"),
    ]
    passed = sum(1 for item in readiness_checks if item["exists"])
    readiness_score = percent(passed, len(readiness_checks))
    quickstart_steps = [
        {
            "order": 1,
            "title": "Open the contributor console",
            "href": "onboarding.html",
            "command": "",
            "why": "Start from this page to choose the right contribution path.",
        },
        {
            "order": 2,
            "title": "Batch candidate links before triage",
            "href": "intake.html",
            "command": "",
            "why": "Paste many links, dedupe them against the library and inbox, then export a candidate CSV.",
        },
        {
            "order": 3,
            "title": "Route a new paper before writing metadata",
            "href": "routing.html",
            "command": "",
            "why": "Use title and abstract to pick an initial research line and taxonomy labels.",
        },
        {
            "order": 4,
            "title": "Edit or review papers in the dense library",
            "href": "library.html",
            "command": "",
            "why": "Filter, select, export metadata patches, and manage status workflows.",
        },
        {
            "order": 5,
            "title": "Run the local quality gate",
            "href": "quality.html",
            "command": "python3 scripts/check_quality.py docs",
            "why": "Use the same checks as CI before opening a PR.",
        },
    ]
    contribution_paths = [
        {
            "id": "paper-intake",
            "title": "Add or triage candidate papers",
            "entry": "intake.html",
            "issue_template": ".github/ISSUE_TEMPLATE/paper-intake.yml",
            "contract": "guides/inbox.schema.json",
            "recommended_pages": ["intake.html", "routing.html", "inbox.html", "library.html"],
            "commands": [
                "python3 scripts/apply_inbox_items.py docs --input <candidate_csv>",
                "python3 scripts/apply_inbox_items.py docs --input <candidate_csv> --write",
                "python3 scripts/build_wiki.py docs",
            ],
        },
        {
            "id": "report-quality",
            "title": "Fix report metadata or rendering issues",
            "entry": "quality.html",
            "issue_template": ".github/ISSUE_TEMPLATE/report-quality.yml",
            "contract": "guides/metadata.schema.json",
            "recommended_pages": ["quality.html", "review.html", "freshness.html"],
            "commands": [
                "python3 scripts/validate_wiki.py docs --strict-taxonomy",
                "python3 scripts/check_quality.py docs",
            ],
        },
        {
            "id": "taxonomy-governance",
            "title": "Govern labels, status workflows, and research lines",
            "entry": "taxonomy.html",
            "issue_template": ".github/ISSUE_TEMPLATE/taxonomy-governance.yml",
            "contract": "guides/taxonomy.schema.json",
            "recommended_pages": ["registry.html", "facets.html", "balance.html", "coverage.html", "ownership.html"],
            "commands": [
                "python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md",
                "python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md",
                "python3 scripts/apply_taxonomy_aliases.py docs --write",
                "python3 scripts/check_quality.py docs",
            ],
        },
        {
            "id": "release-readiness",
            "title": "Prepare a publishable wiki snapshot",
            "entry": "release.html",
            "issue_template": ".github/PULL_REQUEST_TEMPLATE.md",
            "contract": "manifest.json",
            "recommended_pages": ["release.html", "snapshot.html", "catalog.html"],
            "commands": [
                "python3 scripts/build_wiki.py docs",
                "python3 scripts/build_wiki.py docs --check",
                "python3 scripts/check_quality.py docs",
            ],
        },
    ]
    command_groups = [
        {"label": "Build wiki", "command": "python3 scripts/build_wiki.py docs", "href": "release.html"},
        {"label": "Check generated artifacts", "command": "python3 scripts/build_wiki.py docs --check", "href": "release.html"},
        {"label": "Strict validation", "command": "python3 scripts/validate_wiki.py docs --strict-taxonomy", "href": "quality.html"},
        {"label": "Quality gate", "command": "python3 scripts/check_quality.py docs", "href": "quality.html"},
        {"label": "Export unified actions", "command": "python3 scripts/export_actions.py docs --output docs/exports/actions.md", "href": "actions.html"},
        {"label": "Export label registry", "command": "python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md", "href": "registry.html"},
    ]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "inbox_count": len(inbox_items),
        "readiness_score": readiness_score,
        "readiness_passed": passed,
        "readiness_total": len(readiness_checks),
        "readiness_checks": readiness_checks,
        "quickstart_steps": quickstart_steps,
        "contribution_paths": contribution_paths,
        "command_groups": command_groups,
        "contracts": contract_files_manifest(),
        "bootstrap_files": ["command.json", "onboarding.json", "catalog.json", "manifest.json", "papers.json", "workflow.json", "status.json", "views.json", "batch.json", "collections.json", "coverage.json", "gaps.json", "intake.json", "routing.json", "quality.json"],
        "core_pages": [
            item
            for item in wiki_pages_manifest()
            if item["href"] in {"onboarding.html", "intake.html", "routing.html", "library.html", "quality.html", "taxonomy.html", "release.html", "catalog.html"}
        ],
        "links": {
            "catalog": "catalog.html",
            "manifest": "manifest.json",
            "release": "release.html",
            "quality": "quality.html",
            "intake": "intake.html",
            "routing": "routing.html",
        },
    }


def write_onboarding_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_onboarding_payload(report_dir, papers, inbox_items)
    (report_dir / "onboarding.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def wiki_pages_manifest() -> list[dict[str, str]]:
    return [
        {"title": "首页", "href": "index.html", "kind": "view", "description": "卡片检索、筛选、研究线概览"},
        {"title": "命令中心", "href": "command.html", "kind": "ops", "description": "按使用场景组织入口、队列、数据和命令"},
        {"title": "论文库表格", "href": "library.html", "kind": "view", "description": "密集筛选、列管理、批量更新"},
        {"title": "管理控制台", "href": "dashboard.html", "kind": "ops", "description": "覆盖率、队列和运营指标"},
        {"title": "发布摘要", "href": "release.html", "kind": "ops", "description": "页面入口、数据文件、质量状态"},
        {"title": "治理快照", "href": "snapshot.html", "kind": "ops", "description": "当前发布基线、队列和治理策略快照"},
        {"title": "行动中心", "href": "actions.html", "kind": "ops", "description": "统一运营队列和可分派任务"},
        {"title": "集合视图", "href": "collections.html", "kind": "view", "description": "共享视图、智能集合、研究线入口"},
        {"title": "分类均衡", "href": "balance.html", "kind": "ops", "description": "分类维度健康度、长尾和过载复盘"},
        {"title": "覆盖地图", "href": "coverage.html", "kind": "ops", "description": "研究线 x 分类字段覆盖缺口"},
        {"title": "分类工作台", "href": "facets.html", "kind": "ops", "description": "标签规模、长尾和过载分类"},
        {"title": "关联网络", "href": "related.html", "kind": "analysis", "description": "标签共现、相似论文、孤岛论文"},
        {"title": "研究缺口", "href": "gaps.html", "kind": "ops", "description": "下一步行动和研究线缺口"},
        {"title": "状态看板", "href": "board.html", "kind": "workflow", "description": "拖拽式状态流和 CSV patch"},
        {"title": "工作流中心", "href": "workflow.html", "kind": "workflow", "description": "状态体系对比、分布和漂移审计"},
        {"title": "状态选择器", "href": "status.html", "kind": "workflow", "description": "动态选择状态体系、阶段和值并生成可分享视图"},
        {"title": "视图目录", "href": "views.html", "kind": "workflow", "description": "共享视图、系统队列和状态/研究线视图目录"},
        {"title": "批次规划", "href": "batch.html", "kind": "ops", "description": "按分类、状态和复习缺口切分可执行论文批次"},
        {"title": "分类透视表", "href": "pivot.html", "kind": "analysis", "description": "任意两个分类维度交叉分析论文分布"},
        {"title": "论文对比", "href": "compare.html", "kind": "analysis", "description": "并排比较候选论文的分类、状态和质量信号"},
        {"title": "分类图谱", "href": "taxonomy_map.html", "kind": "analysis", "description": "分类节点、共现边和研究线簇"},
        {"title": "研究簇", "href": "clusters.html", "kind": "analysis", "description": "研究线簇、拆分候选和代表论文"},
        {"title": "研究路线图", "href": "roadmap.html", "kind": "planning", "description": "按研究线组织阶段、里程碑和下一步计划"},
        {"title": "规模就绪", "href": "scale.html", "kind": "ops", "description": "大规模论文库容量、风险和扩展建议"},
        {"title": "Owner 工作台", "href": "ownership.html", "kind": "ops", "description": "研究线 owner、工作量和治理队列"},
        {"title": "分类路由器", "href": "routing.html", "kind": "workflow", "description": "新论文研究线和标签推荐"},
        {"title": "开源上手", "href": "onboarding.html", "kind": "ops", "description": "贡献路径、质量门和数据契约"},
        {"title": "数据目录", "href": "catalog.html", "kind": "ops", "description": "机器数据、页面和契约的接入目录"},
        {"title": "批量导入", "href": "intake.html", "kind": "workflow", "description": "批量粘贴论文链接、去重并导出 inbox CSV"},
        {"title": "待处理池", "href": "inbox.html", "kind": "workflow", "description": "候选论文队列和去重提示"},
        {"title": "去重工作台", "href": "dedupe.html", "kind": "ops", "description": "库内报告、候选论文和导入队列重复项治理"},
        {"title": "标签注册表", "href": "registry.html", "kind": "ops", "description": "分类标签字典、alias 和跨字段治理"},
        {"title": "复习计划", "href": "review.html", "kind": "workflow", "description": "待复习、需建计划、建议日期"},
        {"title": "时效治理", "href": "freshness.html", "kind": "ops", "description": "报告新鲜度、过期分析和研究线维护"},
        {"title": "质量治理", "href": "quality.html", "kind": "ops", "description": "弱元数据、别名建议、taxonomy drift"},
        {"title": "分类治理", "href": "taxonomy.html", "kind": "ops", "description": "分类矩阵、状态工作流、治理队列"},
        {"title": "时间轴", "href": "timeline.html", "kind": "analysis", "description": "按年份和研究线浏览论文演进"},
        {"title": "研究矩阵", "href": "matrix.html", "kind": "analysis", "description": "research line x year 覆盖"},
        {"title": "研究线", "href": "lines/index.html", "kind": "view", "description": "按研究脉络组织论文"},
        {"title": "分类总览", "href": "tags.html", "kind": "view", "description": "按标签聚合论文"},
    ]


def data_files_manifest() -> list[dict[str, str]]:
    return [
        {"href": "papers.json", "description": "论文索引、taxonomy 聚合、前端 controls"},
        {"href": "search_index.json", "description": "正文全文检索索引"},
        {"href": "stats.json", "description": "运营统计、覆盖率和队列规模"},
        {"href": "quality.json", "description": "质量问题、taxonomy load、taxonomy drift、标签别名建议"},
        {"href": "review.json", "description": "复习计划和建议 next_review"},
        {"href": "freshness.json", "description": "报告新鲜度、过期分析和研究线维护队列"},
        {"href": "taxonomy_actions.json", "description": "分类长尾、过载和空候选治理任务"},
        {"href": "actions.json", "description": "统一行动队列，汇总质量、复习、分类和 inbox 任务"},
        {"href": "command.json", "description": "场景化命令中心，组织页面入口、队列、数据和推荐命令"},
        {"href": "workflow.json", "description": "状态工作流配置、分布和漂移审计"},
        {"href": "status.json", "description": "运行时状态选择器、状态字段选项和论文状态快照"},
        {"href": "views.json", "description": "共享视图、系统队列、研究线和状态工作流视图目录"},
        {"href": "batch.json", "description": "按分类、状态和治理缺口生成的可执行论文批次"},
        {"href": "collections.json", "description": "共享视图、智能集合和研究线集合的机器可读入口"},
        {"href": "coverage.json", "description": "研究线分类覆盖、字段缺口、缺失 slug 和 owner 信号"},
        {"href": "gaps.json", "description": "研究线缺口、下一步行动和运营队列"},
        {"href": "pivot.json", "description": "分类透视表维度、论文投影和交叉分布"},
        {"href": "compare.json", "description": "论文对比视图数据和推荐对比集合"},
        {"href": "taxonomy_map.json", "description": "分类节点、共现边、研究线簇和图谱治理建议"},
        {"href": "clusters.json", "description": "研究线簇、拆分候选和代表论文"},
        {"href": "roadmap.json", "description": "研究线路线图、阶段覆盖、里程碑和下一步计划"},
        {"href": "scale.json", "description": "规模就绪评分、容量投影和大库治理风险"},
        {"href": "ownership.json", "description": "研究线 owner、工作量和治理队列"},
        {"href": "routing.json", "description": "新论文分类路由画像和推荐权重"},
        {"href": "onboarding.json", "description": "开源贡献路径、质量门和数据契约清单"},
        {"href": "catalog.json", "description": "机器数据、页面入口和契约字段目录"},
        {"href": "snapshot.json", "description": "当前知识库治理快照和发布基线"},
        {"href": "intake.json", "description": "批量导入去重索引、默认字段和 inbox CSV 契约"},
        {"href": "inbox.json", "description": "候选论文队列和重复项"},
        {"href": "dedupe.json", "description": "重复报告、候选重复项和去重建议"},
        {"href": "registry.json", "description": "分类标签注册表、alias、字段复用和治理信号"},
        {"href": "facets.json", "description": "分类字段目录、候选值规模和治理动作"},
        {"href": "manifest.json", "description": "发布摘要和页面入口清单"},
    ]


def contract_files_manifest() -> list[dict[str, str]]:
    return [
        {"href": "guides/report.template.md", "description": "中文论文阅读报告模板"},
        {"href": "guides/metadata.schema.json", "description": "报告 frontmatter 字段契约"},
        {"href": "guides/inbox.schema.json", "description": "候选论文 inbox.csv 字段契约"},
        {"href": "guides/taxonomy.schema.json", "description": "taxonomy.json 配置字段契约"},
        {"href": "guides/facets.schema.json", "description": "facets.json 分类字段目录契约"},
        {"href": "guides/batch.schema.json", "description": "batch.json 批量规划数据契约"},
        {"href": "guides/actions.schema.json", "description": "actions.json 统一行动队列契约"},
        {"href": "guides/catalog.schema.json", "description": "catalog.json 集成目录契约"},
        {"href": "guides/workflow.schema.json", "description": "workflow.json 状态工作流审计契约"},
        {"href": "guides/status.schema.json", "description": "status.json 状态选择器和写回命令契约"},
        {"href": "guides/views.schema.json", "description": "views.json 视图目录和批量队列契约"},
        {"href": "guides/taxonomy.json", "description": "分类别名、状态工作流和共享视图配置"},
    ]


def is_generated_artifact_href(href: str) -> bool:
    return href in GENERATED_FIXED_PATHS or (href.startswith("lines/") and href.endswith(".html"))


def canonical_artifact_bytes(report_dir: Path, href: str, path: Path, data: bytes) -> bytes:
    if not is_generated_artifact_href(href):
        return data
    return normalize_generated_content(path, data).encode("utf-8")


def artifact_record(report_dir: Path, href: str, kind: str, description: str, pending: bool = False) -> dict[str, Any]:
    path = report_dir / href
    record: dict[str, Any] = {
        "href": href,
        "kind": kind,
        "description": description,
        "exists": True if pending else path.exists(),
    }
    if pending:
        record["status"] = "generated_after_inventory"
        return record
    if not path.exists() or not path.is_file():
        record["status"] = "missing"
        return record
    data = path.read_bytes()
    hash_source = canonical_artifact_bytes(report_dir, href, path, data)
    record.update(
        {
            "status": "ok",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(hash_source).hexdigest(),
            "hash_mode": "normalized" if hash_source != data else "raw",
        }
    )
    return record


def artifact_inventory_manifest(report_dir: Path, pages: list[dict[str, str]], data_files: list[dict[str, str]], finalized: bool = False) -> list[dict[str, Any]]:
    pending = {"manifest.json"}
    if not finalized:
        pending.add("release.html")
    artifacts: list[dict[str, Any]] = []
    for page in pages:
        href = page["href"]
        artifacts.append(artifact_record(report_dir, href, "page", page["description"], href in pending))
    for file in data_files:
        href = file["href"]
        artifacts.append(artifact_record(report_dir, href, "data", file["description"], href in pending))
    for file in contract_files_manifest():
        href = file["href"]
        artifacts.append(artifact_record(report_dir, href, "contract", file["description"], href in pending))
    return artifacts


def command_recipes_manifest() -> list[dict[str, Any]]:
    return [
        {
            "id": "build_wiki",
            "kind": "build",
            "label": "Build wiki",
            "command": "python3 scripts/build_wiki.py docs",
            "output": "docs/",
            "mutates": True,
        },
        {
            "id": "quality_gate",
            "kind": "check",
            "label": "Quality gate",
            "command": "python3 scripts/check_quality.py docs",
            "output": "",
            "mutates": False,
        },
        {
            "id": "strict_validate",
            "kind": "check",
            "label": "Strict validation",
            "command": "python3 scripts/validate_wiki.py docs --strict-taxonomy",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_metadata_dry_run",
            "kind": "check",
            "label": "Preview edited metadata CSV",
            "command": "python3 scripts/apply_library_metadata.py docs --input <csv>",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_metadata_audit",
            "kind": "check",
            "label": "Audit edited metadata CSV",
            "command": "python3 scripts/apply_library_metadata.py docs --input <csv> --audit-output docs/exports/metadata-audit.json",
            "output": "docs/exports/metadata-audit.json",
            "mutates": False,
        },
        {
            "id": "apply_inbox_dry_run",
            "kind": "check",
            "label": "Preview candidate inbox CSV",
            "command": "python3 scripts/apply_inbox_items.py docs --input <candidate_csv>",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_inbox",
            "kind": "writeback",
            "label": "Apply candidate inbox CSV",
            "command": "python3 scripts/apply_inbox_items.py docs --input <candidate_csv> --write",
            "output": "docs/inbox.csv",
            "mutates": True,
        },
        {
            "id": "apply_metadata",
            "kind": "writeback",
            "label": "Apply edited metadata CSV",
            "command": "python3 scripts/apply_library_metadata.py docs --input <csv> --write",
            "output": "docs/*.md",
            "mutates": True,
        },
        {
            "id": "apply_aliases",
            "kind": "writeback",
            "label": "Apply taxonomy aliases",
            "command": "python3 scripts/apply_taxonomy_aliases.py docs --write",
            "output": "docs/guides/taxonomy.json",
            "mutates": True,
        },
        {
            "id": "apply_status_workflow_dry_run",
            "kind": "check",
            "label": "Preview status workflow JSON",
            "command": "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json>",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_status_workflow",
            "kind": "writeback",
            "label": "Apply status workflow JSON",
            "command": "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write",
            "output": "docs/guides/taxonomy.json",
            "mutates": True,
        },
        {
            "id": "apply_governance_policy_dry_run",
            "kind": "check",
            "label": "Preview governance policy JSON",
            "command": "python3 scripts/apply_governance_policy.py docs --input <taxonomy_governance_policy.json>",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_governance_policy",
            "kind": "writeback",
            "label": "Apply governance policy JSON",
            "command": "python3 scripts/apply_governance_policy.py docs --input <taxonomy_governance_policy.json> --write",
            "output": "docs/guides/taxonomy.json",
            "mutates": True,
        },
        {
            "id": "apply_shared_views_dry_run",
            "kind": "check",
            "label": "Preview shared views JSON",
            "command": "python3 scripts/apply_shared_views.py docs --input <shared_views.json>",
            "output": "",
            "mutates": False,
        },
        {
            "id": "apply_shared_views",
            "kind": "writeback",
            "label": "Apply shared views JSON",
            "command": "python3 scripts/apply_shared_views.py docs --input <shared_views.json> --write",
            "output": "docs/guides/taxonomy.json",
            "mutates": True,
        },
        {
            "id": "taxonomy_actions_markdown",
            "kind": "export",
            "label": "Export taxonomy actions checklist",
            "command": "python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md",
            "output": "docs/exports/taxonomy-actions.md",
            "mutates": False,
        },
        {
            "id": "taxonomy_actions_project",
            "kind": "export",
            "label": "Export taxonomy action project tasks",
            "command": "python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv",
            "output": "docs/exports/taxonomy-project.csv",
            "mutates": False,
        },
        {
            "id": "taxonomy_actions_patch",
            "kind": "export",
            "label": "Export taxonomy action patch template",
            "command": "python3 scripts/export_taxonomy_actions.py docs --format patch --action merge_candidate --output docs/exports/taxonomy-action-patch.csv",
            "output": "docs/exports/taxonomy-action-patch.csv",
            "mutates": False,
        },
        {
            "id": "taxonomy_registry_markdown",
            "kind": "export",
            "label": "Export taxonomy registry checklist",
            "command": "python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md",
            "output": "docs/exports/taxonomy-registry.md",
            "mutates": False,
        },
        {
            "id": "taxonomy_registry_project",
            "kind": "export",
            "label": "Export taxonomy registry project tasks",
            "command": "python3 scripts/export_taxonomy_registry.py docs --format project --severity high --severity medium --output docs/exports/taxonomy-registry-project.csv",
            "output": "docs/exports/taxonomy-registry-project.csv",
            "mutates": False,
        },
        {
            "id": "actions_markdown",
            "kind": "export",
            "label": "Export unified action checklist",
            "command": "python3 scripts/export_actions.py docs --output docs/exports/actions.md",
            "output": "docs/exports/actions.md",
            "mutates": False,
        },
        {
            "id": "actions_project",
            "kind": "export",
            "label": "Export unified action project tasks",
            "command": "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv",
            "output": "docs/exports/actions-project.csv",
            "mutates": False,
        },
        {
            "id": "batches_markdown",
            "kind": "export",
            "label": "Export batch checklist",
            "command": "python3 scripts/export_batches.py docs --output docs/exports/batches.md",
            "output": "docs/exports/batches.md",
            "mutates": False,
        },
        {
            "id": "batches_project",
            "kind": "export",
            "label": "Export batch project tasks",
            "command": "python3 scripts/export_batches.py docs --format project --severity high --output docs/exports/batches-project.csv",
            "output": "docs/exports/batches-project.csv",
            "mutates": False,
        },
        {
            "id": "batches_review_patch",
            "kind": "export",
            "label": "Export batch review-stage patch",
            "command": "python3 scripts/export_batches.py docs --format patch --gap review --field review_stage --set-value due --output docs/exports/batches-review-patch.csv",
            "output": "docs/exports/batches-review-patch.csv",
            "mutates": False,
        },
        {
            "id": "collections_markdown",
            "kind": "export",
            "label": "Export collection checklist",
            "command": "python3 scripts/export_collections.py docs --output docs/exports/collections.md",
            "output": "docs/exports/collections.md",
            "mutates": False,
        },
        {
            "id": "coverage_markdown",
            "kind": "export",
            "label": "Export coverage gap checklist",
            "command": "python3 scripts/export_coverage.py docs --output docs/exports/coverage.md",
            "output": "docs/exports/coverage.md",
            "mutates": False,
        },
        {
            "id": "coverage_project",
            "kind": "export",
            "label": "Export coverage project tasks",
            "command": "python3 scripts/export_coverage.py docs --format project --risk high --risk medium --output docs/exports/coverage-project.csv",
            "output": "docs/exports/coverage-project.csv",
            "mutates": False,
        },
        {
            "id": "coverage_topic_patch",
            "kind": "export",
            "label": "Export coverage topic patch",
            "command": "python3 scripts/export_coverage.py docs --format patch --field topics --set-value <topic> --output docs/exports/coverage-topic-patch.csv",
            "output": "docs/exports/coverage-topic-patch.csv",
            "mutates": False,
        },
        {
            "id": "gaps_markdown",
            "kind": "export",
            "label": "Export research gap checklist",
            "command": "python3 scripts/export_gaps.py docs --output docs/exports/gaps.md",
            "output": "docs/exports/gaps.md",
            "mutates": False,
        },
        {
            "id": "gaps_project",
            "kind": "export",
            "label": "Export research gap project tasks",
            "command": "python3 scripts/export_gaps.py docs --format project --min-priority 20 --output docs/exports/gaps-project.csv",
            "output": "docs/exports/gaps-project.csv",
            "mutates": False,
        },
        {
            "id": "views_markdown",
            "kind": "export",
            "label": "Export view directory checklist",
            "command": "python3 scripts/export_views.py docs --output docs/exports/views.md",
            "output": "docs/exports/views.md",
            "mutates": False,
        },
        {
            "id": "views_sidebar",
            "kind": "export",
            "label": "Export view sidebar JSON",
            "command": "python3 scripts/export_views.py docs --format sidebar --min-count 1 --output docs/exports/views-sidebar.json",
            "output": "docs/exports/views-sidebar.json",
            "mutates": False,
        },
        {
            "id": "views_status_patch",
            "kind": "export",
            "label": "Export view status patch",
            "command": "python3 scripts/export_views.py docs --format patch --view <view_id_or_name> --field status --set-value reading --output docs/exports/views-status-patch.csv",
            "output": "docs/exports/views-status-patch.csv",
            "mutates": False,
        },
        {
            "id": "collections_project",
            "kind": "export",
            "label": "Export collection project tasks",
            "command": "python3 scripts/export_collections.py docs --format project --output docs/exports/collections-project.csv",
            "output": "docs/exports/collections-project.csv",
            "mutates": False,
        },
        {
            "id": "ownership_markdown",
            "kind": "export",
            "label": "Export ownership workload checklist",
            "command": "python3 scripts/export_ownership.py docs --output docs/exports/ownership.md",
            "output": "docs/exports/ownership.md",
            "mutates": False,
        },
        {
            "id": "ownership_project",
            "kind": "export",
            "label": "Export ownership project tasks",
            "command": "python3 scripts/export_ownership.py docs --format project --only-open-queues --output docs/exports/ownership-project.csv",
            "output": "docs/exports/ownership-project.csv",
            "mutates": False,
        },
        {
            "id": "roadmap_markdown",
            "kind": "export",
            "label": "Export roadmap checklist",
            "command": "python3 scripts/export_roadmap.py docs --output docs/exports/roadmap.md",
            "output": "docs/exports/roadmap.md",
            "mutates": False,
        },
        {
            "id": "roadmap_project",
            "kind": "export",
            "label": "Export roadmap project tasks",
            "command": "python3 scripts/export_roadmap.py docs --format project --output docs/exports/roadmap-project.csv",
            "output": "docs/exports/roadmap-project.csv",
            "mutates": False,
        },
        {
            "id": "taxonomy_balance_project",
            "kind": "export",
            "label": "Export taxonomy balance project tasks",
            "command": "python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --output docs/exports/taxonomy-balance-project.csv",
            "output": "docs/exports/taxonomy-balance-project.csv",
            "mutates": False,
        },
        {
            "id": "taxonomy_load_csv",
            "kind": "export",
            "label": "Export taxonomy load audit CSV",
            "command": "python3 scripts/export_taxonomy_load.py docs --format csv --output docs/exports/taxonomy-load.csv",
            "output": "docs/exports/taxonomy-load.csv",
            "mutates": False,
        },
        {
            "id": "taxonomy_load_patch",
            "kind": "export",
            "label": "Export taxonomy load patch CSV",
            "command": "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv",
            "output": "docs/exports/taxonomy-load-patch.csv",
            "mutates": False,
        },
    ]


def governance_playbooks_manifest() -> list[dict[str, Any]]:
    return [
        {
            "id": "taxonomy_merge_batch",
            "label": "Taxonomy merge batch",
            "description": "Review merge candidates, prepare a metadata patch, dry-run it, then refresh quality gates.",
            "steps": [
                "taxonomy_actions_markdown",
                "taxonomy_actions_patch",
                "apply_metadata_audit",
                "apply_metadata_dry_run",
                "quality_gate",
            ],
        },
        {
            "id": "taxonomy_balance_review",
            "label": "Taxonomy balance review",
            "description": "Turn overloaded or sparse taxonomy buckets into project tasks before changing labels.",
            "steps": [
                "taxonomy_registry_project",
                "taxonomy_balance_project",
                "taxonomy_actions_project",
                "quality_gate",
            ],
        },
        {
            "id": "weekly_action_review",
            "label": "Weekly action review",
            "description": "Export the unified queue, assign dynamic task statuses, and run the local quality gate.",
            "steps": [
                "actions_markdown",
                "actions_project",
                "quality_gate",
            ],
        },
        {
            "id": "paper_intake_batch",
            "label": "Paper intake batch",
            "description": "Preview a candidate CSV, merge it into inbox.csv, rebuild, then validate the incoming queue.",
            "steps": [
                "apply_inbox_dry_run",
                "apply_inbox",
                "build_wiki",
                "strict_validate",
            ],
        },
        {
            "id": "status_workflow_rollout",
            "label": "Status workflow rollout",
            "description": "Preview a downloaded status workflow, write it to taxonomy.json, rebuild, then validate.",
            "steps": [
                "apply_status_workflow_dry_run",
                "apply_status_workflow",
                "build_wiki",
                "strict_validate",
            ],
        },
        {
            "id": "shared_view_rollout",
            "label": "Shared view rollout",
            "description": "Promote browser-saved queues into repository shared_views and validate the refreshed wiki.",
            "steps": [
                "apply_shared_views_dry_run",
                "apply_shared_views",
                "build_wiki",
                "strict_validate",
            ],
        },
        {
            "id": "release_readiness",
            "label": "Release readiness",
            "description": "Rebuild the wiki, validate strict taxonomy, then run the full quality gate before publishing.",
            "steps": [
                "build_wiki",
                "strict_validate",
                "quality_gate",
            ],
        },
    ]


def build_manifest(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]], finalized: bool = False) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    stats = build_stats_report(papers)
    pages = wiki_pages_manifest()
    data_files = data_files_manifest()
    contract_files = contract_files_manifest()
    artifacts = artifact_inventory_manifest(report_dir, pages, data_files, finalized=finalized)
    command_recipes = command_recipes_manifest()
    governance_playbooks = governance_playbooks_manifest()
    quality_queues = {name: len(slugs) for name, slugs in quality["queues"].items()}
    review_queues = {name: len(slugs) for name, slugs in review["queues"].items()}
    missing_artifacts = [item for item in artifacts if item["status"] == "missing"]
    publish_checks = {
        "metadata_complete": quality_queues.get("missing_required_metadata", 0) == 0,
        "taxonomy_clean": quality_queues.get("taxonomy_drift", 0) == 0 and not quality["label_alias_suggestions"],
        "no_duplicate_reports": quality_queues.get("duplicate_reports", 0) == 0,
        "has_review_plan": review_queues.get("needs_plan", 0) == 0,
        "has_generated_pages": all((report_dir / page["href"]).exists() for page in pages if page["href"] != "release.html"),
        "artifacts_present": not missing_artifacts,
    }
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "name": "AutoPaperReader Wiki",
        "count": len(papers),
        "publish_ready": all(publish_checks.values()),
        "publish_checks": publish_checks,
        "quality_score": quality["quality_score"],
        "coverage": quality["coverage"],
        "queue_sizes": {
            "quality": quality_queues,
            "review": review_queues,
            "inbox": {
                "count": len(inbox_items),
                "duplicates": sum(1 for item in inbox_items if item.get("duplicate")),
            },
        },
        "taxonomy": stats["taxonomy"],
        "research_lines": stats["research_lines"],
        "controls": control_options(),
        "pages": pages,
        "data_files": data_files,
        "contract_files": contract_files,
        "artifact_inventory": artifacts,
        "command_recipes": command_recipes,
        "governance_playbooks": governance_playbooks,
        "commands": [recipe["command"] for recipe in command_recipes],
    }


def write_manifest_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_manifest(report_dir, papers, inbox_items, finalized=True)
    (report_dir / "manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_snapshot_payload(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    manifest = build_manifest(report_dir, papers, inbox_items, finalized=False)
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    freshness = build_freshness_report(papers)
    actions = build_action_center(papers, inbox_items)
    stats = build_stats_report(papers)
    snapshot_hrefs = {"manifest.json", "release.html", "snapshot.html", "snapshot.json"}
    artifacts = [
        artifact
        for artifact in manifest.get("artifact_inventory", [])
        if str(artifact.get("href") or "") not in snapshot_hrefs
    ]
    missing_artifacts = [artifact for artifact in artifacts if artifact.get("status") == "missing"]
    action_groups = actions.get("summary", {}).get("groups", {})
    risk_queue_sizes = {
        "missing_required_metadata": len(quality["queues"].get("missing_required_metadata", [])),
        "taxonomy_drift": len(quality["queues"].get("taxonomy_drift", [])),
        "duplicate_reports": len(quality["queues"].get("duplicate_reports", [])),
        "needs_review_plan": len(review["queues"].get("needs_plan", [])),
        "due_review": len(review["queues"].get("due", [])),
        "freshness_due": len(freshness["queues"].get("due", [])),
        "freshness_stale": len(freshness["queues"].get("stale", [])),
        "inbox_duplicates": sum(1 for item in inbox_items if item.get("duplicate")),
    }
    snapshot_checks = dict(manifest["publish_checks"])
    snapshot_checks["has_generated_pages"] = all(
        (report_dir / str(page.get("href") or "")).exists()
        for page in manifest.get("pages", [])
        if str(page.get("href") or "") not in snapshot_hrefs
    )
    snapshot_checks["artifacts_present"] = not missing_artifacts
    snapshot_publish_ready = all(snapshot_checks.values())
    release_state = {
        "count": manifest["count"],
        "publish_ready": snapshot_publish_ready,
        "publish_checks": snapshot_checks,
        "quality_score": manifest["quality_score"],
        "coverage": manifest["coverage"],
        "queue_sizes": manifest["queue_sizes"],
        "risk_queue_sizes": risk_queue_sizes,
        "governance_policy": manifest["controls"].get("governance_policy", {}),
    }
    snapshot_id = hashlib.sha256(json.dumps(release_state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "snapshot_id": snapshot_id,
        "name": manifest["name"],
        "count": manifest["count"],
        "publish_ready": snapshot_publish_ready,
        "publish_checks": snapshot_checks,
        "quality_score": manifest["quality_score"],
        "coverage": manifest["coverage"],
        "queue_sizes": manifest["queue_sizes"],
        "risk_queue_sizes": risk_queue_sizes,
        "action_groups": [
            {"group": group, "count": count}
            for group, count in sorted(action_groups.items(), key=lambda item: (-int(item[1]), item[0]))
        ],
        "governance_policy": manifest["controls"].get("governance_policy", {}),
        "active_status_workflow": manifest["controls"].get("active_status_workflow", ""),
        "research_lines": sorted(
            stats.get("research_lines", []),
            key=lambda item: (-(int(item.get("count") or 0)), str(item.get("name") or "").lower()),
        ),
        "artifact_summary": {
            "count": len(artifacts),
            "missing": [artifact.get("href") for artifact in missing_artifacts],
            "hashes": [
                {
                    "href": artifact.get("href"),
                    "kind": artifact.get("kind"),
                    "sha256": artifact.get("sha256"),
                    "status": artifact.get("status"),
                }
                for artifact in artifacts
                if artifact.get("sha256")
            ],
        },
        "links": {
            "release": "release.html",
            "manifest": "manifest.json",
            "quality": "quality.json",
            "actions": "actions.json",
            "stats": "stats.json",
        },
    }


def write_snapshot_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_snapshot_payload(report_dir, papers, inbox_items)
    (report_dir / "snapshot.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def review_interval_days(paper: dict[str, Any]) -> int:
    importance = int(paper.get("importance") or 0)
    confidence = int(paper.get("confidence") or 0)
    reproducibility = int(paper.get("reproducibility") or 0)
    if importance >= 5:
        days = 14
    elif importance >= 4:
        days = 30
    elif importance >= 3:
        days = 60
    else:
        days = 90
    if confidence and confidence <= 3:
        days = max(7, days // 2)
    if reproducibility and reproducibility <= 3:
        days = max(7, days - 7)
    return days


def review_base_date(paper: dict[str, Any]) -> dt.date:
    for field in ("last_reviewed", "updated_at", "created_at"):
        value = parse_date(paper.get(field))
        if value:
            return value
    return dt.date.today()


def review_item(paper: dict[str, Any], today: str) -> dict[str, Any]:
    interval = review_interval_days(paper)
    existing_next = str(paper.get("next_review") or "").strip()
    base = review_base_date(paper)
    suggested_next = (base + dt.timedelta(days=interval)).isoformat()
    effective_next = existing_next or suggested_next
    due = bool(effective_next and effective_next <= today)
    if existing_next:
        state = "due" if due else "scheduled"
    else:
        state = "needs_plan"
    priority = int(paper.get("importance") or 0) * 10
    if state == "needs_plan":
        priority += 8
    if due:
        priority += 12
    if int(paper.get("confidence") or 0) <= 3:
        priority += 3

    return {
        "slug": paper["slug"],
        "title": paper["title"],
        "title_zh": paper["title_zh"],
        "research_line": paper.get("research_line") or "Unassigned",
        "line_role": paper.get("line_role") or "",
        "importance": paper.get("importance"),
        "confidence": paper.get("confidence"),
        "reproducibility": paper.get("reproducibility"),
        "review_stage": paper.get("review_stage") or "",
        "last_reviewed": paper.get("last_reviewed") or "",
        "next_review": existing_next,
        "suggested_next_review": suggested_next,
        "interval_days": interval,
        "state": state,
        "priority": priority,
        "html_path": paper.get("html_path") or paper.get("md_path"),
    }


def build_review_plan(papers: list[dict[str, Any]]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    items = [review_item(paper, today) for paper in papers]
    items.sort(
        key=lambda item: (
            item["state"] != "due",
            item["state"] != "needs_plan",
            -int(item.get("priority") or 0),
            item.get("suggested_next_review") or item.get("next_review") or "",
            item["title"],
        )
    )
    queues = {
        "due": [item["slug"] for item in items if item["state"] == "due"],
        "needs_plan": [item["slug"] for item in items if item["state"] == "needs_plan"],
        "scheduled": [item["slug"] for item in items if item["state"] == "scheduled"],
        "high_priority": [item["slug"] for item in items if int(item.get("importance") or 0) >= 5],
    }
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "queues": queues,
        "items": items,
    }


def freshness_item(paper: dict[str, Any], today: dt.date) -> dict[str, Any]:
    next_review = parse_date(paper.get("next_review"))
    last_reviewed = parse_date(paper.get("last_reviewed"))
    updated_at = parse_date(paper.get("updated_at"))
    reference_date = last_reviewed or updated_at
    age_days = (today - reference_date).days if reference_date else None
    year = int(paper.get("year") or 0)
    year_age = today.year - year if year else None
    has_plan = bool(next_review)
    due = bool(next_review and next_review <= today)
    score = 100
    reasons: list[str] = []
    actions: list[str] = []

    if not has_plan:
        score -= 25
        reasons.append("missing_next_review")
        actions.append("补 next_review")
    elif due:
        overdue_days = (today - next_review).days
        score -= min(45, 30 + overdue_days // 14)
        reasons.append("review_due")
        actions.append("复习并更新 last_reviewed")

    if not last_reviewed:
        score -= 15
        reasons.append("missing_last_reviewed")
        actions.append("补 last_reviewed")
    elif age_days is not None and age_days >= 365:
        score -= min(35, age_days // 30)
        reasons.append("old_last_reviewed")
        actions.append("检索后续工作")
    elif age_days is not None and age_days >= 180:
        score -= 10
        reasons.append("aging_review")
        actions.append("安排半年复盘")

    if year_age is not None and year_age >= 3:
        score -= 15
        reasons.append("old_publication_year")
        actions.append("补近年 follow-up")
    elif year_age is not None and year_age >= 2:
        score -= 8
        reasons.append("aging_publication_year")

    if due:
        state = "due"
    elif not has_plan:
        state = "needs_plan"
    elif "old_last_reviewed" in reasons or "old_publication_year" in reasons:
        state = "stale"
    elif "aging_review" in reasons or "aging_publication_year" in reasons:
        state = "aging"
    else:
        state = "current"

    if not actions:
        actions.append("保持观察")
    score = max(0, score)
    return {
        "slug": paper["slug"],
        "title": paper["title"],
        "title_zh": paper["title_zh"],
        "research_line": paper.get("research_line") or "Unassigned",
        "line_role": paper.get("line_role") or "",
        "year": paper.get("year"),
        "importance": paper.get("importance"),
        "last_reviewed": paper.get("last_reviewed") or "",
        "next_review": paper.get("next_review") or "",
        "updated_at": paper.get("updated_at") or "",
        "age_days": age_days,
        "year_age": year_age,
        "state": state,
        "score": score,
        "reasons": reasons,
        "actions": actions,
        "html_path": paper.get("html_path") or paper.get("md_path"),
    }


def build_freshness_report(papers: list[dict[str, Any]]) -> dict[str, Any]:
    today = dt.date.today()
    items = [freshness_item(paper, today) for paper in papers]
    state_rank = {"due": 0, "needs_plan": 1, "stale": 2, "aging": 3, "current": 4}
    items.sort(key=lambda item: (state_rank.get(str(item["state"]), 9), int(item["score"]), -int(item.get("importance") or 0), item["title"]))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item.get("research_line") or "Unassigned")].append(item)
    line_health = []
    for line, line_items in grouped.items():
        average_score = round(sum(int(item["score"]) for item in line_items) / len(line_items), 1)
        state_counts = Counter(str(item["state"]) for item in line_items)
        line_health.append(
            {
                "research_line": line,
                "count": len(line_items),
                "average_score": average_score,
                "state_counts": dict(state_counts),
                "risk": "high" if state_counts.get("due") or state_counts.get("stale") else "medium" if state_counts.get("needs_plan") or state_counts.get("aging") else "low",
                "oldest_age_days": max((item["age_days"] or 0) for item in line_items),
                "actions": sorted({action for item in line_items for action in item["actions"] if action != "保持观察"})[:5],
            }
        )
    line_health.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(str(item["risk"]), 9), item["average_score"], item["research_line"]))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "count": len(items),
        "summary": {
            "states": dict(Counter(str(item["state"]) for item in items)),
            "average_score": round(sum(int(item["score"]) for item in items) / len(items), 1) if items else 100,
        },
        "queues": {
            "due": [item["slug"] for item in items if item["state"] == "due"],
            "needs_plan": [item["slug"] for item in items if item["state"] == "needs_plan"],
            "stale": [item["slug"] for item in items if item["state"] == "stale"],
            "aging": [item["slug"] for item in items if item["state"] == "aging"],
        },
        "line_health": line_health,
        "items": items,
    }


def write_freshness_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_freshness_report(papers)
    (report_dir / "freshness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_review_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_review_plan(papers)
    (report_dir / "review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_action_center(papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    freshness = build_freshness_report(papers)
    taxonomy_actions = build_taxonomy_actions(papers)
    paper_by_slug = {paper["slug"]: paper for paper in papers}
    severity_priority = {"high": 90, "medium": 60, "low": 30, "none": 10}
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def paper_title(slug: str) -> str:
        paper = paper_by_slug.get(slug) or {}
        return str(paper.get("title_zh") or paper.get("title") or slug)

    def paper_link(slug: str) -> str:
        paper = paper_by_slug.get(slug) or {}
        return str(paper.get("html_path") or paper.get("md_path") or page_query_href("library.html", q=slug))

    def add_action(
        action_id: str,
        group: str,
        severity: str,
        title: str,
        detail: str,
        href: str,
        source: str,
        slugs: list[str] | None = None,
        command: str = "",
        priority_bonus: int = 0,
    ) -> None:
        if action_id in seen:
            return
        seen.add(action_id)
        clean_slugs = [slug for slug in (slugs or []) if slug]
        max_importance = max((int((paper_by_slug.get(slug) or {}).get("importance") or 0) for slug in clean_slugs), default=0)
        actions.append(
            {
                "id": action_id,
                "group": group,
                "severity": severity,
                "priority": severity_priority.get(severity, 10) + max_importance * 2 + priority_bonus,
                "title": title,
                "detail": detail,
                "href": href,
                "source": source,
                "slugs": clean_slugs,
                "command": command,
            }
        )

    for item in review["items"]:
        slug = str(item["slug"])
        if item["state"] == "due":
            add_action(
                f"review_due:{slug}",
                "review",
                "high",
                f"复习到期：{paper_title(slug)}",
                f"next_review = {item.get('next_review') or item.get('suggested_next_review')}",
                paper_link(slug),
                "review.json",
                [slug],
                "python3 scripts/apply_review_plan.py docs",
                6,
            )
        elif item["state"] == "needs_plan":
            add_action(
                f"review_plan:{slug}",
                "review",
                "medium",
                f"补复习计划：{paper_title(slug)}",
                f"建议 next_review = {item.get('suggested_next_review')}",
                paper_link(slug),
                "review.json",
                [slug],
                "python3 scripts/apply_review_plan.py docs --write",
                4,
            )

    for item in freshness["items"]:
        state = str(item.get("state") or "")
        if state not in {"stale", "aging"}:
            continue
        slug = str(item.get("slug") or "")
        add_action(
            f"freshness:{state}:{slug}",
            "freshness",
            "high" if state == "stale" else "medium",
            f"更新时效：{paper_title(slug)}",
            "; ".join(str(action) for action in item.get("actions", []) if action),
            paper_link(slug),
            "freshness.json",
            [slug],
            "",
            5 if state == "stale" else 2,
        )

    issue_by_slug = {issue["slug"]: issue for issue in quality["issues"]}
    for slug in quality["queues"].get("missing_required_metadata", []):
        issue = issue_by_slug.get(slug, {})
        missing = ", ".join(issue.get("missing_fields", []))
        add_action(
            f"metadata_missing:{slug}",
            "metadata",
            "high",
            f"补必填元数据：{paper_title(slug)}",
            missing or "缺少必要 frontmatter 字段",
            page_query_href("library.html", q=slug),
            "quality.json",
            [slug],
            "python3 scripts/apply_library_metadata.py docs --input <csv>",
            8,
        )
    for slug in quality["queues"].get("no_code_observation", []):
        add_action(
            f"code_observation:{slug}",
            "quality",
            "low",
            f"补代码观察：{paper_title(slug)}",
            "缺少 has_code 或代码实现观察线索。",
            paper_link(slug),
            "quality.json",
            [slug],
        )
    for slug in quality["queues"].get("taxonomy_sparse", []):
        add_action(
            f"taxonomy_sparse:{slug}",
            "taxonomy",
            "medium",
            f"补分类粒度：{paper_title(slug)}",
            "结构分类或 topic/method 偏少，检索入口不足。",
            page_query_href("library.html", q=slug),
            "quality.json",
            [slug],
            "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv",
            4,
        )
    for slug in quality["queues"].get("taxonomy_dense", []):
        add_action(
            f"taxonomy_dense:{slug}",
            "taxonomy",
            "medium",
            f"审分类过密：{paper_title(slug)}",
            "topic/method 过密，可能需要保留更可区分的标签。",
            page_query_href("library.html", q=slug),
            "quality.json",
            [slug],
            "python3 scripts/export_taxonomy_load.py docs --format csv --signal dense_tags --output docs/exports/taxonomy-load.csv",
        )
    for item in quality["taxonomy_drift"]:
        slug = str(item["slug"])
        add_action(
            f"taxonomy_drift:{item['field']}:{item['value']}:{slug}",
            "taxonomy",
            "high",
            f"处理 taxonomy drift：{paper_title(slug)}",
            f"{item['field']} = {item['value']} 不在允许值中。",
            page_query_href("quality.html"),
            "quality.json",
            [slug],
            "python3 scripts/validate_wiki.py docs --strict-taxonomy",
            8,
        )
    for group in quality["duplicate_reports"]:
        slugs = [str(slug) for slug in group.get("slugs", [])]
        add_action(
            f"duplicate_reports:{group.get('reason')}:{'-'.join(slugs)}",
            "dedupe",
            "high",
            f"合并重复报告：{', '.join(slugs[:2])}",
            f"reason={group.get('reason')} value={group.get('value')}",
            "quality.html",
            "quality.json",
            slugs,
            "python3 scripts/check_quality.py docs",
            10,
        )
    for suggestion in quality["label_alias_suggestions"][:20]:
        aliases = ", ".join(suggestion.get("aliases", {}).keys())
        add_action(
            f"alias:{suggestion.get('fingerprint')}",
            "taxonomy",
            "medium",
            f"归一化标签：{suggestion.get('canonical')}",
            f"建议别名：{aliases}",
            "quality.html",
            "quality.json",
            [str(slug) for slug in suggestion.get("slugs", [])],
            "python3 scripts/apply_taxonomy_aliases.py docs --write",
            3,
        )

    for item in taxonomy_actions["actions"]:
        severity = str(item.get("severity") or "low")
        if severity == "none":
            continue
        value = str(item.get("value") or "")
        field = str(item.get("field_label") or item.get("field") or "")
        add_action(
            f"taxonomy_action:{item.get('action')}:{item.get('field')}:{value}",
            "taxonomy",
            severity,
            f"{field}：{value}",
            str(item.get("recommendation") or ""),
            str(item.get("href") or "facets.html"),
            "taxonomy_actions.json",
            [str(slug) for slug in item.get("sample_slugs", [])],
            "python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv",
        )

    for item in inbox_items:
        item_id = str(item.get("id") or item.get("title") or "")
        priority = str(item.get("priority") or "normal")
        duplicate = bool(item.get("duplicate"))
        if duplicate or priority == "high":
            add_action(
                f"inbox:{item_id}",
                "inbox",
                "high" if duplicate else "medium",
                f"{'去重候选' if duplicate else '处理高优先级候选'}：{item.get('title')}",
                str(item.get("note") or item.get("link") or ""),
                "inbox.html",
                "inbox.json",
                [],
                "",
                6 if duplicate else 3,
            )

    severity_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    actions.sort(key=lambda item: (severity_rank.get(str(item["severity"]), 9), -int(item["priority"]), item["group"], item["title"]))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(actions),
        "summary": {
            "groups": dict(Counter(str(item["group"]) for item in actions)),
            "severity": dict(Counter(str(item["severity"]) for item in actions)),
        },
        "actions": actions,
        "csv_columns": ["id", "group", "severity", "priority", "title", "detail", "href", "source", "slugs", "command"],
        "commands": [
            "python3 scripts/export_actions.py docs --output docs/exports/actions.md",
            "python3 scripts/export_actions.py docs --format csv --output docs/exports/actions.csv",
            "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv",
        ],
        "links": {
            "html": "actions.html",
            "library": "library.html",
            "quality": "quality.html",
            "review": "review.html",
            "taxonomy": "taxonomy.html",
            "facets": "facets.html",
            "inbox": "inbox.html",
            "dedupe": "dedupe.html",
            "command": "command.html",
        },
    }


def write_actions_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_action_center(papers, inbox_items)
    (report_dir / "actions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def command_recipe_map() -> dict[str, dict[str, Any]]:
    return {str(recipe["id"]): recipe for recipe in command_recipes_manifest()}


def command_lane(
    lane_id: str,
    title: str,
    description: str,
    primary_href: str,
    pages: list[str],
    data: list[str],
    command_ids: list[str],
    metrics: list[dict[str, Any]],
    next_actions: list[str],
    persona: str,
) -> dict[str, Any]:
    recipes = command_recipe_map()
    page_lookup = {item["href"]: item for item in wiki_pages_manifest()}
    data_lookup = {item["href"]: item for item in data_files_manifest()}
    return {
        "id": lane_id,
        "title": title,
        "description": description,
        "persona": persona,
        "primary_href": primary_href,
        "pages": [page_lookup[href] for href in pages if href in page_lookup],
        "data_files": [data_lookup[href] for href in data if href in data_lookup],
        "commands": [recipes[recipe_id] for recipe_id in command_ids if recipe_id in recipes],
        "metrics": metrics,
        "next_actions": [action for action in next_actions if action],
    }


def build_command_center_payload(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    freshness = build_freshness_report(papers)
    actions = build_action_center(papers, inbox_items)
    workflow = build_workflow_payload(papers)
    registry = build_registry_report(papers)
    stats = build_stats_report(papers)
    manifest = build_manifest(report_dir, papers, inbox_items, finalized=False)
    release_ready = all(
        passed
        for name, passed in manifest["publish_checks"].items()
        if name not in {"has_generated_pages", "artifacts_present"}
    )
    high_actions = int(actions["summary"]["severity"].get("high", 0))
    medium_actions = int(actions["summary"]["severity"].get("medium", 0))
    needs_plan = len(review["queues"].get("needs_plan", []))
    due_review = len(review["queues"].get("due", []))
    stale_reports = len(freshness["queues"].get("stale", []))
    inbox_duplicates = sum(1 for item in inbox_items if item.get("duplicate"))
    active_workflow = next((item for item in workflow["workflows"] if item.get("active")), workflow["workflows"][0] if workflow["workflows"] else {})
    registry_high = int(registry["summary"].get("high", 0))
    registry_medium = int(registry["summary"].get("medium", 0))

    lanes = [
        command_lane(
            "daily_reading",
            "Daily Reading",
            "日常阅读、筛选、复习和状态推进。适合每天打开的主工作区。",
            "library.html",
            ["index.html", "library.html", "batch.html", "collections.html", "review.html", "board.html", "status.html"],
            ["papers.json", "search_index.json", "batch.json", "review.json", "status.json"],
            ["actions_markdown", "actions_project"],
            [
                {"label": "论文", "value": len(papers), "hint": "library size"},
                {"label": "待复习", "value": due_review, "hint": "due review"},
                {"label": "缺计划", "value": needs_plan, "hint": "needs next_review"},
            ],
            [
                "打开 library.html 继续密集筛选和批量编辑。",
                "处理 review.json 中 due 或 needs_plan 的论文。",
                "用 board.html 把正在读的论文拖到下一状态。",
            ],
            "reader",
        ),
        command_lane(
            "paper_intake",
            "Paper Intake",
            "批量导入论文链接，先去重、路由，再进入正式阅读队列。",
            "intake.html",
            ["intake.html", "routing.html", "inbox.html", "dedupe.html", "library.html"],
            ["intake.json", "inbox.json", "dedupe.json", "routing.json"],
            ["apply_inbox_dry_run", "apply_inbox", "build_wiki"],
            [
                {"label": "候选", "value": len(inbox_items), "hint": "inbox items"},
                {"label": "重复", "value": inbox_duplicates, "hint": "candidate duplicates"},
                {"label": "路由画像", "value": len(stats["taxonomy"]["research_lines"]), "hint": "research lines"},
            ],
            [
                "在 intake.html 粘贴一批新论文链接并导出候选 CSV。",
                "用 routing.html 给标题/摘要生成初始分类建议。",
                "写回 inbox.csv 前先执行 dry-run 命令。",
            ],
            "curator",
        ),
        command_lane(
            "taxonomy_governance",
            "Taxonomy Governance",
            "管理 domain/track/problem/topic/method、研究线 owner、标签定义和分类漂移。",
            "registry.html",
            ["registry.html", "batch.html", "facets.html", "taxonomy.html", "balance.html", "coverage.html", "ownership.html"],
            ["registry.json", "batch.json", "taxonomy_actions.json", "quality.json", "ownership.json"],
            ["taxonomy_registry_project", "taxonomy_actions_project", "taxonomy_balance_project", "quality_gate"],
            [
                {"label": "高风险标签", "value": registry_high, "hint": "registry high"},
                {"label": "中风险标签", "value": registry_medium, "hint": "registry medium"},
                {"label": "分类任务", "value": actions["summary"]["groups"].get("taxonomy", 0), "hint": "taxonomy actions"},
            ],
            [
                "从 registry.html 处理 overloaded、deprecated 或 undefined 标签。",
                "用 facets.html 找长尾和过载分类，导出 project CSV 分派。",
                "修改 taxonomy.json 后运行 strict validation。",
            ],
            "maintainer",
        ),
        command_lane(
            "workflow_status",
            "Workflow & Status",
            "维护多套 status_workflows、状态定义和看板列，让个人阅读流与研究实现流共存。",
            "workflow.html",
            ["workflow.html", "status.html", "board.html", "library.html", "taxonomy.html"],
            ["workflow.json", "status.json", "papers.json"],
            ["apply_status_workflow_dry_run", "apply_status_workflow", "build_wiki", "strict_validate"],
            [
                {"label": "Workflow", "value": workflow["workflow_count"], "hint": "named workflows"},
                {"label": "Active", "value": workflow["active_status_workflow"], "hint": "current default"},
                {"label": "未配置值", "value": active_workflow.get("unconfigured_total", 0), "hint": "active drift"},
            ],
            [
                "在 status.html 试选 workflow/status 并复制共享视图。",
                "在 taxonomy.html 设计新 workflow，再用 apply_status_workflow dry-run。",
                "检查 workflow.json 的 unconfigured 值，决定迁移或保留。",
            ],
            "operator",
        ),
        command_lane(
            "research_synthesis",
            "Research Synthesis",
            "围绕研究线、年份、相似论文和缺口做综述、路线图与论文比较。",
            "roadmap.html",
            ["roadmap.html", "batch.html", "timeline.html", "matrix.html", "pivot.html", "compare.html", "related.html", "gaps.html", "clusters.html"],
            ["roadmap.json", "batch.json", "compare.json", "pivot.json", "taxonomy_map.json", "clusters.json"],
            ["actions_markdown"],
            [
                {"label": "研究线", "value": len(stats["taxonomy"]["research_lines"]), "hint": "lines"},
                {"label": "高优先级", "value": len([paper for paper in papers if int(paper.get("importance") or 0) >= 5]), "hint": "importance >= 5"},
                {"label": "缺口任务", "value": actions["summary"]["groups"].get("freshness", 0), "hint": "freshness/synthesis"},
            ],
            [
                "用 roadmap.html 看每条研究线的阶段覆盖和下一步。",
                "用 compare.html 对比同一研究线或同一方向的关键论文。",
                "用 gaps.html 发现下一批阅读或补报告目标。",
            ],
            "researcher",
        ),
        command_lane(
            "release_open_source",
            "Release & Open Source",
            "发布前检查、贡献者上手、机器数据目录和可复现质量门。",
            "release.html",
            ["command.html", "release.html", "snapshot.html", "onboarding.html", "catalog.html", "quality.html", "actions.html"],
            ["command.json", "manifest.json", "snapshot.json", "catalog.json", "onboarding.json", "actions.json"],
            ["build_wiki", "strict_validate", "quality_gate"],
            [
                {"label": "发布状态", "value": "ready" if release_ready else "needs work", "hint": "quality readiness"},
                {"label": "质量分", "value": manifest["quality_score"], "hint": "quality score"},
                {"label": "High action", "value": high_actions, "hint": "blocking work"},
            ],
            [
                "打开 release.html 检查 publish_ready 和 artifact inventory。",
                "在 onboarding.html 查看贡献路径和本地质量门。",
                "用 catalog.json / command.json 作为桌面软件或 DMG 封装入口。",
            ],
            "contributor",
        ),
    ]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "inbox_count": len(inbox_items),
        "lane_count": len(lanes),
        "active_status_workflow": workflow["active_status_workflow"],
        "quality_score": quality["quality_score"],
            "publish_ready": release_ready,
        "summary": {
            "papers": len(papers),
            "actions": actions["count"],
            "high_actions": high_actions,
            "medium_actions": medium_actions,
            "due_review": due_review,
            "needs_review_plan": needs_plan,
            "stale_reports": stale_reports,
            "taxonomy_registry_high": registry_high,
            "taxonomy_registry_medium": registry_medium,
            "workflow_count": workflow["workflow_count"],
            "inbox_count": len(inbox_items),
        },
        "lanes": lanes,
        "recommended_next": [
            {
                "label": "处理高优先级行动",
                "href": "actions.html?severity=high",
                "count": high_actions,
                "reason": "高优先级队列会阻碍发布或长期维护。",
            },
            {
                "label": "补复习计划",
                "href": "review.html",
                "count": needs_plan,
                "reason": "缺 next_review 的论文会从长期知识库里慢慢失焦。",
            },
            {
                "label": "治理标签注册表",
                "href": "registry.html?severity=high",
                "count": registry_high,
                "reason": "标签定义、alias 和过载桶决定大库检索质量。",
            },
            {
                "label": "发布前质量门",
                "href": "release.html",
                "count": 0 if release_ready else 1,
                "reason": "开源前确认生成物、数据契约和质量门一致。",
            },
        ],
        "links": {
            "library": "library.html",
            "actions": "actions.html",
            "registry": "registry.html",
            "workflow": "workflow.html",
            "release": "release.html",
            "catalog": "catalog.html",
            "manifest": "manifest.json",
        },
    }


def write_command_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_command_center_payload(report_dir, papers, inbox_items)
    (report_dir / "command.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_command_lane(lane: dict[str, Any]) -> str:
    metrics = "".join(
        f'<span class="command-metric"><strong>{html.escape(str(item.get("value", "")))}</strong>'
        f'<span>{html.escape(str(item.get("label", "")))}</span>'
        f'<em>{html.escape(str(item.get("hint", "")))}</em></span>'
        for item in lane.get("metrics", [])
    )
    pages = "".join(
        f'<a class="chip" href="{html.escape(str(page["href"]))}">{html.escape(str(page["title"]))}</a>'
        for page in lane.get("pages", [])
    )
    data_files = "".join(
        f'<a class="chip" href="{html.escape(str(item["href"]))}">{html.escape(str(item["href"]))}</a>'
        for item in lane.get("data_files", [])
    )
    commands = "".join(
        f'<button class="button copy-command-lane" type="button" data-command="{html.escape(str(command["command"]), quote=True)}">{html.escape(str(command["label"]))}</button>'
        for command in lane.get("commands", [])
    )
    next_actions = "".join(f'<li>{html.escape(str(action))}</li>' for action in lane.get("next_actions", []))
    search = " ".join(
        [
            str(lane.get("id", "")),
            str(lane.get("title", "")),
            str(lane.get("description", "")),
            str(lane.get("persona", "")),
            " ".join(str(page.get("title", "")) for page in lane.get("pages", [])),
            " ".join(str(item.get("href", "")) for item in lane.get("data_files", [])),
        ]
    ).lower()
    lane_commands = "\n".join(str(command.get("command") or "") for command in lane.get("commands", []) if command.get("command"))
    return f"""
<article class="command-lane" data-persona="{html.escape(str(lane.get("persona") or ""), quote=True)}" data-search="{html.escape(search, quote=True)}">
  <div class="command-lane-head">
    <div>
      <span class="flag">{html.escape(str(lane.get("persona") or ""))}</span>
      <h2>{html.escape(str(lane.get("title") or ""))}</h2>
      <p>{html.escape(str(lane.get("description") or ""))}</p>
    </div>
    <a class="button primary" href="{html.escape(str(lane.get("primary_href") or "index.html"))}">进入</a>
  </div>
  <div class="command-metrics">{metrics}</div>
  <div class="command-grid">
    <section><h3>入口</h3><div class="chips">{pages}</div></section>
    <section><h3>数据</h3><div class="chips">{data_files}</div></section>
    <section><h3>下一步</h3><ol>{next_actions}</ol></section>
    <section><h3>命令</h3><div class="command-stack">{commands}<button class="button copy-command-lane" type="button" data-command="{html.escape(lane_commands, quote=True)}">复制本组</button></div></section>
  </div>
</article>"""


def render_command(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_command_center_payload(report_dir, papers, inbox_items)
    lanes = payload["lanes"]
    lane_html = "".join(render_command_lane(lane) for lane in lanes)
    persona_options = "".join(
        f'<option value="{html.escape(persona, quote=True)}">{html.escape(persona)}</option>'
        for persona in sorted({str(lane.get("persona") or "") for lane in lanes if lane.get("persona")})
    )
    next_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["label"]))}</a></td>'
        f"<td>{html.escape(str(item['count']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in payload["recommended_next"]
    )
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    command_css = """
    .command-toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(160px, 220px) auto auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 14px;
    }
    .command-toolbar input,
    .command-toolbar select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      padding: 10px 12px;
      font: inherit;
    }
    .command-lanes {
      display: grid;
      gap: 14px;
    }
    .command-lane {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .command-lane[hidden] { display: none; }
    .command-lane-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
    }
    .command-lane h2 {
      margin: 6px 0 6px;
      font-size: 22px;
      letter-spacing: 0;
    }
    .command-lane p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .command-metrics {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      margin: 14px 0;
    }
    .command-metric {
      display: grid;
      gap: 2px;
      min-height: 76px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: color-mix(in srgb, var(--panel) 86%, white);
    }
    .command-metric strong { font-size: 20px; }
    .command-metric span { color: var(--ink); font-size: 13px; }
    .command-metric em { color: var(--muted); font-size: 12px; font-style: normal; }
    .command-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }
    .command-grid h3 {
      margin: 0 0 8px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0;
      color: var(--muted);
    }
    .command-grid ol {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
      line-height: 1.5;
    }
    .command-stack {
      display: grid;
      gap: 8px;
    }
    .command-stack .button {
      justify-content: start;
      text-align: left;
    }
    @media (max-width: 980px) {
      .command-toolbar { grid-template-columns: 1fr; }
      .command-lane-head { flex-direction: column; }
      .command-grid { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 640px) {
      .command-grid { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Command Center</div>
  <h1>命令中心</h1>
  <p class="lead">把论文阅读、批量导入、分类治理、状态工作流、研究综合和开源发布组织成可执行场景。适合功能变多以后作为第一层操作入口。</p>
  <div class="stats">
    <a class="stat" href="command.json">Command JSON</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="registry.html">标签注册表</a>
    <a class="stat" href="release.html">发布摘要</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">场景 {payload["lane_count"]}</span>
    <span class="stat">质量分 {payload["quality_score"]}</span>
  </div>
</header>
<main class="shell">
  <section class="metric-grid">
    <section class="metric-card"><span>行动队列</span><strong>{payload["summary"]["actions"]}</strong><span>actions.json</span></section>
    <section class="metric-card"><span>High</span><strong>{payload["summary"]["high_actions"]}</strong><span>优先处理</span></section>
    <section class="metric-card"><span>待复习</span><strong>{payload["summary"]["due_review"]}</strong><span>review.json</span></section>
    <section class="metric-card"><span>Workflow</span><strong>{payload["summary"]["workflow_count"]}</strong><span>{html.escape(str(payload["active_status_workflow"]))}</span></section>
  </section>
  <section>
    <h2 class="section-title">推荐下一步</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>行动</th><th>数量</th><th>原因</th></tr></thead><tbody>{next_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">场景入口</h2>
    <div class="command-toolbar">
      <input id="commandSearch" type="search" placeholder="搜索 reading、intake、taxonomy、release、页面或数据">
      <select id="commandPersona"><option value="">全部角色</option>{persona_options}</select>
      <strong id="commandVisible">{len(lanes)} / {len(lanes)} 场景</strong>
      <button class="button" id="copyCommandBootstrap" type="button">复制接入 JSON</button>
    </div>
    <div class="command-lanes" id="commandLanes">{lane_html}</div>
  </section>
</main>
<script>
const commandPayload = {payload_json};
const commandSearch = document.querySelector("#commandSearch");
const commandPersona = document.querySelector("#commandPersona");
const commandVisible = document.querySelector("#commandVisible");
const commandLanes = Array.from(document.querySelectorAll(".command-lane"));

function renderCommandLanes() {{
  const query = (commandSearch.value || "").trim().toLowerCase();
  const persona = commandPersona.value;
  let visible = 0;
  commandLanes.forEach(lane => {{
    const hit = (!query || lane.dataset.search.includes(query)) && (!persona || lane.dataset.persona === persona);
    lane.hidden = !hit;
    if (hit) visible += 1;
  }});
  commandVisible.textContent = `${{visible}} / ${{commandLanes.length}} 场景`;
}}

async function copyCommandText(text, button) {{
  try {{
    await navigator.clipboard.writeText(text);
    const old = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => button.textContent = old, 1200);
  }} catch (error) {{
    window.prompt("复制内容", text);
  }}
}}

document.querySelectorAll(".copy-command-lane").forEach(button => {{
  button.addEventListener("click", () => copyCommandText(button.dataset.command || "", button));
}});
document.querySelector("#copyCommandBootstrap").addEventListener("click", event => {{
  const bootstrap = {{
    generated_at: commandPayload.generated_at,
    entry: "command.html",
    data: "command.json",
    lanes: commandPayload.lanes.map(lane => ({{
      id: lane.id,
      title: lane.title,
      primary_href: lane.primary_href,
      persona: lane.persona,
      pages: lane.pages.map(page => page.href),
      data_files: lane.data_files.map(file => file.href),
    }})),
  }};
  copyCommandText(JSON.stringify(bootstrap, null, 2), event.currentTarget);
}});
[commandSearch, commandPersona].forEach(control => control.addEventListener("input", renderCommandLanes));
renderCommandLanes();
</script>
"""
    (report_dir / "command.html").write_text(page_shell("命令中心", body, data=payload, extra_css=command_css), encoding="utf-8")


def write_search_index(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "papers": [
            {
                "slug": paper["slug"],
                "title": paper["title"],
                "title_zh": paper["title_zh"],
                "title_en": paper["title_en"],
                "search_text": paper.get("_search_text", ""),
            }
            for paper in papers
        ],
    }
    (report_dir / "search_index.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def set_quick_open_papers(papers: list[dict[str, Any]]) -> None:
    global QUICK_OPEN_PAPERS
    QUICK_OPEN_PAPERS = [
        {
            "title": str(paper.get("title_zh") or paper.get("title") or paper["slug"]),
            "href": paper.get("html_path") or paper.get("md_path") or "",
            "meta": " · ".join(
                str(part)
                for part in [
                    paper.get("research_line") or "Unassigned",
                    paper.get("status") or "",
                    paper.get("arxiv_id") or "",
                ]
                if part
            ),
            "kind": "paper",
        }
        for paper in papers
        if paper.get("html_path") or paper.get("md_path")
    ]


def summarize_view_state(state: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in state.items() if str(value).strip()]
    return ", ".join(parts[:4]) + (" ..." if len(parts) > 4 else "")


def quick_open_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for page in wiki_pages_manifest():
        entries.append(
            {
                "title": str(page["title"]),
                "href": str(page["href"]),
                "meta": str(page["description"]),
                "kind": str(page["kind"]),
            }
        )
    for file in data_files_manifest():
        entries.append(
            {
                "title": f"Data: {file['href']}",
                "href": str(file["href"]),
                "meta": str(file["description"]),
                "kind": "data",
            }
        )
    for view in SHARED_VIEWS:
        entries.append(
            {
                "title": f"View: {view['name']}",
                "href": view_href(view),
                "meta": f"{view.get('page') or 'all'} · {summarize_view_state(view.get('state') or {})}",
                "kind": "view",
            }
        )
    for playbook in governance_playbooks_manifest():
        entries.append(
            {
                "title": f"Playbook: {playbook['label']}",
                "href": "release.html",
                "meta": str(playbook["description"]),
                "kind": "playbook",
            }
        )
    for recipe in command_recipes_manifest():
        entries.append(
            {
                "title": f"Command: {recipe['label']}",
                "href": "release.html",
                "meta": str(recipe["command"]),
                "kind": "command",
            }
        )
    entries.extend(QUICK_OPEN_PAPERS)
    return entries


def page_shell(
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    extra_css: str = "",
    base_prefix: str = "",
) -> str:
    embedded = ""
    css_extra = f"\n{extra_css.strip()}" if extra_css else ""
    quick_nav_prefix = json.dumps(base_prefix)
    quick_entries_json = json.dumps(quick_open_entries(), ensure_ascii=False)
    if data is not None:
        embedded = (
            "<script>\n"
            f"window.PAPER_WIKI = {json.dumps(data, ensure_ascii=False)};\n"
            "</script>\n"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ee;
      --panel: #fffdf8;
      --ink: #222426;
      --muted: #6b6f76;
      --line: #ded8cd;
      --accent: #2f6f73;
      --accent-2: #8a5d3b;
      --chip: #edf3f1;
      --shadow: 0 14px 36px rgba(48, 44, 36, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "PingFang SC", "Noto Sans SC", system-ui, -apple-system, sans-serif;
      line-height: 1.65;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
    header {{ padding: 44px 0 22px; }}
    .eyebrow {{ color: var(--accent-2); font-size: 13px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font-size: clamp(30px, 5vw, 56px); line-height: 1.08; letter-spacing: 0; }}
    .lead {{ max-width: 760px; margin: 0; color: var(--muted); font-size: 17px; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }}
    .stat, .chip {{
      display: inline-flex;
      align-items: center;
      gap: 7px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 7px 12px;
      color: var(--muted);
      font-size: 14px;
    }}
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 12px 0;
      background: color-mix(in srgb, var(--bg) 88%, transparent);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid color-mix(in srgb, var(--line) 80%, transparent);
    }}
    .controls {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(138px, 1fr)); gap: 10px; }}
    .controls input[type="search"] {{ grid-column: span 2; min-width: 260px; }}
    input, select {{
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      padding: 0 12px;
      font: inherit;
    }}
    main {{ padding: 28px 0 56px; }}
    .overview {{ margin-bottom: 30px; }}
    .line-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .line-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
    }}
    .line-card h2 {{ margin: 0 0 8px; font-size: 18px; line-height: 1.25; }}
    .line-card ul {{ margin: 10px 0 0; padding-left: 18px; }}
    .taxonomy-kicker {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 10px; }}
    .results-bar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin: 0 0 16px;
      color: var(--muted);
    }}
    .results-actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .saved-view {{ min-width: 180px; width: auto; }}
    .pager {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      margin-top: 22px;
      color: var(--muted);
    }}
    .pager[hidden] {{ display: none; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0; }}
    .metric-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric-card strong {{ display: block; font-size: 28px; line-height: 1.1; }}
    .metric-card span {{ color: var(--muted); font-size: 13px; }}
    .data-table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .data-table th, .data-table td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    .data-table th {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    .data-table tr:last-child td {{ border-bottom: 0; }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }}
    .library-table {{
      width: 100%;
      min-width: 1080px;
      border-collapse: collapse;
    }}
    .library-table th, .library-table td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    .library-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f0ebe1;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      text-transform: uppercase;
    }}
    .library-table tr:last-child td {{ border-bottom: 0; }}
    .library-table tr[hidden] {{ display: none; }}
    .library-title {{ min-width: 300px; }}
    .library-title strong {{ display: block; font-size: 15px; line-height: 1.3; }}
    .library-taxonomy {{ min-width: 210px; }}
    .library-actions {{ display: flex; flex-wrap: wrap; gap: 8px; min-width: 145px; }}
    .status-stack {{ display: grid; gap: 5px; }}
    .score-grid {{ display: grid; grid-template-columns: repeat(3, minmax(42px, 1fr)); gap: 6px; }}
    .score-grid span {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #faf7f0;
      padding: 4px 6px;
      color: var(--muted);
      font-size: 12px;
      text-align: center;
    }}
    .queue-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .queue-list {{ margin: 0; padding-left: 18px; }}
    .queue-list li {{ margin: 8px 0; }}
    .taxonomy-board {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }}
    .taxonomy-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .taxonomy-panel h2 {{ margin: 0 0 10px; font-size: 20px; }}
    .taxonomy-panel .data-table {{ border: 0; }}
    .matrix-link {{ display: inline-flex; min-width: 32px; justify-content: center; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 16px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
      min-height: 260px;
      display: flex;
      flex-direction: column;
    }}
    .card h2 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.25; letter-spacing: 0; }}
    .line-detail {{ display: grid; gap: 18px; }}
    .role-section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .role-section h2 {{ margin: 0 0 12px; font-size: 20px; }}
    .paper-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      padding: 12px 0;
      border-top: 1px solid color-mix(in srgb, var(--line) 70%, transparent);
    }}
    .paper-row:first-of-type {{ border-top: 0; }}
    .paper-row h3 {{ margin: 0 0 4px; font-size: 17px; line-height: 1.3; }}
    .paper-row .chips {{ margin-top: 8px; padding-top: 0; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .essence {{
      margin: 12px 0 0;
      padding: 10px 12px;
      border-left: 3px solid var(--accent);
      border-radius: 7px;
      background: var(--chip);
      color: #2f5054;
      font-size: 14px;
    }}
    .excerpt {{ color: #3f4448; margin: 12px 0; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: auto; padding-top: 12px; }}
    .chip {{ background: var(--chip); padding: 4px 9px; font-size: 12px; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 0 11px;
      font-size: 14px;
      font-weight: 650;
      color: var(--accent);
      cursor: pointer;
    }}
    .button:disabled {{ cursor: not-allowed; opacity: .45; }}
    .quick-open {{
      position: fixed;
      right: 18px;
      bottom: 18px;
      z-index: 80;
      min-width: 92px;
      box-shadow: var(--shadow);
    }}
    .quick-panel[hidden] {{ display: none; }}
    .quick-panel {{
      position: fixed;
      inset: 0;
      z-index: 100;
      display: grid;
      place-items: start center;
      padding: 74px 16px 16px;
      background: rgba(34, 36, 38, .28);
    }}
    .quick-dialog {{
      width: min(680px, 100%);
      max-height: min(720px, calc(100vh - 96px));
      display: grid;
      grid-template-rows: auto 1fr;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(28, 31, 32, .24);
      overflow: hidden;
    }}
    .quick-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .quick-close {{ min-width: 40px; padding: 0; }}
    .quick-list {{
      overflow-y: auto;
      padding: 8px;
    }}
    .quick-item {{
      display: grid;
      gap: 2px;
      width: 100%;
      border-radius: 8px;
      padding: 10px 12px;
      color: var(--ink);
    }}
    .quick-item-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .quick-kind {{
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #faf7f0;
      color: var(--muted);
      padding: 1px 7px;
      font-size: 11px;
      font-weight: 750;
      text-transform: uppercase;
    }}
    .quick-item:hover, .quick-item.is-active {{
      background: var(--chip);
      text-decoration: none;
    }}
    .quick-item strong {{ line-height: 1.25; }}
    .quick-empty {{ padding: 24px; color: var(--muted); }}
    .section-title {{ margin: 28px 0 12px; font-size: 22px; }}
    .tag-list {{ display: flex; flex-wrap: wrap; gap: 10px; }}
    .tag-pill {{
      display: inline-flex;
      justify-content: space-between;
      gap: 20px;
      min-width: 150px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px 12px;
    }}
    .empty {{
      border: 1px dashed var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 28px;
      color: var(--muted);
    }}
    .card-flags {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .flag {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      background: #f7f3eb;
      border: 1px solid var(--line);
      color: var(--muted);
      padding: 0 8px;
      font-size: 12px;
    }}
    @media (max-width: 760px) {{
      .controls {{ grid-template-columns: 1fr; }}
      .controls input[type="search"] {{ grid-column: auto; min-width: 0; }}
      .results-bar {{ align-items: flex-start; flex-direction: column; }}
      .pager {{ justify-content: flex-start; flex-wrap: wrap; }}
      .paper-row {{ grid-template-columns: 1fr; }}
      .data-table {{ display: block; overflow-x: auto; }}
      header {{ padding-top: 28px; }}
    }}{css_extra}
  </style>
</head>
<body>
{embedded}
<button class="button quick-open" type="button" id="quickOpen">快速跳转</button>
<div class="quick-panel" id="quickPanel" hidden>
  <div class="quick-dialog" role="dialog" aria-modal="true" aria-label="快速跳转">
    <div class="quick-head">
      <input id="quickSearch" type="search" placeholder="搜索页面或论文" aria-labelledby="quickTitle">
      <button class="button quick-close" type="button" id="quickClose" aria-label="关闭">×</button>
    </div>
    <div class="quick-list" id="quickList"></div>
  </div>
</div>
{body}
<script>
(() => {{
  const prefix = {quick_nav_prefix};
  const openButton = document.querySelector("#quickOpen");
  const panel = document.querySelector("#quickPanel");
  const search = document.querySelector("#quickSearch");
  const list = document.querySelector("#quickList");
  const closeButton = document.querySelector("#quickClose");
  if (!openButton || !panel || !search || !list || !closeButton) return;

  function withPrefix(href) {{
    if (!href || href.startsWith("#") || href.startsWith("/") || /^[a-z][a-z0-9+.-]*:/i.test(href)) return href;
    return prefix + href;
  }}

  const quickEntries = {quick_entries_json}.map((entry) => ({{
    ...entry,
    href: withPrefix(entry.href || ""),
    meta: entry.meta || "",
    kind: entry.kind || "entry",
  }})).filter((entry) => entry.title && entry.href);

  const dataPapers = (window.PAPER_WIKI && Array.isArray(window.PAPER_WIKI.papers))
    ? window.PAPER_WIKI.papers.map((paper) => ({{
        title: paper.title_zh || paper.title || paper.slug,
        href: withPrefix(paper.html_path || paper.md_path || ""),
        meta: [paper.research_line, paper.status, paper.arxiv_id].filter(Boolean).join(" · "),
        kind: "paper",
      }})).filter((item) => item.href)
    : [];
  const rowPapers = Array.from(document.querySelectorAll("[data-slug][data-href]")).map((row) => ({{
    title: row.dataset.titleZh || row.dataset.title || row.dataset.slug,
    href: row.dataset.href || "",
    meta: [row.dataset.line, row.dataset.status, row.dataset.arxivId].filter(Boolean).join(" · "),
    kind: "paper",
  }})).filter((item) => item.href);
  const entryMap = new Map([...quickEntries, ...dataPapers, ...rowPapers].map((item) => [`${{item.kind}}:${{item.href}}:${{item.title}}`, item]));
  const entries = Array.from(entryMap.values());
  const kindPriority = {{ view: 5, page: 4, paper: 3, playbook: 2, command: 1, data: 1 }};
  let activeIndex = 0;

  function score(entry, query) {{
    if (!query) return kindPriority[entry.kind] || 1;
    const haystack = `${{entry.title}} ${{entry.meta}} ${{entry.href}}`.toLowerCase();
    if (haystack.includes(query)) return (entry.title.toLowerCase().includes(query) ? 30 : 20) + (kindPriority[entry.kind] || 1);
    return 0;
  }}

  function currentEntries() {{
    const query = search.value.trim().toLowerCase();
    return entries
      .map((entry) => [score(entry, query), entry])
      .filter(([rank]) => rank > 0)
      .sort((left, right) => right[0] - left[0] || left[1].title.localeCompare(right[1].title))
      .slice(0, 40)
      .map(([, entry]) => entry);
  }}

  function render() {{
    const visible = currentEntries();
    activeIndex = Math.min(activeIndex, Math.max(visible.length - 1, 0));
    if (!visible.length) {{
      list.innerHTML = '<div class="quick-empty">没有匹配结果</div>';
      return;
    }}
    list.replaceChildren(...visible.map((entry, index) => {{
      const link = document.createElement("a");
      link.className = `quick-item${{index === activeIndex ? " is-active" : ""}}`;
      link.href = entry.href;
      link.dataset.index = String(index);
      const titleWrap = document.createElement("span");
      titleWrap.className = "quick-item-title";
      const title = document.createElement("strong");
      title.textContent = entry.title;
      const kind = document.createElement("span");
      kind.className = "quick-kind";
      kind.textContent = entry.kind;
      titleWrap.append(title, kind);
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = entry.meta || entry.href;
      link.append(titleWrap, meta);
      return link;
    }}));
  }}

  function open() {{
    panel.hidden = false;
    search.value = "";
    activeIndex = 0;
    render();
    search.focus();
  }}

  function close() {{
    panel.hidden = true;
    openButton.focus();
  }}

  openButton.addEventListener("click", open);
  closeButton.addEventListener("click", close);
  panel.addEventListener("click", (event) => {{
    if (event.target === panel) close();
  }});
  search.addEventListener("input", () => {{
    activeIndex = 0;
    render();
  }});
  search.addEventListener("keydown", (event) => {{
    const visible = currentEntries();
    if (event.key === "Escape") {{
      event.preventDefault();
      close();
    }} else if (event.key === "ArrowDown") {{
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, Math.max(visible.length - 1, 0));
      render();
    }} else if (event.key === "ArrowUp") {{
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      render();
    }} else if (event.key === "Enter" && visible[activeIndex]) {{
      event.preventDefault();
      window.location.href = visible[activeIndex].href;
    }}
  }});
  document.addEventListener("keydown", (event) => {{
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {{
      event.preventDefault();
      panel.hidden ? open() : close();
    }}
  }});
}})();
</script>
</body>
</html>
"""


def render_line_overview(papers: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[paper.get("research_line") or "Unassigned"].append(paper)

    assigned = {
        line: items
        for line, items in grouped.items()
        if line != "Unassigned"
    }
    if not assigned:
        return ""

    cards = []
    for line in sorted(assigned, key=lambda name: (-len(assigned[name]), name.lower())):
        items = sorted(
            assigned[line],
            key=lambda paper: (role_rank(paper.get("line_role", "")), -(paper.get("year") or 0)),
        )
        line_href = f"lines/{slugify_label(line)}.html"
        paper_items = "".join(
            f'<li><a href="{html.escape(paper_href(p))}">{html.escape(p["title_zh"] or p["title"])}</a>'
            f' <span class="meta">{html.escape(str(p.get("line_role") or p.get("year") or ""))}</span></li>'
            for p in items[:6]
        )
        roles = sorted({p.get("line_role") for p in items if p.get("line_role")}, key=role_rank)
        role_html = "".join(f'<span class="flag">{html.escape(role)}</span>' for role in roles)
        cards.append(
            f'<section class="line-card"><h2><a href="{html.escape(line_href)}">{html.escape(line)}</a> <span class="meta">{len(items)}</span></h2>'
            f'<div class="card-flags">{role_html}</div><ul>{paper_items}</ul></section>'
        )

    return f"""
<section class="overview">
  <h2 class="section-title">研究线概览</h2>
  <div class="line-grid">{''.join(cards)}</div>
</section>
"""


def render_index_lane(lane: dict[str, Any]) -> str:
    metrics = " · ".join(
        f"{item.get('label')}: {item.get('value')}"
        for item in lane.get("metrics", [])[:3]
    )
    pages = "".join(
        f'<a class="chip" href="{html.escape(str(page.get("href") or ""))}">{html.escape(str(page.get("title") or ""))}</a>'
        for page in lane.get("pages", [])[:4]
    )
    next_action = str((lane.get("next_actions") or [""])[0] or "")
    return f"""
<article class="home-lane" data-persona="{html.escape(str(lane.get("persona") or ""), quote=True)}">
  <div class="home-lane-main">
    <span class="flag">{html.escape(str(lane.get("persona") or ""))}</span>
    <h2>{html.escape(str(lane.get("title") or ""))}</h2>
    <p>{html.escape(str(lane.get("description") or ""))}</p>
    <div class="meta">{html.escape(metrics)}</div>
  </div>
  <div class="home-lane-actions">
    <a class="button primary" href="{html.escape(str(lane.get("primary_href") or "command.html"))}">进入</a>
    <a class="button" href="command.html">详情</a>
  </div>
  <div class="chips">{pages}</div>
  <div class="home-next">{html.escape(next_action)}</div>
</article>"""


def render_index(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
    controls = control_options()
    command_payload = build_command_center_payload(report_dir, papers, inbox_items)
    index_controls = {key: value for key, value in controls.items() if key != "shared_views"}
    data = {
        "papers": [public_paper(paper) for paper in papers],
        "search_index": [
            {
                "slug": paper["slug"],
                "search_text": paper.get("_search_text", ""),
            }
            for paper in papers
        ],
        "tags": tag_counts(papers),
        "taxonomy": taxonomy,
        "controls": index_controls,
        "command": command_payload,
        "shared_views": shared_views_for("index"),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    cards = "\n".join(render_card(paper) for paper in papers)
    line_overview = render_line_overview(papers)
    lane_cards = "".join(render_index_lane(lane) for lane in command_payload["lanes"])
    command_next = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["label"]))}</a></td>'
        f"<td>{html.escape(str(item['count']))}</td>"
        f"<td>{html.escape(str(item['reason']))}</td>"
        "</tr>"
        for item in command_payload["recommended_next"]
    )
    index_css = """
    .home-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr);
      gap: 18px;
      align-items: start;
      margin-top: 22px;
    }
    .home-primary-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }
    .button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .home-command-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .home-command-panel h2 {
      margin: 0 0 10px;
      font-size: 20px;
      letter-spacing: 0;
    }
    .home-command-panel .data-table {
      border: 0;
      background: transparent;
    }
    .home-lanes {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 14px;
      margin-top: 14px;
    }
    .home-lane {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .home-lane-main h2 {
      margin: 6px 0 6px;
      font-size: 20px;
      letter-spacing: 0;
    }
    .home-lane-main p {
      margin: 0 0 8px;
      color: var(--muted);
      line-height: 1.5;
    }
    .home-lane-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: end;
    }
    .home-lane .chips {
      grid-column: 1 / -1;
      margin-top: 0;
      padding-top: 0;
    }
    .home-next {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 13px;
      border-top: 1px solid color-mix(in srgb, var(--line) 72%, transparent);
      padding-top: 10px;
    }
    @media (max-width: 860px) {
      .home-hero { grid-template-columns: 1fr; }
      .home-lane { grid-template-columns: 1fr; }
      .home-lane-actions { justify-content: start; }
    }
    """
    empty = """
      <div class="empty">
        还没有论文报告。生成第一篇 <code>docs/&lt;slug&gt;.md</code> 后，再运行
        <code>python3 scripts/build_wiki.py</code>，这里就会长出你的论文知识库。
      </div>
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">AutoPaperReader Wiki</div>
  <h1>我的论文知识库</h1>
  <p class="lead">这里汇总每一篇独立阅读报告，并按阅读、导入、分类治理、状态流、研究综合和开源发布组织成可执行工作台。</p>
  <div class="home-primary-actions">
    <a class="button primary" href="command.html">打开命令中心</a>
    <a class="button" href="library.html">进入论文库</a>
    <a class="button" href="actions.html">查看行动队列</a>
    <a class="button" href="registry.html">治理标签</a>
  </div>
  <div class="stats">
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">研究线 {len(taxonomy["research_lines"])}</span>
    <span class="stat">分类 {len(data["tags"])}</span>
    <span class="stat">行动 {command_payload["summary"]["actions"]}</span>
    <span class="stat">High {command_payload["summary"]["high_actions"]}</span>
    <span class="stat">最近更新 {html.escape(data["generated_at"])}</span>
    <a class="stat" href="command.html">命令中心</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="batch.html">批次规划</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="tags.html">分类总览</a>
    <a class="stat" href="quality.json">质量 JSON</a>
    <a class="stat" href="stats.json">统计 JSON</a>
    <a class="stat" href="papers.json">JSON 索引</a>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="search" type="search" placeholder="全文搜索：标题、作者、主题、方法、正文关键词">
    <select id="domain"><option value="">全部领域</option>{render_topic_options(taxonomy["domains"])}</select>
    <select id="line"><option value="">全部研究线</option>{render_topic_options(taxonomy["research_lines"])}</select>
    <select id="role"><option value="">全部角色</option>{render_topic_options(taxonomy["line_roles"])}</select>
    <select id="statusWorkflow" aria-label="状态体系"></select>
    <select id="topic"><option value="">全部主题</option>{render_topic_options(taxonomy["topics"])}</select>
    <select id="method"><option value="">全部方法</option>{render_topic_options(taxonomy["methods"])}</select>
    <select id="status"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="stage"><option value="">阅读阶段</option>{render_topic_options(taxonomy["reading_stages"])}</select>
    <select id="code"><option value="">代码状态</option><option value="yes">有代码观察</option><option value="no">无代码观察</option></select>
    <select id="importance"><option value="">重要性</option><option value="5">5 星</option><option value="4">4 星及以上</option><option value="3">3 星及以上</option></select>
    <select id="reviewStage"><option value="">复习阶段</option>{render_topic_options(taxonomy["review_stages"])}</select>
    <select id="review"><option value="">复习时间</option><option value="due">待复习</option><option value="none">未设置复习</option></select>
    <select id="sort"><option value="default">默认排序</option><option value="importance">重要性优先</option><option value="updated">最近更新</option><option value="year">年份新到旧</option><option value="reading">阅读时间短到长</option><option value="title">标题 A-Z</option></select>
    <select id="pageSize"><option value="12">每页 12 篇</option><option value="24">每页 24 篇</option><option value="48">每页 48 篇</option><option value="all">显示全部</option></select>
  </div>
</div>
<main class="shell">
  <section class="home-hero">
    <div>
      <h2 class="section-title">按场景进入</h2>
      <div class="home-lanes">{lane_cards}</div>
    </div>
    <aside class="home-command-panel">
      <h2>推荐下一步</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>行动</th><th>数量</th><th>原因</th></tr></thead><tbody>{command_next}</tbody></table></div>
      <div class="links">
        <a class="button" href="command.json">Command JSON</a>
        <a class="button" href="manifest.json">Manifest JSON</a>
      </div>
    </aside>
  </section>
  {line_overview}
  <h2 class="section-title">论文检索</h2>
  <div class="results-bar">
    <strong id="resultCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <div class="results-actions">
      <select id="savedView" class="saved-view" aria-label="选择保存视图"><option value="">选择视图</option></select>
      <button id="saveView" class="button" type="button">保存视图</button>
      <button id="copyCurrentLink" class="button" type="button">复制当前链接</button>
      <button id="copySharedView" class="button" type="button">复制共享视图</button>
      <button id="deleteView" class="button" type="button">删除视图</button>
      <button id="exportSavedViews" class="button" type="button">导出视图</button>
      <button id="importSavedViews" class="button" type="button">导入视图</button>
      <button id="resetFilters" class="button" type="button">重置筛选</button>
    </div>
  </div>
  <div id="cards" class="grid">{cards if papers else empty}</div>
  <nav id="pager" class="pager" aria-label="分页">
    <button id="prevPage" class="button" type="button">上一页</button>
    <span id="pageInfo">第 1 / 1 页</span>
    <button id="nextPage" class="button" type="button">下一页</button>
  </nav>
</main>
<script>
const papers = window.PAPER_WIKI.papers;
const cards = document.querySelector("#cards");
const resultCount = document.querySelector("#resultCount");
const search = document.querySelector("#search");
const domain = document.querySelector("#domain");
const line = document.querySelector("#line");
const role = document.querySelector("#role");
const statusWorkflow = document.querySelector("#statusWorkflow");
const topic = document.querySelector("#topic");
const method = document.querySelector("#method");
const status = document.querySelector("#status");
const stage = document.querySelector("#stage");
const code = document.querySelector("#code");
const importance = document.querySelector("#importance");
const reviewStage = document.querySelector("#reviewStage");
const review = document.querySelector("#review");
const sort = document.querySelector("#sort");
const pageSize = document.querySelector("#pageSize");
const resetFilters = document.querySelector("#resetFilters");
const pager = document.querySelector("#pager");
const pageInfo = document.querySelector("#pageInfo");
const prevPage = document.querySelector("#prevPage");
const nextPage = document.querySelector("#nextPage");
const savedView = document.querySelector("#savedView");
const saveView = document.querySelector("#saveView");
const copyCurrentLink = document.querySelector("#copyCurrentLink");
const copySharedView = document.querySelector("#copySharedView");
const deleteView = document.querySelector("#deleteView");
const exportSavedViews = document.querySelector("#exportSavedViews");
const importSavedViews = document.querySelector("#importSavedViews");
const searchTextBySlug = new Map((window.PAPER_WIKI.search_index || []).map(item => [item.slug, item.search_text || ""]));
const sharedViews = window.PAPER_WIKI.shared_views || [];
const wikiControls = window.PAPER_WIKI.controls || {{}};
const statusWorkflows = wikiControls.status_workflows || {{}};
const activeStatusWorkflow = wikiControls.active_status_workflow || Object.keys(statusWorkflows)[0] || "default";
const fallbackStatusValues = Array.isArray(wikiControls.status) ? wikiControls.status : [];
const fallbackStageValues = Array.isArray(wikiControls.reading_stage) ? wikiControls.reading_stage : [];
const fallbackReviewStageValues = Array.isArray(wikiControls.review_stage) ? wikiControls.review_stage : [];
const observedStatusValues = Array.from(new Set(papers.map(p => p.status).filter(Boolean)));
const observedStageValues = Array.from(new Set(papers.map(p => p.reading_stage).filter(Boolean)));
const observedReviewStageValues = Array.from(new Set(papers.map(p => p.review_stage).filter(Boolean)));
let currentPage = 1;
const savedViewsKey = "autopaperreader:index:savedViews";
const queryControls = [
  ["q", search],
  ["domain", domain],
  ["line", line],
  ["role", role],
  ["workflow", statusWorkflow],
  ["topic", topic],
  ["method", method],
  ["status", status],
  ["stage", stage],
  ["code", code],
  ["importance", importance],
  ["reviewStage", reviewStage],
  ["review", review],
  ["sort", sort],
  ["size", pageSize],
];

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, ch => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[ch]));
}}

function clampPage(page, totalPages) {{
  return Math.min(Math.max(page, 1), totalPages);
}}

function getPageSize() {{
  return pageSize.value === "all" ? Infinity : Number(pageSize.value || 12);
}}

function orderedUnique(values) {{
  return Array.from(new Set(values.map(value => String(value || "").trim()).filter(Boolean)));
}}

function workflowValuesFor(name, key, fallbackValues, observedValues) {{
  const workflow = statusWorkflows[name] || {{}};
  const configured = Array.isArray(workflow[key]) ? workflow[key] : fallbackValues;
  return orderedUnique([...configured, ...observedValues]);
}}

function statusValuesForWorkflow(name) {{
  return workflowValuesFor(name, "status_values", fallbackStatusValues, observedStatusValues);
}}

function valueCount(key, value) {{
  return papers.filter(p => String(p[key] || "") === value).length;
}}

function replaceWorkflowOptions(select, placeholder, values, field, withCounts = false) {{
  const current = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  values.forEach(value => {{
    const label = withCounts ? `${{value}} (${{valueCount(field, value)}})` : value;
    select.appendChild(new Option(label, value));
  }});
  select.value = values.includes(current) ? current : "";
}}

function populateStatusWorkflowOptions() {{
  const names = Object.keys(statusWorkflows);
  const workflowNames = names.length ? names : [activeStatusWorkflow];
  statusWorkflow.replaceChildren(...workflowNames.map(name => {{
    const label = name === activeStatusWorkflow ? `${{name}} (默认)` : name;
    return new Option(label, name);
  }}));
  statusWorkflow.value = workflowNames.includes(activeStatusWorkflow) ? activeStatusWorkflow : workflowNames[0] || "";
}}

function applyStatusWorkflow() {{
  const workflowName = statusWorkflow.value || activeStatusWorkflow;
  const statusValues = statusValuesForWorkflow(workflowName);
  const stageValues = workflowValuesFor(workflowName, "reading_stage_values", fallbackStageValues, observedStageValues);
  const reviewStageValues = workflowValuesFor(workflowName, "review_stage_values", fallbackReviewStageValues, observedReviewStageValues);
  replaceWorkflowOptions(status, "全部状态", statusValues, "status", true);
  replaceWorkflowOptions(stage, "阅读阶段", stageValues, "reading_stage", true);
  replaceWorkflowOptions(reviewStage, "复习阶段", reviewStageValues, "review_stage", true);
}}

function defaultValueFor(key) {{
  return key === "workflow" ? activeStatusWorkflow : key === "sort" ? "default" : key === "size" ? "12" : "";
}}

function currentState() {{
  const state = {{}};
  queryControls.forEach(([key, el]) => {{
    const defaultValue = defaultValueFor(key);
    if (el.value && el.value !== defaultValue) state[key] = el.value;
  }});
  if (currentPage > 1) state.page = String(currentPage);
  return state;
}}

function applyState(state) {{
  queryControls.forEach(([key, el]) => {{
    if (["status", "stage", "reviewStage"].includes(key)) return;
    el.value = state[key] || defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = state.status || defaultValueFor("status");
  stage.value = state.stage || defaultValueFor("stage");
  reviewStage.value = state.reviewStage || defaultValueFor("reviewStage");
  currentPage = Number(state.page || 1) || 1;
  render();
}}

function readStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  queryControls.forEach(([key, el]) => {{
    if (["status", "stage", "reviewStage"].includes(key)) return;
    el.value = params.has(key) ? params.get(key) : defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = params.has("status") ? params.get("status") : defaultValueFor("status");
  stage.value = params.has("stage") ? params.get("stage") : defaultValueFor("stage");
  reviewStage.value = params.has("reviewStage") ? params.get("reviewStage") : defaultValueFor("reviewStage");
  currentPage = Number(params.get("page") || 1) || 1;
}}

function writeStateToUrl() {{
  const params = new URLSearchParams(currentState());
  const query = params.toString();
  const nextUrl = query ? `${{location.pathname}}?${{query}}` : location.pathname;
  window.history.replaceState(null, "", nextUrl);
}}

function currentViewUrl() {{
  const params = new URLSearchParams(currentState());
  const url = new URL(window.location.href);
  url.search = params.toString();
  url.hash = "";
  return url.toString();
}}

function readSavedViews() {{
  try {{
    const views = JSON.parse(localStorage.getItem(savedViewsKey) || "[]");
    return Array.isArray(views) ? views.filter(view => view && view.name && view.state) : [];
  }} catch {{
    return [];
  }}
}}

function writeSavedViews(views) {{
  try {{
    localStorage.setItem(savedViewsKey, JSON.stringify(views.slice(0, 50)));
    return true;
  }} catch {{
    window.alert("浏览器本地存储不可用，无法保存视图。");
    return false;
  }}
}}

function normalizeSavedViews(payload, pageName) {{
  const candidates = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.saved_views)
      ? payload.saved_views
      : Array.isArray(payload?.shared_views)
        ? payload.shared_views
        : payload?.name && payload?.state
          ? [payload]
          : [];
  const allowedKeys = new Set([...queryControls.map(([key]) => key), "page"]);
  const pageScope = new Set(["all", pageName, ""]);
  return candidates.map(view => {{
    const page = String(view?.page || "").trim();
    if (!pageScope.has(page)) return null;
    const name = String(view?.name || "").trim();
    const rawState = view?.state && typeof view.state === "object" && !Array.isArray(view.state) ? view.state : {{}};
    const state = Object.fromEntries(Object.entries(rawState)
      .filter(([key, value]) => allowedKeys.has(key) && value !== null && typeof value !== "object")
      .map(([key, value]) => [key, String(value)]));
    return name ? {{ name, state }} : null;
  }}).filter(Boolean);
}}

function sharedViewPayload(page) {{
  const name = window.prompt("共享视图名称");
  if (!name || !name.trim()) return null;
  const state = {{ ...currentState() }};
  delete state.page;
  if (!Object.keys(state).length) {{
    window.alert("当前没有可共享的筛选条件。");
    return null;
  }}
  return {{ name: name.trim(), page, state }};
}}

async function copyJsonSnippet(payload) {{
  if (!payload) return;
  const text = JSON.stringify(payload, null, 2);
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制 shared view JSON。");
  }} catch {{
    window.prompt("复制 shared view JSON", text);
  }}
}}

async function copyText(text, fallbackLabel) {{
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt(fallbackLabel, text);
  }}
}}

function downloadText(filename, text, type = "text/plain;charset=utf-8") {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function refreshSavedViews() {{
  const views = readSavedViews();
  savedView.replaceChildren(new Option("选择视图", ""));
  if (sharedViews.length) {{
    const sharedGroup = document.createElement("optgroup");
    sharedGroup.label = "共享视图";
    sharedViews.forEach((view, index) => sharedGroup.appendChild(new Option(view.name, `shared:${{index}}`)));
    savedView.appendChild(sharedGroup);
  }}
  if (views.length) {{
    const localGroup = document.createElement("optgroup");
    localGroup.label = "本地视图";
    views.forEach((view, index) => localGroup.appendChild(new Option(view.name, `local:${{index}}`)));
    savedView.appendChild(localGroup);
  }}
}}

function card(p) {{
  const link = p.html_path || p.md_path;
  const tags = [...(p.domains || []), ...(p.topics || []), ...(p.methods || [])].map(t => `<span class="chip">${{esc(t)}}</span>`).join("");
  const authors = (p.authors || []).slice(0, 4).join(", ");
  const flags = [
    p.reading_time_min ? `${{esc(p.reading_time_min)}} min` : "",
    p.importance ? `重要性 ${{esc(p.importance)}}` : "",
    p.research_line ? `研究线 ${{esc(p.research_line)}}` : "",
    p.line_role ? `角色 ${{esc(p.line_role)}}` : "",
    p.reading_stage ? `阅读 ${{esc(p.reading_stage)}}` : "",
    p.review_stage ? `复习 ${{esc(p.review_stage)}}` : "",
    p.next_review ? `下次 ${{esc(p.next_review)}}` : "",
  ].filter(Boolean).map(item => `<span class="flag">${{item}}</span>`).join("");
  return `<article class="card">
    <h2><a href="${{esc(link)}}">${{esc(p.title_zh || p.title)}}</a></h2>
    ${{p.title_en ? `<div class="meta">${{esc(p.title_en)}}</div>` : ""}}
    <div class="meta">${{esc([p.year, authors, p.arxiv_id].filter(Boolean).join(" / "))}}</div>
    <div class="card-flags">${{flags}}</div>
    ${{p.essence ? `<p class="essence">${{esc(p.essence)}}</p>` : ""}}
    <p class="excerpt">${{esc(p.excerpt || "暂无摘要。")}}</p>
    <div class="links">
      <a class="button" href="${{esc(link)}}">阅读报告</a>
      ${{p.arxiv_url ? `<a class="button" href="${{esc(p.arxiv_url)}}">arxiv</a>` : ""}}
      ${{p.code_url ? `<a class="button" href="${{esc(p.code_url)}}">code</a>` : ""}}
    </div>
    <div class="chips">${{tags}}</div>
  </article>`;
}}

function sortPapers(items) {{
  const mode = sort.value;
  const ranked = [...items];
  const byTitle = p => String(p.title_en || p.title || p.slug || "");
  ranked.sort((a, b) => {{
    if (mode === "importance") return Number(b.importance || 0) - Number(a.importance || 0) || Number(b.year || 0) - Number(a.year || 0) || byTitle(a).localeCompare(byTitle(b));
    if (mode === "updated") return String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || byTitle(a).localeCompare(byTitle(b));
    if (mode === "year") return Number(b.year || 0) - Number(a.year || 0) || byTitle(a).localeCompare(byTitle(b));
    if (mode === "reading") return Number(a.reading_time_min || 0) - Number(b.reading_time_min || 0) || byTitle(a).localeCompare(byTitle(b));
    if (mode === "title") return byTitle(a).localeCompare(byTitle(b));
    return Number(b.year || 0) - Number(a.year || 0) || String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
  }});
  return ranked;
}}

function render() {{
  const q = search.value.trim().toLowerCase();
  const domainValue = domain.value;
  const lineValue = line.value;
  const roleValue = role.value;
  const topicValue = topic.value;
  const methodValue = method.value;
  const statusValue = status.value;
  const stageValue = stage.value;
  const codeValue = code.value;
  const importanceValue = Number(importance.value || 0);
  const reviewStageValue = reviewStage.value;
  const reviewValue = review.value;
  const today = new Date().toISOString().slice(0, 10);
  const filtered = papers.filter(p => {{
    const text = [p.slug, p.title, p.title_zh, p.title_en, p.arxiv_id, p.excerpt, p.essence, p.research_line, p.line_role, p.status, p.reading_stage, p.review_stage, ...(p.authors || []), ...(p.domains || []), ...(p.tracks || []), ...(p.problems || []), ...(p.topics || []), ...(p.methods || []), searchTextBySlug.get(p.slug) || ""].join(" ").toLowerCase();
    const domainHit = !domainValue || (p.domains || []).includes(domainValue);
    const lineHit = !lineValue || p.research_line === lineValue;
    const roleHit = !roleValue || p.line_role === roleValue;
    const topicHit = !topicValue || (p.topics || []).includes(topicValue);
    const methodHit = !methodValue || (p.methods || []).includes(methodValue);
    const statusHit = !statusValue || p.status === statusValue;
    const stageHit = !stageValue || p.reading_stage === stageValue;
    const codeHit = !codeValue || (codeValue === "yes" ? p.has_code : !p.has_code);
    const importanceHit = !importanceValue || Number(p.importance || 0) >= importanceValue;
    const reviewStageHit = !reviewStageValue || p.review_stage === reviewStageValue;
    const reviewHit = !reviewValue ||
      (reviewValue === "none" ? !p.next_review : Boolean(p.next_review && p.next_review <= today));
    return (!q || text.includes(q)) && domainHit && lineHit && roleHit && topicHit && methodHit && statusHit && stageHit && codeHit && importanceHit && reviewStageHit && reviewHit;
  }});
  const sorted = sortPapers(filtered);
  const size = getPageSize();
  const totalPages = size === Infinity ? 1 : Math.max(1, Math.ceil(sorted.length / size));
  currentPage = clampPage(currentPage, totalPages);
  const start = size === Infinity ? 0 : (currentPage - 1) * size;
  const end = size === Infinity ? sorted.length : Math.min(start + size, sorted.length);
  const visible = size === Infinity ? sorted : sorted.slice(start, end);
  const from = sorted.length ? start + 1 : 0;
  const to = sorted.length ? end : 0;
  resultCount.textContent = `显示 ${{from}}-${{to}} / ${{sorted.length}} 篇（总计 ${{papers.length}} 篇）`;
  cards.innerHTML = visible.length ? visible.map(card).join("") : `<div class="empty">没有匹配的论文。</div>`;
  pager.hidden = sorted.length === 0 || size === Infinity || totalPages <= 1;
  pageInfo.textContent = `第 ${{currentPage}} / ${{totalPages}} 页`;
  prevPage.disabled = currentPage <= 1;
  nextPage.disabled = currentPage >= totalPages;
  writeStateToUrl();
}}

const filterControls = [search, domain, line, role, statusWorkflow, topic, method, status, stage, code, importance, reviewStage, review, sort, pageSize];
filterControls.forEach(el => el.addEventListener("input", () => {{
  if (el === statusWorkflow) applyStatusWorkflow();
  currentPage = 1;
  render();
}}));
prevPage.addEventListener("click", () => {{
  currentPage -= 1;
  render();
}});
nextPage.addEventListener("click", () => {{
  currentPage += 1;
  render();
}});
resetFilters.addEventListener("click", () => {{
  queryControls.forEach(([key, el]) => {{
    el.value = defaultValueFor(key);
  }});
  applyStatusWorkflow();
  currentPage = 1;
  render();
}});
saveView.addEventListener("click", () => {{
  const name = window.prompt("保存当前视图为");
  if (!name || !name.trim()) return;
  const normalized = name.trim();
  const views = readSavedViews().filter(view => view.name !== normalized);
  views.unshift({{ name: normalized, state: currentState() }});
  if (!writeSavedViews(views)) return;
  refreshSavedViews();
  savedView.value = "local:0";
}});
copyCurrentLink.addEventListener("click", () => copyText(currentViewUrl(), "复制当前视图链接"));
copySharedView.addEventListener("click", () => copyJsonSnippet(sharedViewPayload("index")));
exportSavedViews.addEventListener("click", () => {{
  const views = readSavedViews();
  if (!views.length) {{
    window.alert("当前没有本地保存视图。");
    return;
  }}
  const payload = {{ page: "index", saved_views: views }};
  downloadText("index_saved_views.json", JSON.stringify(payload, null, 2) + "\\n", "application/json;charset=utf-8");
}});
importSavedViews.addEventListener("click", () => {{
  const text = window.prompt("粘贴 saved_views / shared_views JSON");
  if (!text || !text.trim()) return;
  try {{
    const incoming = normalizeSavedViews(JSON.parse(text), "index");
    if (!incoming.length) {{
      window.alert("没有找到可导入的视图。");
      return;
    }}
    const names = new Set(incoming.map(view => view.name));
    const merged = [...incoming, ...readSavedViews().filter(view => !names.has(view.name))];
    if (!writeSavedViews(merged)) return;
    refreshSavedViews();
    savedView.value = "local:0";
    window.alert(`已导入 ${{incoming.length}} 个视图。`);
  }} catch {{
    window.alert("JSON 解析失败，请检查格式。");
  }}
}});
deleteView.addEventListener("click", () => {{
  if (!savedView.value || !savedView.value.startsWith("local:")) {{
    if (savedView.value.startsWith("shared:")) window.alert("共享视图来自 taxonomy.json，不能在页面里删除。");
    return;
  }}
  const index = Number(savedView.value.split(":")[1]);
  const views = readSavedViews();
  views.splice(index, 1);
  if (!writeSavedViews(views)) return;
  refreshSavedViews();
}});
savedView.addEventListener("change", () => {{
  if (!savedView.value) return;
  const [source, indexText] = savedView.value.split(":");
  const index = Number(indexText);
  const view = source === "shared" ? sharedViews[index] : readSavedViews()[index];
  if (view) applyState(view.state || {{}});
}});
populateStatusWorkflowOptions();
readStateFromUrl();
refreshSavedViews();
render();
</script>
"""
    (report_dir / "index.html").write_text(page_shell("我的论文知识库", body, data, extra_css=index_css), encoding="utf-8")


def render_topic_options(tags: dict[str, int]) -> str:
    return "".join(
        f'<option value="{html.escape(tag)}">{html.escape(tag)} ({count})</option>'
        for tag, count in tags.items()
    )


def render_value_options(values: list[str]) -> str:
    return "".join(
        f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
        for value in values
    )


def render_datalist_options(values: dict[str, int] | list[str]) -> str:
    names = values.keys() if isinstance(values, dict) else values
    return "".join(f'<option value="{html.escape(str(value))}"></option>' for value in names)


def render_card(paper: dict[str, Any]) -> str:
    link = paper["html_path"] or paper["md_path"]
    authors = ", ".join(paper.get("authors", [])[:4])
    tags = "".join(
        f'<span class="chip">{html.escape(tag)}</span>'
        for tag in [*paper.get("domains", []), *paper.get("topics", []), *paper.get("methods", [])]
    )
    links = [f'<a class="button" href="{html.escape(link)}">阅读报告</a>']
    if paper.get("arxiv_url"):
        links.append(f'<a class="button" href="{html.escape(paper["arxiv_url"])}">arxiv</a>')
    if paper.get("code_url"):
        links.append(f'<a class="button" href="{html.escape(paper["code_url"])}">code</a>')
    title_en = f'<div class="meta">{html.escape(paper["title_en"])}</div>' if paper.get("title_en") else ""
    meta = " / ".join(str(part) for part in [paper.get("year"), authors, paper.get("arxiv_id")] if part)
    flags = [
        f'{paper["reading_time_min"]} min' if paper.get("reading_time_min") else "",
        f'重要性 {paper["importance"]}' if paper.get("importance") else "",
        f'研究线 {paper["research_line"]}' if paper.get("research_line") else "",
        f'角色 {paper["line_role"]}' if paper.get("line_role") else "",
        f'阅读 {paper["reading_stage"]}' if paper.get("reading_stage") else "",
        f'复习 {paper["review_stage"]}' if paper.get("review_stage") else "",
        f'下次 {paper["next_review"]}' if paper.get("next_review") else "",
    ]
    flag_html = "".join(f'<span class="flag">{html.escape(flag)}</span>' for flag in flags if flag)
    essence = (
        f'<p class="essence">{html.escape(paper["essence"])}</p>'
        if paper.get("essence")
        else ""
    )
    return f"""<article class="card">
  <h2><a href="{html.escape(link)}">{html.escape(paper["title_zh"] or paper["title"])}</a></h2>
  {title_en}
  <div class="meta">{html.escape(meta)}</div>
  <div class="card-flags">{flag_html}</div>
  {essence}
  <p class="excerpt">{html.escape(paper.get("excerpt") or "暂无摘要。")}</p>
  <div class="links">{''.join(links)}</div>
  <div class="chips">{tags}</div>
</article>"""


def attr_tokens(values: list[str]) -> str:
    return "|".join(values)


def render_inline_chips(values: list[str], limit: int = 4) -> str:
    shown = values[:limit]
    extra = len(values) - len(shown)
    chips = "".join(f'<span class="chip">{html.escape(value)}</span>' for value in shown)
    if extra > 0:
        chips += f'<span class="chip">+{extra}</span>'
    return chips


def render_library_row(paper: dict[str, Any]) -> str:
    link = paper["html_path"] or paper["md_path"]
    authors = ", ".join(paper.get("authors", [])[:3])
    domain_track_problem = [
        *paper.get("domains", []),
        *paper.get("tracks", []),
        *paper.get("problems", []),
    ]
    topics_methods = [*paper.get("topics", []), *paper.get("methods", [])]
    search_text = " ".join(
        str(part)
        for part in [
            paper.get("slug"),
            paper.get("title"),
            paper.get("title_zh"),
            paper.get("title_en"),
            paper.get("arxiv_id"),
            paper.get("research_line"),
            paper.get("line_role"),
            paper.get("status"),
            paper.get("reading_stage"),
            paper.get("review_stage"),
            paper.get("excerpt"),
            *paper.get("authors", []),
            *domain_track_problem,
            *topics_methods,
        ]
        if part
    ).lower()
    links = [f'<a class="button" href="{html.escape(link)}">报告</a>']
    if paper.get("arxiv_url"):
        links.append(f'<a class="button" href="{html.escape(paper["arxiv_url"])}">arxiv</a>')
    if paper.get("code_url"):
        links.append(f'<a class="button" href="{html.escape(paper["code_url"])}">code</a>')

    line_href = ""
    if paper.get("research_line") and paper.get("research_line") != "Unassigned":
        line_href = f'lines/{slugify_label(str(paper["research_line"]))}.html'
    line_html = (
        f'<a href="{html.escape(line_href)}">{html.escape(str(paper["research_line"]))}</a>'
        if line_href
        else html.escape(str(paper.get("research_line") or "Unassigned"))
    )
    next_review = str(paper.get("next_review") or "")
    review_bits = []
    if paper.get("review_stage"):
        review_bits.append(f'复习 {html.escape(str(paper["review_stage"]))}')
    if next_review:
        review_bits.append(f'下次 {html.escape(next_review)}')
    if not review_bits:
        review_bits.append("未设置复习")

    return f"""<tr
  data-search="{html.escape(search_text, quote=True)}"
  data-domains="{html.escape(attr_tokens(paper.get("domains", [])), quote=True)}"
  data-tracks="{html.escape(attr_tokens(paper.get("tracks", [])), quote=True)}"
  data-problems="{html.escape(attr_tokens(paper.get("problems", [])), quote=True)}"
  data-topics="{html.escape(attr_tokens(paper.get("topics", [])), quote=True)}"
  data-methods="{html.escape(attr_tokens(paper.get("methods", [])), quote=True)}"
  data-line="{html.escape(str(paper.get("research_line") or ""), quote=True)}"
  data-role="{html.escape(str(paper.get("line_role") or ""), quote=True)}"
  data-status="{html.escape(str(paper.get("status") or ""), quote=True)}"
  data-stage="{html.escape(str(paper.get("reading_stage") or ""), quote=True)}"
  data-review-stage="{html.escape(str(paper.get("review_stage") or ""), quote=True)}"
  data-code="{"yes" if paper.get("has_code") else "no"}"
  data-importance="{html.escape(str(paper.get("importance") or 0), quote=True)}"
  data-year="{html.escape(str(paper.get("year") or 0), quote=True)}"
  data-updated="{html.escape(str(paper.get("updated_at") or ""), quote=True)}"
  data-next-review="{html.escape(str(paper.get("next_review") or ""), quote=True)}"
  data-slug="{html.escape(str(paper.get("slug") or ""), quote=True)}"
  data-title="{html.escape(str(paper.get("title_en") or paper.get("title") or paper.get("slug") or ""), quote=True)}"
  data-title-zh="{html.escape(str(paper.get("title_zh") or ""), quote=True)}"
  data-authors="{html.escape('; '.join(str(author) for author in paper.get("authors", [])), quote=True)}"
  data-arxiv-id="{html.escape(str(paper.get("arxiv_id") or ""), quote=True)}"
  data-arxiv-url="{html.escape(str(paper.get("arxiv_url") or ""), quote=True)}"
  data-code-url="{html.escape(str(paper.get("code_url") or ""), quote=True)}"
  data-href="{html.escape(str(link), quote=True)}">
  <td data-col="select"><input class="row-check" type="checkbox" aria-label="选择 {html.escape(str(paper.get("slug") or ""), quote=True)}"></td>
  <td class="library-title" data-col="title">
    <strong><a href="{html.escape(link)}">{html.escape(paper["title_zh"] or paper["title"])}</a></strong>
    <div class="meta">{html.escape(paper.get("title_en") or "")}</div>
    <div class="meta">{html.escape(" / ".join(str(part) for part in [paper.get("year"), authors, paper.get("arxiv_id")] if part))}</div>
  </td>
  <td data-col="line">{line_html}<div class="meta">{html.escape(str(paper.get("line_role") or ""))}</div></td>
  <td class="library-taxonomy" data-col="structure"><div class="chips">{render_inline_chips(domain_track_problem, 4)}</div></td>
  <td class="library-taxonomy" data-col="tags"><div class="chips">{render_inline_chips(topics_methods, 5)}</div></td>
  <td data-col="state"><div class="status-stack"><span class="flag">{html.escape(str(paper.get("status") or "unknown"))}</span><span class="flag">{html.escape(str(paper.get("reading_stage") or "未分阶段"))}</span><span class="meta">{" · ".join(review_bits)}</span></div></td>
  <td data-col="scores"><div class="score-grid"><span>I {html.escape(str(paper.get("importance") or "-"))}</span><span>C {html.escape(str(paper.get("confidence") or "-"))}</span><span>R {html.escape(str(paper.get("reproducibility") or "-"))}</span></div></td>
  <td data-col="code">{"有" if paper.get("has_code") else "无"}</td>
  <td data-col="actions"><div class="library-actions">{"".join(links)}</div></td>
</tr>"""


def render_library(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
    rows = "\n".join(render_library_row(paper) for paper in papers)
    controls = control_options()
    data = {"shared_views": shared_views_for("library"), "controls": controls}
    bulk_css = """
    .bulk-panel {
      display: grid;
      grid-template-columns: minmax(120px, auto) repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      align-items: center;
      margin: 0 0 16px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .bulk-panel .bulk-count { color: var(--muted); font-weight: 700; white-space: nowrap; }
    .bulk-actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .bulk-taxonomy {
      grid-column: 1 / -1;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }
    .bulk-taxonomy summary {
      cursor: pointer;
      color: var(--accent);
      font-weight: 800;
    }
    .bulk-taxonomy-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .bulk-taxonomy-grid label {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .bulk-taxonomy-grid input,
    .bulk-taxonomy-grid select { width: 100%; }
    .bulk-hint {
      grid-column: 1 / -1;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.4;
    }
    .bulk-preview {
      grid-column: 1 / -1;
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--bg);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .bulk-preview strong { color: var(--text); }
    .bulk-preview code { white-space: normal; overflow-wrap: anywhere; }
    .bulk-preview-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .bulk-preview-list span {
      padding: 2px 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
    }
    .row-check, .header-check { width: 18px; min-height: 18px; padding: 0; }
    .column-panel { position: relative; }
    .column-panel summary { list-style: none; cursor: pointer; }
    .column-panel summary::-webkit-details-marker { display: none; }
    .column-menu {
      position: absolute;
      right: 0;
      top: calc(100% + 8px);
      z-index: 30;
      width: min(340px, calc(100vw - 32px));
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    .column-menu h3 { margin: 0 0 8px; font-size: 14px; }
    .column-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .column-options label, .density-control {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .density-control { margin-top: 12px; justify-content: space-between; }
    .density-control select { min-width: 128px; }
    .library-table [data-col].is-hidden-column { display: none; }
    .library-table[data-density="compact"] th,
    .library-table[data-density="compact"] td { padding: 6px 8px; font-size: 13px; }
    .library-table[data-density="compact"] .chips { gap: 4px; }
    .library-table[data-density="compact"] .flag,
    .library-table[data-density="compact"] .chip { padding: 2px 6px; }
    .library-table[data-density="comfortable"] th,
    .library-table[data-density="comfortable"] td { padding: 14px 12px; }
    .active-filters {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      margin: -4px 0 16px;
      color: var(--muted);
      font-size: 13px;
    }
    .active-filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      max-width: 280px;
      min-height: 30px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
      cursor: pointer;
    }
    .active-filter-chip span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .active-filter-chip b {
      color: var(--muted);
      font-weight: 750;
    }
    .active-filter-chip::after {
      content: "x";
      color: var(--muted);
      font-weight: 850;
    }
    .library-insights {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin: 0 0 16px;
    }
    .insight-card {
      min-height: 116px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .insight-card > span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .insight-card strong {
      display: block;
      margin-top: 4px;
      font-size: 26px;
      line-height: 1.1;
    }
    .insight-card .meta { margin-top: 6px; }
    .insight-list {
      margin: 8px 0 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 5px;
    }
    .insight-list li {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .insight-list b {
      color: var(--ink);
      font-weight: 750;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Paper Library</div>
  <h1>论文库表格</h1>
  <p class="lead">面向大量论文的密集管理视图：快速扫状态、研究线、分类覆盖、重要性和代码情况。适合批量整理与查漏补缺。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="batch.html">批次规划</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="tags.html">分类总览</a>
    <a class="stat" href="quality.json">质量 JSON</a>
    <a class="stat" href="stats.json">统计 JSON</a>
    <span class="stat">论文 {len(papers)}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="search" type="search" placeholder="搜索标题、作者、研究线、分类、状态">
    <select id="domain"><option value="">全部领域</option>{render_topic_options(taxonomy["domains"])}</select>
    <select id="track"><option value="">全部方向</option>{render_topic_options(taxonomy["tracks"])}</select>
    <select id="problem"><option value="">全部问题</option>{render_topic_options(taxonomy["problems"])}</select>
    <select id="topic"><option value="">全部主题</option>{render_topic_options(taxonomy["topics"])}</select>
    <select id="method"><option value="">全部方法</option>{render_topic_options(taxonomy["methods"])}</select>
    <select id="line"><option value="">全部研究线</option>{render_topic_options(taxonomy["research_lines"])}</select>
    <select id="role"><option value="">全部角色</option>{render_topic_options(taxonomy["line_roles"])}</select>
    <select id="statusWorkflow" aria-label="状态体系"></select>
    <select id="status"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="stage"><option value="">阅读阶段</option>{render_topic_options(taxonomy["reading_stages"])}</select>
    <select id="reviewStage"><option value="">复习阶段</option>{render_topic_options(taxonomy["review_stages"])}</select>
    <select id="review"><option value="">复习队列</option><option value="due">到期复习</option><option value="none">未设置复习</option><option value="planned">已设置复习</option></select>
    <select id="code"><option value="">代码状态</option><option value="yes">有代码</option><option value="no">无代码</option></select>
    <select id="importance"><option value="">重要性</option><option value="5">5 星</option><option value="4">4 星及以上</option><option value="3">3 星及以上</option></select>
    <select id="sort"><option value="default">默认排序</option><option value="importance">重要性优先</option><option value="updated">最近更新</option><option value="year">年份新到旧</option><option value="title">标题 A-Z</option></select>
    <select id="pageSize"><option value="50">每页 50 篇</option><option value="100">每页 100 篇</option><option value="200">每页 200 篇</option><option value="all">显示全部</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="resultCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <div class="results-actions">
      <select id="savedView" class="saved-view" aria-label="选择保存视图"><option value="">选择视图</option></select>
      <button id="saveView" class="button" type="button">保存视图</button>
      <button id="copyCurrentLink" class="button" type="button">复制当前链接</button>
      <button id="copySharedView" class="button" type="button">复制共享视图</button>
      <button id="deleteView" class="button" type="button">删除视图</button>
      <button id="exportSavedViews" class="button" type="button">导出视图</button>
      <button id="importSavedViews" class="button" type="button">导入视图</button>
      <details class="column-panel">
        <summary class="button">列设置</summary>
        <div class="column-menu" id="columnMenu">
          <h3>显示列</h3>
          <div class="column-options">
            <label><input type="checkbox" data-column-toggle="title" checked disabled>论文</label>
            <label><input type="checkbox" data-column-toggle="line" checked>研究线</label>
            <label><input type="checkbox" data-column-toggle="structure" checked>结构分类</label>
            <label><input type="checkbox" data-column-toggle="tags" checked>主题 / 方法</label>
            <label><input type="checkbox" data-column-toggle="state" checked>状态</label>
            <label><input type="checkbox" data-column-toggle="scores" checked>评分</label>
            <label><input type="checkbox" data-column-toggle="code" checked>代码</label>
            <label><input type="checkbox" data-column-toggle="actions" checked>操作</label>
          </div>
          <label class="density-control"><span>表格密度</span><select id="densityMode"><option value="compact">紧凑</option><option value="normal">标准</option><option value="comfortable">舒适</option></select></label>
        </div>
      </details>
      <button id="exportMarkdown" class="button" type="button">导出清单</button>
      <button id="exportCsv" class="button" type="button">导出 CSV</button>
      <button id="exportBibtex" class="button" type="button">导出 BibTeX</button>
      <button id="resetFilters" class="button" type="button">重置筛选</button>
    </div>
  </div>
  <div class="active-filters" id="activeFilters" aria-live="polite"></div>
  <div class="bulk-panel">
    <span id="bulkCount" class="bulk-count">已选 0 篇</span>
    <select id="bulkStatus"><option value="">状态</option>{render_value_options(controls["status"])}</select>
    <select id="bulkStage"><option value="">阅读阶段</option>{render_value_options(controls["reading_stage"])}</select>
    <select id="bulkReviewStage"><option value="">复习阶段</option>{render_value_options(controls["review_stage"])}</select>
    <input id="bulkNextReview" type="date" aria-label="下次复习日期">
    <select id="bulkImportance"><option value="">重要性</option><option value="5">5</option><option value="4">4</option><option value="3">3</option><option value="2">2</option><option value="1">1</option></select>
    <div class="bulk-actions">
      <button id="selectVisible" class="button" type="button">选中当前页</button>
      <button id="selectFiltered" class="button" type="button">选中筛选结果</button>
      <button id="clearSelected" class="button" type="button">清除选择</button>
      <button id="copySelectedMarkdown" class="button" type="button">复制选中清单</button>
      <button id="copySelectedSlugs" class="button" type="button">复制 Slugs</button>
      <button id="previewPatch" class="button" type="button">预览 Patch</button>
      <button id="downloadPatch" class="button" type="button">下载 CSV</button>
      <button id="copyPatchDryRun" class="button" type="button">复制预览命令</button>
      <button id="copyPatchWrite" class="button" type="button">复制写入命令</button>
    </div>
    <details class="bulk-taxonomy">
      <summary>批量分类字段</summary>
      <div class="bulk-taxonomy-grid">
        <label><span>分类写入方式</span><select id="bulkListMode"><option value="replace">替换原分类</option><option value="append">追加到原分类</option><option value="remove">从原分类移除</option></select></label>
        <label><span>研究线</span><input id="bulkResearchLine" list="researchLineOptions" type="text" placeholder="Research line"></label>
        <label><span>研究线角色</span><select id="bulkLineRole"><option value="">角色</option>{render_value_options(controls["line_role"])}</select></label>
        <label><span>Domain</span><input id="bulkDomains" list="domainOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Track</span><input id="bulkTracks" list="trackOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Problem</span><input id="bulkProblems" list="problemOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Topics</span><input id="bulkTopics" list="topicOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Methods</span><input id="bulkMethods" list="methodOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <div class="bulk-hint">分类写入方式只影响 domains / tracks / problems / topics / methods；状态、日期、重要性和研究线字段仍按输入值写入。下载后先 dry-run，再用 --write 写回。</div>
      </div>
    </details>
    <div id="bulkPreview" class="bulk-preview" aria-live="polite">选择论文和字段后显示 patch 摘要。</div>
  </div>
  <section class="library-insights" id="libraryInsights" aria-live="polite">
    <div class="insight-card">
      <span>当前队列</span>
      <strong id="insightTotal">0</strong>
      <div class="meta" id="insightCoverage">-</div>
    </div>
    <div class="insight-card">
      <span>Status 分布</span>
      <ul class="insight-list" id="insightStatuses"></ul>
    </div>
    <div class="insight-card">
      <span>研究线分布</span>
      <ul class="insight-list" id="insightLines"></ul>
    </div>
    <div class="insight-card">
      <span>Topic 热点</span>
      <ul class="insight-list" id="insightTopics"></ul>
    </div>
    <div class="insight-card">
      <span>Method 热点</span>
      <ul class="insight-list" id="insightMethods"></ul>
    </div>
    <div class="insight-card">
      <span>覆盖与优先级</span>
      <strong id="insightReviewGap">0</strong>
      <div class="meta" id="insightPriority">-</div>
    </div>
  </section>
  <datalist id="researchLineOptions">{render_datalist_options(taxonomy["research_lines"])}</datalist>
  <datalist id="domainOptions">{render_datalist_options(taxonomy["domains"])}</datalist>
  <datalist id="trackOptions">{render_datalist_options(taxonomy["tracks"])}</datalist>
  <datalist id="problemOptions">{render_datalist_options(taxonomy["problems"])}</datalist>
  <datalist id="topicOptions">{render_datalist_options(taxonomy["topics"])}</datalist>
  <datalist id="methodOptions">{render_datalist_options(taxonomy["methods"])}</datalist>
  <div class="table-wrap">
    <table class="library-table" data-density="normal">
      <thead>
        <tr><th data-col="select"><input id="toggleVisible" class="header-check" type="checkbox" aria-label="切换当前页选择"></th><th data-col="title">论文</th><th data-col="line">研究线</th><th data-col="structure">结构分类</th><th data-col="tags">主题 / 方法</th><th data-col="state">状态</th><th data-col="scores">评分</th><th data-col="code">代码</th><th data-col="actions">操作</th></tr>
      </thead>
      <tbody id="libraryRows">{rows}</tbody>
    </table>
  </div>
  <nav id="pager" class="pager" aria-label="分页">
    <button id="prevPage" class="button" type="button">上一页</button>
    <span id="pageInfo">第 1 / 1 页</span>
    <button id="nextPage" class="button" type="button">下一页</button>
  </nav>
</main>
<script>
const tbody = document.querySelector("#libraryRows");
const allRows = Array.from(tbody.querySelectorAll("tr"));
const search = document.querySelector("#search");
const domain = document.querySelector("#domain");
const track = document.querySelector("#track");
const problem = document.querySelector("#problem");
const topic = document.querySelector("#topic");
const method = document.querySelector("#method");
const line = document.querySelector("#line");
const role = document.querySelector("#role");
const statusWorkflow = document.querySelector("#statusWorkflow");
const status = document.querySelector("#status");
const stage = document.querySelector("#stage");
const reviewStage = document.querySelector("#reviewStage");
const review = document.querySelector("#review");
const code = document.querySelector("#code");
const importance = document.querySelector("#importance");
const sort = document.querySelector("#sort");
const pageSize = document.querySelector("#pageSize");
const resultCount = document.querySelector("#resultCount");
const resetFilters = document.querySelector("#resetFilters");
const pager = document.querySelector("#pager");
const pageInfo = document.querySelector("#pageInfo");
const prevPage = document.querySelector("#prevPage");
const nextPage = document.querySelector("#nextPage");
const savedView = document.querySelector("#savedView");
const saveView = document.querySelector("#saveView");
const copyCurrentLink = document.querySelector("#copyCurrentLink");
const copySharedView = document.querySelector("#copySharedView");
const deleteView = document.querySelector("#deleteView");
const exportSavedViews = document.querySelector("#exportSavedViews");
const importSavedViews = document.querySelector("#importSavedViews");
const activeFilters = document.querySelector("#activeFilters");
const exportMarkdown = document.querySelector("#exportMarkdown");
const exportCsv = document.querySelector("#exportCsv");
const exportBibtex = document.querySelector("#exportBibtex");
const rowChecks = allRows.map(row => row.querySelector(".row-check"));
const toggleVisible = document.querySelector("#toggleVisible");
const bulkCount = document.querySelector("#bulkCount");
const bulkStatus = document.querySelector("#bulkStatus");
const bulkStage = document.querySelector("#bulkStage");
const bulkReviewStage = document.querySelector("#bulkReviewStage");
const bulkNextReview = document.querySelector("#bulkNextReview");
const bulkImportance = document.querySelector("#bulkImportance");
const bulkListMode = document.querySelector("#bulkListMode");
const bulkResearchLine = document.querySelector("#bulkResearchLine");
const bulkLineRole = document.querySelector("#bulkLineRole");
const bulkDomains = document.querySelector("#bulkDomains");
const bulkTracks = document.querySelector("#bulkTracks");
const bulkProblems = document.querySelector("#bulkProblems");
const bulkTopics = document.querySelector("#bulkTopics");
const bulkMethods = document.querySelector("#bulkMethods");
const selectVisible = document.querySelector("#selectVisible");
const selectFiltered = document.querySelector("#selectFiltered");
const clearSelected = document.querySelector("#clearSelected");
const previewPatch = document.querySelector("#previewPatch");
const downloadPatch = document.querySelector("#downloadPatch");
const copySelectedMarkdown = document.querySelector("#copySelectedMarkdown");
const copySelectedSlugs = document.querySelector("#copySelectedSlugs");
const copyPatchDryRun = document.querySelector("#copyPatchDryRun");
const copyPatchWrite = document.querySelector("#copyPatchWrite");
const bulkPreview = document.querySelector("#bulkPreview");
const libraryTable = document.querySelector(".library-table");
const insightTotal = document.querySelector("#insightTotal");
const insightCoverage = document.querySelector("#insightCoverage");
const insightStatuses = document.querySelector("#insightStatuses");
const insightLines = document.querySelector("#insightLines");
const insightTopics = document.querySelector("#insightTopics");
const insightMethods = document.querySelector("#insightMethods");
const insightReviewGap = document.querySelector("#insightReviewGap");
const insightPriority = document.querySelector("#insightPriority");
const columnToggles = Array.from(document.querySelectorAll("[data-column-toggle]"));
const densityMode = document.querySelector("#densityMode");
const sharedViews = window.PAPER_WIKI.shared_views || [];
const wikiControls = window.PAPER_WIKI.controls || {{}};
const statusWorkflows = wikiControls.status_workflows || {{}};
const listPatchFields = new Set(["domains", "tracks", "problems", "topics", "methods"]);
const activeStatusWorkflow = wikiControls.active_status_workflow || Object.keys(statusWorkflows)[0] || "default";
const fallbackStatusValues = Array.isArray(wikiControls.status) ? wikiControls.status : [];
const fallbackStageValues = Array.isArray(wikiControls.reading_stage) ? wikiControls.reading_stage : [];
const fallbackReviewStageValues = Array.isArray(wikiControls.review_stage) ? wikiControls.review_stage : [];
const observedStatusValues = Array.from(new Set(allRows.map(row => row.dataset.status).filter(Boolean)));
const observedStageValues = Array.from(new Set(allRows.map(row => row.dataset.stage).filter(Boolean)));
const observedReviewStageValues = Array.from(new Set(allRows.map(row => row.dataset.reviewStage).filter(Boolean)));
let currentPage = 1;
let currentRankedRows = [...allRows];
const savedViewsKey = "autopaperreader:library:savedViews";
const libraryPrefsKey = "autopaperreader:library:prefs";
const controls = [
  ["q", search],
  ["domain", domain],
  ["track", track],
  ["problem", problem],
  ["topic", topic],
  ["method", method],
  ["line", line],
  ["role", role],
  ["workflow", statusWorkflow],
  ["status", status],
  ["stage", stage],
  ["reviewStage", reviewStage],
  ["review", review],
  ["code", code],
  ["importance", importance],
  ["sort", sort],
  ["size", pageSize],
];
const controlsByKey = new Map(controls);
const activeFilterLabels = {{
  q: "搜索",
  domain: "领域",
  track: "方向",
  problem: "问题",
  topic: "主题",
  method: "方法",
  line: "研究线",
  role: "角色",
  workflow: "状态体系",
  status: "状态",
  stage: "阅读阶段",
  reviewStage: "复习阶段",
  review: "复习队列",
  code: "代码",
  importance: "重要性",
}};
const hiddenActiveFilterKeys = new Set(["sort", "size"]);

function tokens(value) {{
  return String(value || "").split("|").filter(Boolean);
}}

function hasToken(row, key, value) {{
  return !value || tokens(row.dataset[key]).includes(value);
}}

function orderedUnique(values) {{
  return Array.from(new Set(values.map(value => String(value || "").trim()).filter(Boolean)));
}}

function statusValuesForWorkflow(name) {{
  return workflowValuesFor(name, "status_values", fallbackStatusValues, observedStatusValues);
}}

function workflowValuesFor(name, key, fallbackValues, observedValues) {{
  const workflow = statusWorkflows[name] || {{}};
  const configured = Array.isArray(workflow[key]) ? workflow[key] : fallbackValues;
  return orderedUnique([...configured, ...observedValues]);
}}

function valueCount(datasetKey, value) {{
  return allRows.filter(row => row.dataset[datasetKey] === value).length;
}}

function replaceWorkflowOptions(select, placeholder, values, datasetKey, withCounts = false) {{
  const current = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  values.forEach(value => {{
    const label = withCounts ? `${{value}} (${{valueCount(datasetKey, value)}})` : value;
    select.appendChild(new Option(label, value));
  }});
  select.value = values.includes(current) ? current : "";
}}

function populateStatusWorkflowOptions() {{
  const names = Object.keys(statusWorkflows);
  const workflowNames = names.length ? names : [activeStatusWorkflow];
  statusWorkflow.replaceChildren(...workflowNames.map(name => {{
    const label = name === activeStatusWorkflow ? `${{name}} (默认)` : name;
    return new Option(label, name);
  }}));
  statusWorkflow.value = workflowNames.includes(activeStatusWorkflow) ? activeStatusWorkflow : workflowNames[0] || "";
}}

function applyStatusWorkflow() {{
  const workflowName = statusWorkflow.value;
  const statusValues = statusValuesForWorkflow(workflowName);
  const stageValues = workflowValuesFor(workflowName, "reading_stage_values", fallbackStageValues, observedStageValues);
  const reviewStageValues = workflowValuesFor(workflowName, "review_stage_values", fallbackReviewStageValues, observedReviewStageValues);
  replaceWorkflowOptions(status, "全部状态", statusValues, "status", true);
  replaceWorkflowOptions(bulkStatus, "状态", statusValues, "status", false);
  replaceWorkflowOptions(stage, "阅读阶段", stageValues, "stage", true);
  replaceWorkflowOptions(bulkStage, "阅读阶段", stageValues, "stage", false);
  replaceWorkflowOptions(reviewStage, "复习阶段", reviewStageValues, "reviewStage", true);
  replaceWorkflowOptions(bulkReviewStage, "复习阶段", reviewStageValues, "reviewStage", false);
}}

function pageLimit() {{
  return pageSize.value === "all" ? Infinity : Number(pageSize.value || 50);
}}

function defaultValueFor(key) {{
  return key === "workflow" ? activeStatusWorkflow : key === "sort" ? "default" : key === "size" ? "50" : "";
}}

function currentState() {{
  const state = {{}};
  controls.forEach(([key, el]) => {{
    const defaultValue = defaultValueFor(key);
    if (el.value && el.value !== defaultValue) state[key] = el.value;
  }});
  if (currentPage > 1) state.page = String(currentPage);
  return state;
}}

function cleanOptionLabel(label) {{
  return String(label || "").replace(/\\s\\(\\d+\\)$/, "");
}}

function controlDisplayValue(key, el) {{
  if (key === "q") return el.value;
  const option = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
  return cleanOptionLabel(option ? option.textContent : el.value);
}}

function renderActiveFilters() {{
  const state = currentState();
  const entries = Object.entries(state)
    .filter(([key]) => controlsByKey.has(key) && !hiddenActiveFilterKeys.has(key));
  activeFilters.replaceChildren();
  if (!entries.length) {{
    activeFilters.textContent = "未设置筛选条件";
    return;
  }}
  const label = document.createElement("span");
  label.textContent = "当前筛选";
  activeFilters.appendChild(label);
  entries.forEach(([key]) => {{
    const el = controlsByKey.get(key);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "active-filter-chip";
    button.dataset.filterKey = key;
    button.title = `移除${{activeFilterLabels[key] || key}}筛选`;
    const name = document.createElement("b");
    name.textContent = activeFilterLabels[key] || key;
    const value = document.createElement("span");
    value.textContent = controlDisplayValue(key, el);
    button.append(name, value);
    activeFilters.appendChild(button);
  }});
}}

function clearActiveFilter(key) {{
  const el = controlsByKey.get(key);
  if (!el) return;
  el.value = defaultValueFor(key);
  if (key === "workflow") applyStatusWorkflow();
  currentPage = 1;
  render();
}}

function applyState(state) {{
  controls.forEach(([key, el]) => {{
    if (["status", "stage", "reviewStage"].includes(key)) return;
    el.value = state[key] || defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = state.status || defaultValueFor("status");
  stage.value = state.stage || defaultValueFor("stage");
  reviewStage.value = state.reviewStage || defaultValueFor("reviewStage");
  currentPage = Number(state.page || 1) || 1;
  render();
}}

function readStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  controls.forEach(([key, el]) => {{
    if (["status", "stage", "reviewStage"].includes(key)) return;
    el.value = params.has(key) ? params.get(key) : defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = params.has("status") ? params.get("status") : defaultValueFor("status");
  stage.value = params.has("stage") ? params.get("stage") : defaultValueFor("stage");
  reviewStage.value = params.has("reviewStage") ? params.get("reviewStage") : defaultValueFor("reviewStage");
  currentPage = Number(params.get("page") || 1) || 1;
}}

function writeStateToUrl() {{
  const params = new URLSearchParams(currentState());
  const query = params.toString();
  window.history.replaceState(null, "", query ? `${{location.pathname}}?${{query}}` : location.pathname);
}}

function currentViewUrl() {{
  const params = new URLSearchParams(currentState());
  const url = new URL(window.location.href);
  url.search = params.toString();
  url.hash = "";
  return url.toString();
}}

function readSavedViews() {{
  try {{
    const views = JSON.parse(localStorage.getItem(savedViewsKey) || "[]");
    return Array.isArray(views) ? views.filter(view => view && view.name && view.state) : [];
  }} catch {{
    return [];
  }}
}}

function writeSavedViews(views) {{
  try {{
    localStorage.setItem(savedViewsKey, JSON.stringify(views.slice(0, 50)));
    return true;
  }} catch {{
    window.alert("浏览器本地存储不可用，无法保存视图。");
    return false;
  }}
}}

function normalizeSavedViews(payload, pageName) {{
  const candidates = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.saved_views)
      ? payload.saved_views
      : Array.isArray(payload?.shared_views)
        ? payload.shared_views
        : payload?.name && payload?.state
          ? [payload]
          : [];
  const allowedKeys = new Set([...controls.map(([key]) => key), "page"]);
  const pageScope = new Set(["all", pageName, ""]);
  return candidates.map(view => {{
    const page = String(view?.page || "").trim();
    if (!pageScope.has(page)) return null;
    const name = String(view?.name || "").trim();
    const rawState = view?.state && typeof view.state === "object" && !Array.isArray(view.state) ? view.state : {{}};
    const state = Object.fromEntries(Object.entries(rawState)
      .filter(([key, value]) => allowedKeys.has(key) && value !== null && typeof value !== "object")
      .map(([key, value]) => [key, String(value)]));
    return name ? {{ name, state }} : null;
  }}).filter(Boolean);
}}

function sharedViewPayload(page) {{
  const name = window.prompt("共享视图名称");
  if (!name || !name.trim()) return null;
  const state = {{ ...currentState() }};
  delete state.page;
  if (!Object.keys(state).length) {{
    window.alert("当前没有可共享的筛选条件。");
    return null;
  }}
  return {{ name: name.trim(), page, state }};
}}

async function copyJsonSnippet(payload) {{
  if (!payload) return;
  const text = JSON.stringify(payload, null, 2);
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制 shared view JSON。");
  }} catch {{
    window.prompt("复制 shared view JSON", text);
  }}
}}

function defaultLibraryPrefs() {{
  return {{
    density: "normal",
    columns: Object.fromEntries(columnToggles.map(toggle => [toggle.dataset.columnToggle, true])),
  }};
}}

function readLibraryPrefs() {{
  const defaults = defaultLibraryPrefs();
  try {{
    const stored = JSON.parse(localStorage.getItem(libraryPrefsKey) || "{{}}");
    return {{
      density: ["compact", "normal", "comfortable"].includes(stored.density) ? stored.density : defaults.density,
      columns: {{ ...defaults.columns, ...(stored.columns || {{}}), title: true }},
    }};
  }} catch {{
    return defaults;
  }}
}}

function writeLibraryPrefs(prefs) {{
  try {{
    localStorage.setItem(libraryPrefsKey, JSON.stringify(prefs));
  }} catch {{
    // Preference persistence is optional; the table should still work without localStorage.
  }}
}}

function collectLibraryPrefs() {{
  return {{
    density: densityMode.value || "normal",
    columns: Object.fromEntries(columnToggles.map(toggle => [
      toggle.dataset.columnToggle,
      toggle.disabled ? true : toggle.checked,
    ])),
  }};
}}

function applyLibraryPrefs(prefs) {{
  const density = ["compact", "normal", "comfortable"].includes(prefs.density) ? prefs.density : "normal";
  densityMode.value = density;
  libraryTable.dataset.density = density;
  columnToggles.forEach(toggle => {{
    const key = toggle.dataset.columnToggle;
    toggle.checked = toggle.disabled || prefs.columns[key] !== false;
  }});
  document.querySelectorAll("[data-col]").forEach(cell => {{
    const key = cell.dataset.col;
    const alwaysVisible = key === "select" || key === "title";
    cell.classList.toggle("is-hidden-column", !alwaysVisible && prefs.columns[key] === false);
  }});
}}

function refreshSavedViews() {{
  const views = readSavedViews();
  savedView.replaceChildren(new Option("选择视图", ""));
  if (sharedViews.length) {{
    const sharedGroup = document.createElement("optgroup");
    sharedGroup.label = "共享视图";
    sharedViews.forEach((view, index) => sharedGroup.appendChild(new Option(view.name, `shared:${{index}}`)));
    savedView.appendChild(sharedGroup);
  }}
  if (views.length) {{
    const localGroup = document.createElement("optgroup");
    localGroup.label = "本地视图";
    views.forEach((view, index) => localGroup.appendChild(new Option(view.name, `local:${{index}}`)));
    savedView.appendChild(localGroup);
  }}
}}

function sortRows(rows) {{
  const mode = sort.value;
  return [...rows].sort((a, b) => {{
    if (mode === "importance") {{
      return Number(b.dataset.importance || 0) - Number(a.dataset.importance || 0)
        || Number(b.dataset.year || 0) - Number(a.dataset.year || 0)
        || a.dataset.title.localeCompare(b.dataset.title);
    }}
    if (mode === "updated") return String(b.dataset.updated || "").localeCompare(String(a.dataset.updated || "")) || a.dataset.title.localeCompare(b.dataset.title);
    if (mode === "year") return Number(b.dataset.year || 0) - Number(a.dataset.year || 0) || a.dataset.title.localeCompare(b.dataset.title);
    if (mode === "title") return a.dataset.title.localeCompare(b.dataset.title);
    return Number(b.dataset.year || 0) - Number(a.dataset.year || 0)
      || String(b.dataset.updated || "").localeCompare(String(a.dataset.updated || ""))
      || a.dataset.title.localeCompare(b.dataset.title);
  }});
}}

function visibleRows() {{
  return allRows.filter(row => !row.hidden);
}}

function selectedRows() {{
  return allRows.filter(row => row.querySelector(".row-check").checked);
}}

function matchesReviewQueue(row, value, today = localDateString()) {{
  if (!value) return true;
  const nextReview = row.dataset.nextReview || "";
  if (value === "none") return !nextReview;
  if (value === "planned") return Boolean(nextReview);
  if (value === "due") return Boolean(nextReview && nextReview <= today);
  return true;
}}

function percentLabel(count, total) {{
  return total ? `${{Math.round((count / total) * 100)}}%` : "0%";
}}

function localDateString(date = new Date()) {{
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}}

function countBy(rows, getter) {{
  const counts = new Map();
  rows.forEach(row => {{
    const value = String(getter(row) || "").trim() || "未设置";
    counts.set(value, (counts.get(value) || 0) + 1);
  }});
  return Array.from(counts.entries()).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
}}

function countTokens(rows, key) {{
  const counts = new Map();
  rows.forEach(row => {{
    tokens(row.dataset[key]).forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
  }});
  return Array.from(counts.entries()).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
}}

function renderInsightList(list, entries, total, emptyLabel = "无结果") {{
  list.replaceChildren();
  if (!entries.length) {{
    const item = document.createElement("li");
    const label = document.createElement("b");
    label.textContent = emptyLabel;
    const count = document.createElement("span");
    count.textContent = "0";
    item.append(label, count);
    list.appendChild(item);
    return;
  }}
  entries.slice(0, 5).forEach(([name, count]) => {{
    const item = document.createElement("li");
    const label = document.createElement("b");
    label.textContent = name;
    const value = document.createElement("span");
    value.textContent = `${{count}} · ${{percentLabel(count, total)}}`;
    item.append(label, value);
    list.appendChild(item);
  }});
}}

function updateLibraryInsights(rows) {{
  const total = rows.length;
  const codeCount = rows.filter(row => row.dataset.code === "yes").length;
  const missingReview = rows.filter(row => !row.dataset.nextReview).length;
  const missingTaxonomy = rows.filter(row => !row.dataset.domains || !row.dataset.topics || !row.dataset.methods).length;
  const today = localDateString();
  const dueReview = rows.filter(row => row.dataset.nextReview && row.dataset.nextReview <= today).length;
  const importanceValues = rows
    .map(row => Number(row.dataset.importance || 0))
    .filter(value => Number.isFinite(value) && value > 0);
  const averageImportance = importanceValues.length
    ? (importanceValues.reduce((sum, value) => sum + value, 0) / importanceValues.length).toFixed(1)
    : "-";
  insightTotal.textContent = String(total);
  insightCoverage.textContent = `${{codeCount}}/${{total}} 有代码 · ${{percentLabel(codeCount, total)}} 覆盖`;
  insightReviewGap.textContent = String(missingTaxonomy);
  insightPriority.textContent = `缺 taxonomy · 缺复习 ${{missingReview}} · 到期 ${{dueReview}} · 平均重要性 ${{averageImportance}}`;
  renderInsightList(insightStatuses, countBy(rows, row => row.dataset.status), total);
  renderInsightList(insightLines, countBy(rows, row => row.dataset.line), total);
  renderInsightList(insightTopics, countTokens(rows, "topics"), total, "未设置 topic");
  renderInsightList(insightMethods, countTokens(rows, "methods"), total, "未设置 method");
}}

function updateBulkState() {{
  const selected = selectedRows().length;
  const visible = visibleRows();
  const visibleSelected = visible.filter(row => row.querySelector(".row-check").checked).length;
  bulkCount.textContent = `已选 ${{selected}} 篇`;
  toggleVisible.checked = visible.length > 0 && visibleSelected === visible.length;
  toggleVisible.indeterminate = visibleSelected > 0 && visibleSelected < visible.length;
  copySelectedMarkdown.disabled = selected === 0;
  copySelectedSlugs.disabled = selected === 0;
  updateBulkPreview();
}}

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function downloadCsv(filename, rows) {{
  const csv = rows.map(row => row.map(csvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function downloadText(filename, text, type = "text/plain;charset=utf-8") {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function mdEscape(value) {{
  return String(value ?? "").replace(/[\\[\\]()`]/g, "\\\\$&");
}}

function bibtexEscape(value) {{
  return String(value ?? "").replaceAll("\\\\", "\\\\\\\\").replaceAll("{{", "\\\\{{").replaceAll("}}", "\\\\}}");
}}

function bibtexKey(row) {{
  const firstAuthor = String(row.dataset.authors || "paper").split(";")[0].trim().split(/\\s+/).pop() || "paper";
  const author = firstAuthor.toLowerCase().replace(/[^a-z0-9]+/g, "") || "paper";
  const year = row.dataset.year && row.dataset.year !== "0" ? row.dataset.year : "nd";
  const slug = String(row.dataset.slug || "paper").toLowerCase().replace(/[^a-z0-9]+/g, "").slice(0, 24);
  return `${{author}}${{year}}${{slug}}`;
}}

function rowUrl(row) {{
  return row.dataset.arxivUrl || row.dataset.href || "";
}}

function tokenCsvValue(row, key) {{
  return tokens(row.dataset[key]).join("; ");
}}

function exportRows(format) {{
  if (!currentRankedRows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  if (format === "markdown") {{
    const lines = ["# Reading List", ""];
    currentRankedRows.forEach(row => {{
      const title = row.dataset.title || row.dataset.slug;
      const titleZh = row.dataset.titleZh || "";
      const url = rowUrl(row);
      const label = url ? `[${{mdEscape(title)}}](${{url}})` : mdEscape(title);
      const meta = [row.dataset.year !== "0" ? row.dataset.year : "", row.dataset.line, row.dataset.status, row.dataset.importance !== "0" ? `I${{row.dataset.importance}}` : ""].filter(Boolean).join(" · ");
      lines.push(`- ${{label}}`);
      if (titleZh && titleZh !== title) lines.push(`  - 中文：${{titleZh}}`);
      if (meta) lines.push(`  - 元数据：${{meta}}`);
      if (row.dataset.codeUrl) lines.push(`  - 代码：${{row.dataset.codeUrl}}`);
    }});
    lines.push("");
    downloadText("reading_list.md", lines.join("\\n"), "text/markdown;charset=utf-8");
    return;
  }}
  if (format === "csv") {{
    const header = [
      "slug",
      "title",
      "title_zh",
      "year",
      "authors",
      "arxiv_id",
      "research_line",
      "line_role",
      "domains",
      "tracks",
      "problems",
      "topics",
      "methods",
      "status",
      "reading_stage",
      "review_stage",
      "importance",
      "has_code",
      "arxiv_url",
      "code_url",
      "report",
    ];
    const rows = currentRankedRows.map(row => [
      row.dataset.slug,
      row.dataset.title,
      row.dataset.titleZh,
      row.dataset.year !== "0" ? row.dataset.year : "",
      row.dataset.authors,
      row.dataset.arxivId,
      row.dataset.line,
      row.dataset.role,
      tokenCsvValue(row, "domains"),
      tokenCsvValue(row, "tracks"),
      tokenCsvValue(row, "problems"),
      tokenCsvValue(row, "topics"),
      tokenCsvValue(row, "methods"),
      row.dataset.status,
      row.dataset.stage,
      row.dataset.reviewStage,
      row.dataset.importance !== "0" ? row.dataset.importance : "",
      row.dataset.code,
      row.dataset.arxivUrl,
      row.dataset.codeUrl,
      row.dataset.href,
    ]);
    downloadCsv("library_filtered.csv", [header, ...rows]);
    return;
  }}
  const entries = currentRankedRows.map(row => {{
    const fields = [
      ["title", row.dataset.title || row.dataset.slug],
      ["author", String(row.dataset.authors || "").split(";").map(author => author.trim()).filter(Boolean).join(" and ")],
      ["year", row.dataset.year !== "0" ? row.dataset.year : ""],
      ["url", rowUrl(row)],
      ["note", row.dataset.arxivId],
    ].filter(([, value]) => value);
    const body = fields.map(([name, value]) => `  ${{name}} = {{${{bibtexEscape(value)}}}},`).join("\\n");
    return `@misc{{${{bibtexKey(row)}},\\n${{body}}\\n}}`;
  }});
  downloadText("library.bib", entries.join("\\n\\n") + "\\n", "application/x-bibtex;charset=utf-8");
}}

function selectedMarkdown(rows) {{
  const lines = ["# Selected Papers", ""];
  rows.forEach(row => {{
    const title = row.dataset.title || row.dataset.slug;
    const report = row.dataset.href || "";
    const label = report ? `[${{mdEscape(title)}}](${{report}})` : mdEscape(title);
    const meta = [
      row.dataset.year !== "0" ? row.dataset.year : "",
      row.dataset.line,
      row.dataset.status,
      row.dataset.stage,
      row.dataset.importance !== "0" ? `I${{row.dataset.importance}}` : "",
    ].filter(Boolean).join(" · ");
    lines.push(`- ${{label}}`);
    if (row.dataset.titleZh && row.dataset.titleZh !== title) lines.push(`  - 中文：${{row.dataset.titleZh}}`);
    if (meta) lines.push(`  - 元数据：${{meta}}`);
    if (row.dataset.arxivUrl) lines.push(`  - arXiv：${{row.dataset.arxivUrl}}`);
    if (row.dataset.codeUrl) lines.push(`  - 代码：${{row.dataset.codeUrl}}`);
  }});
  lines.push("");
  return lines.join("\\n");
}}

function copySelectedRows(format) {{
  const rows = selectedRows();
  if (!rows.length) {{
    window.alert("请先选择论文。");
    return;
  }}
  const text = format === "slugs"
    ? rows.map(row => row.dataset.slug).join("\\n") + "\\n"
    : selectedMarkdown(rows);
  copyText(text, format === "slugs" ? "复制选中 Slugs" : "复制选中清单");
}}

function patchCommand(write = false) {{
  const mode = bulkListMode.value || "replace";
  const modeArg = mode !== "replace" ? ` --list-mode ${{mode}}` : "";
  return `python3 scripts/apply_library_metadata.py docs --input ~/Downloads/metadata_patch.csv${{modeArg}}${{write ? " --write" : ""}}`;
}}

async function copyText(text, fallbackLabel) {{
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt(fallbackLabel, text);
  }}
}}

function patchFieldValues() {{
  const fields = [];
  const values = {{}};
  [
    ["status", bulkStatus.value],
    ["reading_stage", bulkStage.value],
    ["review_stage", bulkReviewStage.value],
    ["next_review", bulkNextReview.value],
    ["importance", bulkImportance.value],
    ["research_line", bulkResearchLine.value],
    ["line_role", bulkLineRole.value],
    ["domains", bulkDomains.value],
    ["tracks", bulkTracks.value],
    ["problems", bulkProblems.value],
    ["topics", bulkTopics.value],
    ["methods", bulkMethods.value],
  ].forEach(([field, value]) => {{
    if (String(value || "").trim()) {{
      fields.push(field);
      values[field] = String(value).trim();
    }}
  }});
  return {{ fields, values }};
}}

function buildPatchSpec(showAlerts = false) {{
  const {{ fields, values }} = patchFieldValues();
  const selected = selectedRows();
  const listMode = bulkListMode.value || "replace";
  const includeListMode = listMode !== "replace" && fields.some(field => listPatchFields.has(field));
  if (!selected.length) {{
    if (showAlerts) window.alert("请先选择论文。");
    return null;
  }}
  if (!fields.length) {{
    if (showAlerts) window.alert("请先选择要写入的状态、日期或分类字段。");
    return null;
  }}
  return {{
    fields,
    values,
    listMode,
    includeListMode,
    selected,
    rows: [
      ["slug", ...(includeListMode ? ["_list_mode"] : []), ...fields],
      ...selected.map(row => [row.dataset.slug, ...(includeListMode ? [listMode] : []), ...fields.map(field => values[field])]),
    ],
  }};
}}

function updateBulkPreview() {{
  const {{ fields }} = patchFieldValues();
  const selected = selectedRows();
  copyPatchDryRun.disabled = !selected.length || !fields.length;
  copyPatchWrite.disabled = !selected.length || !fields.length;
  if (!selected.length || !fields.length) {{
    bulkPreview.textContent = "选择论文和字段后显示 patch 摘要。";
    return;
  }}
  const listFields = fields.filter(field => listPatchFields.has(field));
  const listModeLabel = listFields.length
    ? `；分类字段以 ${{bulkListMode.options[bulkListMode.selectedIndex].textContent}} 写入`
    : "";
  const sample = selected.slice(0, 8).map(row => `<span>${{row.dataset.slug}}</span>`).join("");
  const more = selected.length > 8 ? `<span>+${{selected.length - 8}}</span>` : "";
  bulkPreview.innerHTML = `
    <div><strong>${{selected.length}}</strong> 篇论文，字段 <strong>${{fields.join(", ")}}</strong>${{listModeLabel}}</div>
    <div class="bulk-preview-list">${{sample}}${{more}}</div>
    <code>${{patchCommand(false)}}</code>
  `;
}}

function buildPatchRows() {{
  const spec = buildPatchSpec(true);
  return spec ? spec.rows : [];
}}

function render() {{
  const q = search.value.trim().toLowerCase();
  const minImportance = Number(importance.value || 0);
  const reviewValue = review.value;
  const today = localDateString();
  const filtered = allRows.filter(row => {{
    return (!q || row.dataset.search.includes(q))
      && hasToken(row, "domains", domain.value)
      && hasToken(row, "tracks", track.value)
      && hasToken(row, "problems", problem.value)
      && hasToken(row, "topics", topic.value)
      && hasToken(row, "methods", method.value)
      && (!line.value || row.dataset.line === line.value)
      && (!role.value || row.dataset.role === role.value)
      && (!status.value || row.dataset.status === status.value)
      && (!stage.value || row.dataset.stage === stage.value)
      && (!reviewStage.value || row.dataset.reviewStage === reviewStage.value)
      && matchesReviewQueue(row, reviewValue, today)
      && (!code.value || row.dataset.code === code.value)
      && (!minImportance || Number(row.dataset.importance || 0) >= minImportance);
  }});
  const ranked = sortRows(filtered);
  currentRankedRows = ranked;
  renderActiveFilters();
  updateLibraryInsights(ranked);
  const limit = pageLimit();
  const totalPages = limit === Infinity ? 1 : Math.max(1, Math.ceil(ranked.length / limit));
  currentPage = Math.min(Math.max(currentPage, 1), totalPages);
  const start = limit === Infinity ? 0 : (currentPage - 1) * limit;
  const visible = new Set(ranked.slice(start, limit === Infinity ? ranked.length : start + limit));
  const fragment = document.createDocumentFragment();
  ranked.forEach(row => {{
    row.hidden = !visible.has(row);
    fragment.appendChild(row);
  }});
  tbody.appendChild(fragment);
  allRows.forEach(row => {{
    if (!filtered.includes(row)) row.hidden = true;
  }});
  resultCount.textContent = `显示 ${{ranked.length}} / ${{allRows.length}} 篇`;
  pageInfo.textContent = `第 ${{currentPage}} / ${{totalPages}} 页`;
  pager.hidden = ranked.length === 0 || limit === Infinity || totalPages <= 1;
  prevPage.disabled = currentPage <= 1;
  nextPage.disabled = currentPage >= totalPages;
  updateBulkState();
  writeStateToUrl();
}}

controls.forEach(([, el]) => el.addEventListener("input", () => {{
  if (el === statusWorkflow) applyStatusWorkflow();
  currentPage = 1;
  render();
}}));
activeFilters.addEventListener("click", (event) => {{
  const button = event.target instanceof Element ? event.target.closest("[data-filter-key]") : null;
  if (button) clearActiveFilter(button.dataset.filterKey);
}});
resetFilters.addEventListener("click", () => {{
  controls.forEach(([key, el]) => {{
    el.value = defaultValueFor(key);
  }});
  applyStatusWorkflow();
  currentPage = 1;
  render();
}});
saveView.addEventListener("click", () => {{
  const name = window.prompt("保存当前视图为");
  if (!name || !name.trim()) return;
  const normalized = name.trim();
  const views = readSavedViews().filter(view => view.name !== normalized);
  views.unshift({{ name: normalized, state: currentState() }});
  if (!writeSavedViews(views)) return;
  refreshSavedViews();
  savedView.value = "local:0";
}});
copyCurrentLink.addEventListener("click", () => copyText(currentViewUrl(), "复制当前视图链接"));
copySharedView.addEventListener("click", () => copyJsonSnippet(sharedViewPayload("library")));
exportSavedViews.addEventListener("click", () => {{
  const views = readSavedViews();
  if (!views.length) {{
    window.alert("当前没有本地保存视图。");
    return;
  }}
  const payload = {{ page: "library", saved_views: views }};
  downloadText("library_saved_views.json", JSON.stringify(payload, null, 2) + "\\n", "application/json;charset=utf-8");
}});
importSavedViews.addEventListener("click", () => {{
  const text = window.prompt("粘贴 saved_views / shared_views JSON");
  if (!text || !text.trim()) return;
  try {{
    const incoming = normalizeSavedViews(JSON.parse(text), "library");
    if (!incoming.length) {{
      window.alert("没有找到可导入的视图。");
      return;
    }}
    const names = new Set(incoming.map(view => view.name));
    const merged = [...incoming, ...readSavedViews().filter(view => !names.has(view.name))];
    if (!writeSavedViews(merged)) return;
    refreshSavedViews();
    savedView.value = "local:0";
    window.alert(`已导入 ${{incoming.length}} 个视图。`);
  }} catch {{
    window.alert("JSON 解析失败，请检查格式。");
  }}
}});
deleteView.addEventListener("click", () => {{
  if (!savedView.value || !savedView.value.startsWith("local:")) {{
    if (savedView.value.startsWith("shared:")) window.alert("共享视图来自 taxonomy.json，不能在页面里删除。");
    return;
  }}
  const index = Number(savedView.value.split(":")[1]);
  const views = readSavedViews();
  views.splice(index, 1);
  if (!writeSavedViews(views)) return;
  refreshSavedViews();
}});
savedView.addEventListener("change", () => {{
  if (!savedView.value) return;
  const [source, indexText] = savedView.value.split(":");
  const index = Number(indexText);
  const view = source === "shared" ? sharedViews[index] : readSavedViews()[index];
  if (view) applyState(view.state || {{}});
}});
prevPage.addEventListener("click", () => {{
  currentPage -= 1;
  render();
}});
nextPage.addEventListener("click", () => {{
  currentPage += 1;
  render();
}});
rowChecks.forEach(check => check.addEventListener("change", updateBulkState));
toggleVisible.addEventListener("change", () => {{
  visibleRows().forEach(row => {{
    row.querySelector(".row-check").checked = toggleVisible.checked;
  }});
  updateBulkState();
}});
selectVisible.addEventListener("click", () => {{
  visibleRows().forEach(row => {{
    row.querySelector(".row-check").checked = true;
  }});
  updateBulkState();
}});
selectFiltered.addEventListener("click", () => {{
  currentRankedRows.forEach(row => {{
    row.querySelector(".row-check").checked = true;
  }});
  updateBulkState();
}});
clearSelected.addEventListener("click", () => {{
  rowChecks.forEach(check => {{
    check.checked = false;
  }});
  updateBulkState();
}});
downloadPatch.addEventListener("click", () => {{
  const rows = buildPatchRows();
  if (rows.length) downloadCsv("metadata_patch.csv", rows);
}});
previewPatch.addEventListener("click", () => updateBulkPreview());
copySelectedMarkdown.addEventListener("click", () => copySelectedRows("markdown"));
copySelectedSlugs.addEventListener("click", () => copySelectedRows("slugs"));
copyPatchDryRun.addEventListener("click", () => copyText(patchCommand(false), "复制 dry-run 命令"));
copyPatchWrite.addEventListener("click", () => copyText(patchCommand(true), "复制写入命令"));
[
  bulkStatus,
  bulkStage,
  bulkReviewStage,
  bulkNextReview,
  bulkImportance,
  bulkListMode,
  bulkResearchLine,
  bulkLineRole,
  bulkDomains,
  bulkTracks,
  bulkProblems,
  bulkTopics,
  bulkMethods,
].forEach(el => el.addEventListener("input", updateBulkPreview));
exportMarkdown.addEventListener("click", () => exportRows("markdown"));
exportCsv.addEventListener("click", () => exportRows("csv"));
exportBibtex.addEventListener("click", () => exportRows("bibtex"));
columnToggles.forEach(toggle => toggle.addEventListener("change", () => {{
  const prefs = collectLibraryPrefs();
  applyLibraryPrefs(prefs);
  writeLibraryPrefs(prefs);
}}));
densityMode.addEventListener("input", () => {{
  const prefs = collectLibraryPrefs();
  applyLibraryPrefs(prefs);
  writeLibraryPrefs(prefs);
}});

populateStatusWorkflowOptions();
readStateFromUrl();
refreshSavedViews();
applyLibraryPrefs(readLibraryPrefs());
render();
</script>
"""
    (report_dir / "library.html").write_text(page_shell("论文库表格", body, data, bulk_css), encoding="utf-8")


def render_board_card(paper: dict[str, Any]) -> str:
    link = paper["html_path"] or paper["md_path"]
    labels = [
        f'I {paper.get("importance")}' if paper.get("importance") else "",
        str(paper.get("reading_stage") or ""),
        str(paper.get("line_role") or ""),
        "code" if paper.get("has_code") else "",
    ]
    flags = "".join(f'<span class="flag">{html.escape(label)}</span>' for label in labels if label)
    tags = render_inline_chips([*paper.get("topics", []), *paper.get("methods", [])], 4)
    search_text = " ".join(
        str(part)
        for part in [
            paper.get("slug"),
            paper.get("title"),
            paper.get("title_zh"),
            paper.get("title_en"),
            paper.get("arxiv_id"),
            paper.get("research_line"),
            paper.get("line_role"),
            paper.get("status"),
            paper.get("reading_stage"),
            *paper.get("authors", []),
            *paper.get("domains", []),
            *paper.get("tracks", []),
            *paper.get("problems", []),
            *paper.get("topics", []),
            *paper.get("methods", []),
        ]
        if part
    ).lower()
    return f"""<article class="board-card" draggable="true"
  data-slug="{html.escape(str(paper.get("slug") or ""), quote=True)}"
  data-original-status="{html.escape(str(paper.get("status") or "unread"), quote=True)}"
  data-status="{html.escape(str(paper.get("status") or "unread"), quote=True)}"
  data-line="{html.escape(str(paper.get("research_line") or ""), quote=True)}"
  data-tracks="{html.escape(attr_tokens(paper.get("tracks", [])), quote=True)}"
  data-importance="{html.escape(str(paper.get("importance") or 0), quote=True)}"
  data-search="{html.escape(search_text, quote=True)}">
  <h3><a href="{html.escape(link)}">{html.escape(paper["title_zh"] or paper["title"])}</a></h3>
  <div class="meta">{html.escape(str(paper.get("title_en") or ""))}</div>
  <div class="meta">{html.escape(str(paper.get("research_line") or "Unassigned"))}</div>
  <div class="card-flags">{flags}</div>
  <div class="chips">{tags}</div>
</article>"""


def render_board(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
    controls = control_options()
    status_workflows = controls.get("status_workflows") or {}
    active_workflow = controls.get("active_status_workflow") or next(iter(status_workflows), "")
    workflow_options = "".join(
        f'<option value="{html.escape(name, quote=True)}"{" selected" if name == active_workflow else ""}>{html.escape(name)}</option>'
        for name in status_workflows
    )
    workflow_select = (
        f'<select id="boardWorkflow" aria-label="状态工作流">{workflow_options}</select>'
        if workflow_options
        else '<select id="boardWorkflow" aria-label="状态工作流"><option value="">默认状态流</option></select>'
    )
    workflow_json = json.dumps(status_workflows, ensure_ascii=False)
    active_workflow_json = json.dumps(active_workflow, ensure_ascii=False)
    statuses = list(taxonomy["statuses"].keys())
    fallback_statuses = sorted(
        {
            str(paper.get("status") or "unread")
            for paper in papers
            if str(paper.get("status") or "").strip() and str(paper.get("status") or "") not in statuses
        }
    )
    statuses.extend(fallback_statuses)
    if not statuses:
        statuses = controls["status"] or DEFAULT_STATUS_VALUES

    status_columns = []
    for status in statuses:
        cards = "\n".join(render_board_card(paper) for paper in papers if str(paper.get("status") or "unread") == status)
        status_columns.append(
            f"""<section class="board-column" data-status="{html.escape(status, quote=True)}">
  <header><h2>{html.escape(status)}</h2><span class="board-count">0</span></header>
  <div class="board-dropzone" data-status="{html.escape(status, quote=True)}">{cards}</div>
</section>"""
        )

    board_css = """
    .board-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .status-composer {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      padding: 12px;
      margin: 10px 0 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .status-composer input {
      flex: 1 1 220px;
      min-width: 0;
    }
    .board-wrap {
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(280px, 1fr);
      gap: 14px;
      overflow-x: auto;
      padding-bottom: 10px;
      min-height: 480px;
    }
    .board-column {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      min-width: 280px;
      max-width: 420px;
    }
    .board-column header {
      position: sticky;
      top: 0;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px 8px 0 0;
    }
    .board-column h2 { margin: 0; font-size: 15px; line-height: 1.2; }
    .board-count {
      min-width: 26px;
      text-align: center;
      color: var(--muted);
      font-weight: 800;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
    }
    .board-dropzone {
      display: grid;
      align-content: start;
      gap: 10px;
      min-height: 360px;
      padding: 12px;
    }
    .board-dropzone.drag-over { outline: 2px solid var(--accent); outline-offset: -5px; }
    .board-card {
      display: grid;
      gap: 7px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--bg);
      cursor: grab;
    }
    .board-card:active { cursor: grabbing; }
    .board-card.changed { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(37, 99, 235, .14); }
    .board-card[hidden] { display: none; }
    .board-card h3 { margin: 0; font-size: 15px; line-height: 1.35; }
    .board-card .chips { padding-top: 0; }
    .board-help { color: var(--muted); font-size: 13px; line-height: 1.5; }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Status Board</div>
  <h1>状态看板</h1>
  <p class="lead">按自定义 status 分列管理论文。拖拽卡片只会在浏览器里暂存改动，下载 CSV 后用现有写回脚本应用到 markdown frontmatter。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">状态 {len(statuses)}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="boardSearch" type="search" placeholder="搜索标题、作者、研究线、分类、状态">
    {workflow_select}
    <select id="boardLine"><option value="">全部研究线</option>{render_topic_options(taxonomy["research_lines"])}</select>
    <select id="boardTrack"><option value="">全部方向</option>{render_topic_options(taxonomy["tracks"])}</select>
    <select id="boardImportance"><option value="">重要性</option><option value="5">5 星</option><option value="4">4 星及以上</option><option value="3">3 星及以上</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="boardCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <div class="board-actions">
      <span id="changedCount" class="board-help">未保存 0 篇</span>
      <button id="downloadBoardPatch" class="button" type="button">下载 CSV</button>
      <button id="resetBoardChanges" class="button" type="button">撤销改动</button>
    </div>
  </div>
  <div class="status-composer">
    <input id="newStatusName" type="text" placeholder="新增临时状态列，例如 queued_for_deep_read" aria-label="新增状态名称">
    <button id="addStatusColumn" class="button" type="button">新增状态列</button>
  </div>
  <div class="board-help">导出后运行：python3 scripts/apply_library_metadata.py docs --input ~/Downloads/status_board_patch.csv --write</div>
  <div class="board-wrap" id="boardWrap">{''.join(status_columns)}</div>
</main>
<script>
const boardCards = Array.from(document.querySelectorAll(".board-card"));
const boardWrap = document.querySelector("#boardWrap");
let dropzones = Array.from(document.querySelectorAll(".board-dropzone"));
const boardWorkflows = {workflow_json};
const activeBoardWorkflow = {active_workflow_json};
const boardSearch = document.querySelector("#boardSearch");
const boardWorkflow = document.querySelector("#boardWorkflow");
const boardLine = document.querySelector("#boardLine");
const boardTrack = document.querySelector("#boardTrack");
const boardImportance = document.querySelector("#boardImportance");
const boardCount = document.querySelector("#boardCount");
const changedCount = document.querySelector("#changedCount");
const downloadBoardPatch = document.querySelector("#downloadBoardPatch");
const resetBoardChanges = document.querySelector("#resetBoardChanges");
const newStatusName = document.querySelector("#newStatusName");
const addStatusColumn = document.querySelector("#addStatusColumn");
let draggedCard = null;

function boardTokens(value) {{
  return String(value || "").split("|").filter(Boolean);
}}

function boardCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function downloadBoardCsv(filename, rows) {{
  const csv = rows.map(row => row.map(boardCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function changedCards() {{
  return boardCards.filter(card => card.dataset.status !== card.dataset.originalStatus);
}}

function syncBoardUrl() {{
  const url = new URL(window.location.href);
  const defaults = {{
    q: "",
    workflow: activeBoardWorkflow || "",
    line: "",
    track: "",
    importance: "",
  }};
  const values = {{
    q: boardSearch.value.trim(),
    workflow: boardWorkflow.value || "",
    line: boardLine.value || "",
    track: boardTrack.value || "",
    importance: boardImportance.value || "",
  }};
  Object.entries(values).forEach(([key, value]) => {{
    if (value && value !== defaults[key]) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }});
  window.history.replaceState(null, "", url);
}}

function readBoardState() {{
  const params = new URLSearchParams(window.location.search);
  boardSearch.value = params.get("q") || "";
  const workflow = params.get("workflow") || activeBoardWorkflow || boardWorkflow.value;
  if (workflow && Array.from(boardWorkflow.options).some(option => option.value === workflow)) {{
    boardWorkflow.value = workflow;
  }}
  boardLine.value = params.get("line") || "";
  boardTrack.value = params.get("track") || "";
  boardImportance.value = params.get("importance") || "";
}}

function placeCard(card, status) {{
  const zone = dropzones.find(item => item.dataset.status === status);
  if (!zone) return;
  zone.appendChild(card);
  card.dataset.status = status;
  card.classList.toggle("changed", card.dataset.status !== card.dataset.originalStatus);
  renderBoard();
}}

function renderBoard(updateUrl = true) {{
  const q = boardSearch.value.trim().toLowerCase();
  const minImportance = Number(boardImportance.value || 0);
  let visible = 0;
  boardCards.forEach(card => {{
    const hit = (!q || card.dataset.search.includes(q))
      && (!boardLine.value || card.dataset.line === boardLine.value)
      && (!boardTrack.value || boardTokens(card.dataset.tracks).includes(boardTrack.value))
      && (!minImportance || Number(card.dataset.importance || 0) >= minImportance);
    card.hidden = !hit;
    if (hit) visible += 1;
  }});
  dropzones.forEach(zone => {{
    const count = Array.from(zone.querySelectorAll(".board-card")).filter(card => !card.hidden).length;
    zone.closest(".board-column").querySelector(".board-count").textContent = count;
  }});
  const changed = changedCards().length;
  boardCount.textContent = `显示 ${{visible}} / ${{boardCards.length}} 篇`;
  changedCount.textContent = `未保存 ${{changed}} 篇`;
  downloadBoardPatch.disabled = changed === 0;
  resetBoardChanges.disabled = changed === 0;
  if (updateUrl) syncBoardUrl();
}}

function attachDropzone(zone) {{
  zone.addEventListener("dragover", event => {{
    event.preventDefault();
    zone.classList.add("drag-over");
  }});
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", event => {{
    event.preventDefault();
    zone.classList.remove("drag-over");
    if (draggedCard) placeCard(draggedCard, zone.dataset.status);
  }});
}}

function createBoardColumn(status) {{
  const normalized = String(status || "").trim();
  const section = document.createElement("section");
  section.className = "board-column";
  section.dataset.status = normalized;
  const header = document.createElement("header");
  const title = document.createElement("h2");
  title.textContent = normalized;
  const count = document.createElement("span");
  count.className = "board-count";
  count.textContent = "0";
  header.append(title, count);
  const zone = document.createElement("div");
  zone.className = "board-dropzone";
  zone.dataset.status = normalized;
  section.append(header, zone);
  attachDropzone(zone);
  return {{ section, zone }};
}}

function addBoardColumn(status) {{
  const normalized = String(status || "").trim();
  if (!normalized) return;
  if (dropzones.some(zone => zone.dataset.status === normalized)) {{
    window.alert("这个状态列已经存在。");
    return;
  }}
  const {{ section, zone }} = createBoardColumn(normalized);
  boardWrap.appendChild(section);
  dropzones.push(zone);
  renderBoard();
}}

function uniqueValues(values) {{
  const seen = new Set();
  return values
    .map(value => String(value || "").trim())
    .filter(value => {{
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    }});
}}

function applyWorkflow(name, updateUrl = true) {{
  const workflow = boardWorkflows[name] || {{}};
  const workflowStatuses = Array.isArray(workflow.status_values) ? workflow.status_values : [];
  const activeStatuses = boardCards.map(card => card.dataset.status || card.dataset.originalStatus || "unread");
  const orderedStatuses = uniqueValues([...workflowStatuses, ...activeStatuses]);
  if (!orderedStatuses.length) return;
  const cards = boardCards.slice();
  boardWrap.textContent = "";
  dropzones = [];
  orderedStatuses.forEach(status => {{
    const {{ section, zone }} = createBoardColumn(status);
    boardWrap.appendChild(section);
    dropzones.push(zone);
  }});
  cards.forEach(card => {{
    const status = card.dataset.status || card.dataset.originalStatus || "unread";
    const zone = dropzones.find(item => item.dataset.status === status) || dropzones[0];
    zone.appendChild(card);
  }});
  renderBoard(updateUrl);
}}

boardCards.forEach(card => {{
  card.addEventListener("dragstart", event => {{
    draggedCard = card;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", card.dataset.slug);
  }});
  card.addEventListener("dragend", () => {{
    draggedCard = null;
    dropzones.forEach(zone => zone.classList.remove("drag-over"));
  }});
}});

dropzones.forEach(attachDropzone);
addStatusColumn.addEventListener("click", () => {{
  addBoardColumn(newStatusName.value);
  newStatusName.value = "";
  newStatusName.focus();
}});
newStatusName.addEventListener("keydown", event => {{
  if (event.key === "Enter") {{
    event.preventDefault();
    addStatusColumn.click();
  }}
}});

[boardSearch, boardLine, boardTrack, boardImportance].forEach(el => el.addEventListener("input", () => renderBoard()));
boardWorkflow.addEventListener("change", () => applyWorkflow(boardWorkflow.value));
downloadBoardPatch.addEventListener("click", () => {{
  const changed = changedCards();
  if (!changed.length) return;
  downloadBoardCsv("status_board_patch.csv", [["slug", "status"], ...changed.map(card => [card.dataset.slug, card.dataset.status])]);
}});
resetBoardChanges.addEventListener("click", () => {{
  changedCards().forEach(card => placeCard(card, card.dataset.originalStatus));
}});
readBoardState();
applyWorkflow(boardWorkflow.value, false);
</script>
"""
    (report_dir / "board.html").write_text(page_shell("状态看板", body, extra_css=board_css), encoding="utf-8")


def render_workflow(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_workflow_payload(papers)
    active = next((workflow for workflow in payload["workflows"] if workflow["active"]), payload["workflows"][0] if payload["workflows"] else {})
    active_fields = active.get("fields") or {}
    active_statuses = active_fields.get("status", {}).get("values", [])

    def workflow_definition_cell(item: dict[str, Any]) -> str:
        status = str(item.get("definition_status") or "")
        owner = str(item.get("owner_name") or "")
        description = str(item.get("description") or "")
        headline = " / ".join(part for part in (status, owner) if part) or "-"
        return f"{html.escape(headline)}<div class=\"meta\">{html.escape(description or 'No definition')}</div>"

    status_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["value"]))}</a></td>'
        f"<td>{int(item['count'])}</td>"
        f"<td>{workflow_definition_cell(item)}</td>"
        f'<td><a href="{html.escape(page_query_href("board.html", workflow=str(active.get("name") or ""), status=str(item["value"])))}">看板</a></td>'
        "</tr>"
        for item in active_statuses
    )
    if not status_rows:
        status_rows = '<tr><td colspan="4" class="empty">当前 workflow 没有 status 配置。</td></tr>'

    workflow_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(workflow["library_href"]))}">{html.escape(str(workflow["name"]))}</a>{" <span class=\"flag\">active</span>" if workflow["active"] else ""}</td>'
        f"<td>{len(workflow['status_values'])}</td>"
        f"<td>{len(workflow['reading_stage_values'])}</td>"
        f"<td>{len(workflow['review_stage_values'])}</td>"
        f"<td>{workflow['definition_total']}</td>"
        f"<td>{workflow['unconfigured_total']}</td>"
        f"<td>{workflow['empty_total']}</td>"
        f'<td><a href="{html.escape(str(workflow["board_href"]))}">打开看板</a></td>'
        "</tr>"
        for workflow in payload["workflows"]
    )
    if not workflow_rows:
        workflow_rows = '<tr><td colspan="8" class="empty">还没有命名 workflow。</td></tr>'

    drift_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['label']))}<div class=\"meta\">{html.escape(str(item['field']))}</div></td>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["value"]))}</a></td>'
        f"<td>{int(item['count'])}</td>"
        f"<td>{html.escape(', '.join(item.get('slugs', [])[:6]))}{' ...' if len(item.get('slugs', [])) > 6 else ''}</td>"
        "</tr>"
        for item in payload["active_unconfigured"]
    )
    if not drift_rows:
        drift_rows = '<tr><td colspan="4" class="empty">当前激活 workflow 没有未配置状态值。</td></tr>'

    field_sections = []
    for field_name in ("status", "reading_stage", "review_stage"):
        field = active_fields.get(field_name, {})
        values = field.get("values", [])
        rows = "".join(
            "<tr>"
            f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["value"]))}</a></td>'
            f"<td>{int(item['count'])}</td>"
            f"<td>{workflow_definition_cell(item)}</td>"
            f"<td>{'used' if int(item['count']) else 'empty'}</td>"
            "</tr>"
            for item in values
        )
        extras = "".join(
            "<tr>"
            f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["value"]))}</a></td>'
            f"<td>{int(item['count'])}</td>"
            f"<td>{workflow_definition_cell(item)}</td>"
            "<td>unconfigured</td>"
            "</tr>"
            for item in field.get("unconfigured", [])
        )
        table_rows = rows + extras or '<tr><td colspan="4" class="empty">没有可展示的值。</td></tr>'
        field_sections.append(
            f"""
  <section>
    <h2 class="section-title">{html.escape(str(field.get("label") or field_name))}</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>值</th><th>论文</th><th>定义</th><th>状态</th></tr></thead><tbody>{table_rows}</tbody></table></div>
  </section>"""
        )

    shared_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(view["href"]))}">{html.escape(str(view["name"]))}</a></td>'
        f"<td>{html.escape(str(view.get('page') or 'all'))}</td>"
        f"<td>{html.escape(str(view.get('workflow') or ''))}</td>"
        f"<td><code>{html.escape(json.dumps(view.get('state') or {}, ensure_ascii=False, sort_keys=True))}</code></td>"
        "</tr>"
        for view in payload["shared_workflow_views"]
    )
    if not shared_rows:
        shared_rows = '<tr><td colspan="4" class="empty">暂无绑定 workflow 的共享视图。</td></tr>'

    recommendation_html = "".join(f"<li>{html.escape(text)}</li>" for text in payload["recommendations"])
    command_buttons = "".join(
        f'<button class="button copy-workflow-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command.split()[1] if len(command.split()) > 1 else command)}</button>'
        for command in payload["commands"]
    )

    workflow_css = """
    .workflow-summary {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr);
      align-items: start;
    }
    .workflow-command-panel {
      display: grid;
      gap: 10px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .workflow-command-panel .bulk-actions { margin: 0; }
    .workflow-recommendations {
      margin: 0;
      padding-left: 20px;
      color: var(--muted);
      line-height: 1.55;
    }
    @media (max-width: 860px) { .workflow-summary { grid-template-columns: 1fr; } }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Workflow Center</div>
  <h1>工作流中心</h1>
  <p class="lead">集中查看当前启用的状态体系、不同 workflow 的覆盖情况、未配置状态漂移和共享视图绑定。适合在论文库变大后持续调整阅读状态语义。</p>
  <div class="stats">
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="workflow.json">Workflow JSON</a>
    <a class="stat" href="snapshot.html">治理快照</a>
    <span class="stat">active {html.escape(str(payload["active_status_workflow"]))}</span>
    <span class="stat">workflow {payload["workflow_count"]}</span>
    <span class="stat">论文 {payload["count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="workflow-summary">
    <div>
      <h2 class="section-title">当前 Status 分布</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Status</th><th>论文</th><th>定义</th><th>入口</th></tr></thead><tbody>{status_rows}</tbody></table></div>
    </div>
    <div class="workflow-command-panel">
      <strong>推荐动作</strong>
      <ol class="workflow-recommendations">{recommendation_html}</ol>
      <div class="bulk-actions">{command_buttons}</div>
      <p class="meta">复制后在仓库根目录执行；带 --write 的命令会修改 taxonomy.json 或报告 frontmatter。</p>
    </div>
  </section>
  <section>
    <h2 class="section-title">Workflow 对比</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>Workflow</th><th>Status</th><th>Reading</th><th>Review</th><th>已定义</th><th>未配置值</th><th>空字段</th><th>入口</th></tr></thead><tbody>{workflow_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">当前 Drift</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>字段</th><th>值</th><th>论文</th><th>样例</th></tr></thead><tbody>{drift_rows}</tbody></table></div>
  </section>
  {''.join(field_sections)}
  <section>
    <h2 class="section-title">绑定 Workflow 的共享视图</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>视图</th><th>页面</th><th>Workflow</th><th>State</th></tr></thead><tbody>{shared_rows}</tbody></table></div>
  </section>
</main>
<script>
document.querySelectorAll(".copy-workflow-command").forEach(button => {{
  button.dataset.label = button.textContent;
  button.addEventListener("click", async () => {{
    try {{
      await navigator.clipboard.writeText(button.dataset.command || "");
      button.textContent = "已复制";
      setTimeout(() => button.textContent = button.dataset.label, 1200);
    }} catch (error) {{
      window.prompt("复制命令", button.dataset.command || "");
    }}
  }});
}});
</script>
"""
    (report_dir / "workflow.html").write_text(page_shell("工作流中心", body, extra_css=workflow_css), encoding="utf-8")


def render_status(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_status_selector_payload(papers)
    status_json = json.dumps(payload, ensure_ascii=False)
    workflow_options = "".join(
        f'<option value="{html.escape(str(workflow["name"]), quote=True)}">'
        f'{html.escape(str(workflow["name"]))}{" (默认)" if workflow.get("active") else ""}</option>'
        for workflow in payload["workflows"]
    )
    command_buttons = "".join(
        f'<button class="button copy-status-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command.split()[1] if len(command.split()) > 1 else command)}</button>'
        for command in payload["commands"]
    )
    status_css = """
    .status-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
      gap: 16px;
      align-items: start;
    }
    .status-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .status-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
    }
    .status-choice {
      display: grid;
      gap: 4px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: color-mix(in srgb, var(--panel) 88%, white);
    }
    .status-choice strong { font-size: 16px; }
    .status-choice span { color: var(--muted); font-size: 13px; }
    .status-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .status-builder {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(160px, 220px);
      gap: 10px;
      margin-top: 14px;
    }
    .status-builder label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .status-builder input,
    .status-builder select {
      width: 100%;
    }
    .status-output {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .status-patch {
      display: grid;
      gap: 10px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }
    .status-patch-controls {
      display: grid;
      grid-template-columns: minmax(140px, .8fr) minmax(160px, 1fr);
      gap: 10px;
    }
    .status-patch-controls label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .status-url {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8f5ed;
      color: var(--ink);
      padding: 9px 10px;
      font: 13px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .status-summary {
      color: var(--muted);
      font-size: 13px;
    }
    .status-config {
      width: 100%;
      min-height: 160px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      padding: 10px;
      font: 13px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    @media (max-width: 900px) {
      .status-layout { grid-template-columns: 1fr; }
      .status-builder { grid-template-columns: 1fr; }
      .status-patch-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Status Selector</div>
  <h1>状态选择器</h1>
  <p class="lead">把多套 `status_workflows` 变成运行时可选项：选择 workflow、status、reading stage 和 review stage 后，可直接跳转到对应页面，或复制共享视图与配置片段。</p>
  <div class="stats">
    <a class="stat" href="status.json">Status JSON</a>
    <a class="stat" href="workflow.html">工作流中心</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <span class="stat">active {html.escape(str(payload["active_status_workflow"]))}</span>
    <span class="stat">workflow {payload["workflow_count"]}</span>
    <span class="stat">论文 {payload["count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="status-layout">
    <div class="status-panel">
      <div class="controls">
        <select id="statusWorkflow" aria-label="状态体系">{workflow_options}</select>
        <select id="statusValue" aria-label="状态"><option value="">全部状态</option></select>
        <select id="statusStage" aria-label="阅读阶段"><option value="">全部阅读阶段</option></select>
        <select id="statusReview" aria-label="复习阶段"><option value="">全部复习阶段</option></select>
      </div>
      <div class="status-actions">
        <a class="button" id="openLibrary" href="library.html">打开论文库</a>
        <a class="button" id="openBoard" href="board.html">打开看板</a>
        <a class="button" id="openIndex" href="index.html">打开首页</a>
        <button class="button" type="button" id="copyStatusUrl">复制当前链接</button>
        <button class="button" type="button" id="copyStatusView">复制共享视图</button>
        <button class="button" type="button" id="downloadStatusView">下载共享视图</button>
        <button class="button" type="button" id="copyStatusConfig">复制当前 workflow 配置</button>
      </div>
      <div class="status-builder">
        <label><span>场景名称</span><input id="statusViewName" type="text" value="状态视图"></label>
        <label>
          <span>共享视图页面</span>
          <select id="statusViewPage">
            <option value="library">论文库</option>
            <option value="index">首页</option>
            <option value="all">全局</option>
          </select>
        </label>
      </div>
      <div class="status-output">
        <input class="status-url" id="statusShareUrl" readonly value="status.html">
        <p class="status-summary" id="statusSelectionSummary"></p>
      </div>
      <div class="status-patch">
        <h2 class="section-title">批量状态写回</h2>
        <div class="status-patch-controls">
          <label>
            <span>写回字段</span>
            <select id="statusPatchField">
              <option value="status">status</option>
              <option value="reading_stage">reading_stage</option>
              <option value="review_stage">review_stage</option>
            </select>
          </label>
          <label><span>写回值</span><select id="statusPatchValue"></select></label>
        </div>
        <div class="status-actions">
          <button class="button" type="button" id="copyStatusPatch">复制 patch CSV</button>
          <button class="button" type="button" id="downloadStatusPatch">下载 patch CSV</button>
          <button class="button" type="button" id="copyStatusPatchDryRun">复制 dry-run</button>
          <button class="button" type="button" id="copyStatusPatchWrite">复制 write</button>
        </div>
        <p class="meta" id="statusPatchSummary"></p>
      </div>
      <h2 class="section-title">当前候选值</h2>
      <div class="status-grid" id="statusChoices"></div>
    </div>
    <aside class="status-panel">
      <h2 class="section-title">配置片段</h2>
      <textarea class="status-config" id="statusConfigPreview" readonly></textarea>
      <h2 class="section-title">共享视图包</h2>
      <textarea class="status-config" id="statusSharedViewPreview" readonly></textarea>
      <div class="bulk-actions">{command_buttons}</div>
      <p class="meta">复制 JSON 后可用 apply_status_workflow.py 或 apply_shared_views.py 预览/写回；页面选择只影响当前浏览视图，不会直接修改报告。</p>
    </aside>
  </section>
  <section>
    <h2 class="section-title">命中论文 <span class="meta" id="statusResultCount"></span></h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>论文</th><th>研究线</th><th>Status</th><th>Reading</th><th>Review</th><th>重要性</th></tr></thead><tbody id="statusRows"></tbody></table></div>
  </section>
</main>
<script>
const statusPayload = {status_json};
const statusWorkflow = document.querySelector("#statusWorkflow");
const statusValue = document.querySelector("#statusValue");
const statusStage = document.querySelector("#statusStage");
const statusReview = document.querySelector("#statusReview");
const statusChoices = document.querySelector("#statusChoices");
const statusRows = document.querySelector("#statusRows");
const statusResultCount = document.querySelector("#statusResultCount");
const statusConfigPreview = document.querySelector("#statusConfigPreview");
const statusSharedViewPreview = document.querySelector("#statusSharedViewPreview");
const statusShareUrl = document.querySelector("#statusShareUrl");
const statusSelectionSummary = document.querySelector("#statusSelectionSummary");
const statusViewName = document.querySelector("#statusViewName");
const statusViewPage = document.querySelector("#statusViewPage");
const statusPatchField = document.querySelector("#statusPatchField");
const statusPatchValue = document.querySelector("#statusPatchValue");
const statusPatchSummary = document.querySelector("#statusPatchSummary");
const openLibrary = document.querySelector("#openLibrary");
const openBoard = document.querySelector("#openBoard");
const openIndex = document.querySelector("#openIndex");
const patchFieldConfig = {{
  status: {{ valueKey: "status_values", paperField: "status", label: "status" }},
  reading_stage: {{ valueKey: "reading_stage_values", paperField: "reading_stage", label: "reading_stage" }},
  review_stage: {{ valueKey: "review_stage_values", paperField: "review_stage", label: "review_stage" }},
}};

function workflowByName(name) {{
  return statusPayload.workflows.find(workflow => workflow.name === name) || statusPayload.workflows[0] || {{}};
}}

function uniqueObserved(field) {{
  return Array.from(new Set(statusPayload.papers.map(paper => paper[field]).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}}

function countFor(field, value) {{
  return statusPayload.papers.filter(paper => paper[field] === value).length;
}}

function workflowItems(workflow, fieldName, valueKey, paperField) {{
  const field = (workflow.fields || {{}})[fieldName] || {{}};
  const configuredItems = Array.isArray(field.values) ? field.values : (workflow[valueKey] || []).map(value => ({{ value }}));
  const unconfiguredItems = Array.isArray(field.unconfigured) ? field.unconfigured : [];
  const byValue = new Map();
  [...configuredItems, ...unconfiguredItems].forEach(item => {{
    if (item && item.value && !byValue.has(item.value)) byValue.set(item.value, item);
  }});
  uniqueObserved(paperField).forEach(value => {{
    if (!byValue.has(value)) byValue.set(value, {{ value, count: countFor(paperField, value), configured: false }});
  }});
  return Array.from(byValue.values());
}}

function definitionText(item) {{
  const bits = [item.definition_status, item.owner_name].filter(Boolean);
  return {{
    head: bits.join(" / ") || "No definition",
    body: item.description || "还没有为这个状态值写 description。",
  }};
}}

function fillSelect(select, label, items, field) {{
  const current = select.value;
  select.replaceChildren(new Option(label, ""));
  const values = items.map(item => item.value).filter(Boolean);
  items.forEach(item => {{
    const value = item.value;
    const option = new Option(`${{value}} (${{countFor(field, value)}})`, value);
    const definition = definitionText(item);
    option.title = `${{definition.head}} — ${{definition.body}}`;
    select.appendChild(option);
  }});
  select.value = values.includes(current) ? current : "";
}}

function stateFromControls() {{
  return {{
    workflow: statusWorkflow.value || statusPayload.active_status_workflow || "",
    status: statusValue.value || "",
    stage: statusStage.value || "",
    reviewStage: statusReview.value || "",
  }};
}}

function compactState() {{
  return Object.fromEntries(Object.entries(stateFromControls()).filter(([, value]) => value));
}}

function queryHref(page) {{
  const url = new URL(page, window.location.href);
  Object.entries(stateFromControls()).forEach(([key, value]) => {{
    if (value) url.searchParams.set(key, value);
  }});
  return `${{url.pathname.split("/").pop()}}${{url.search}}`;
}}

function targetPageHref() {{
  const page = statusViewPage.value === "index" ? "index.html" : "library.html";
  return queryHref(page);
}}

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function sharedViewPayload() {{
  const state = compactState();
  const page = statusViewPage.value || "library";
  const name = statusViewName.value.trim() || `状态视图-${{state.workflow || "default"}}`;
  return {{
    page,
    shared_views: [
      {{
        name,
        page,
        state,
      }},
    ],
  }};
}}

function downloadJson(filename, payload) {{
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\\n"], {{ type: "application/json;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function downloadText(filename, text, type = "text/plain;charset=utf-8") {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function renderConfig(workflow) {{
  const name = workflow.name || statusPayload.active_status_workflow || "default";
  const config = {{
    active_status_workflow: name,
    status_workflows: {{
      [name]: {{
        status_values: workflow.status_values || [],
        reading_stage_values: workflow.reading_stage_values || [],
        review_stage_values: workflow.review_stage_values || [],
      }},
    }},
  }};
  statusConfigPreview.value = JSON.stringify(config, null, 2);
}}

function renderSharedView(rows) {{
  const state = compactState();
  const payload = sharedViewPayload();
  statusSharedViewPreview.value = JSON.stringify(payload, null, 2);
  statusShareUrl.value = targetPageHref();
  const selected = [
    state.workflow ? `workflow=${{state.workflow}}` : "",
    state.status ? `status=${{state.status}}` : "",
    state.stage ? `reading=${{state.stage}}` : "",
    state.reviewStage ? `review=${{state.reviewStage}}` : "",
  ].filter(Boolean).join(" / ") || "全部状态";
  statusSelectionSummary.textContent = `当前场景命中 ${{rows.length}} 篇论文；${{selected}}。共享视图可写回 guides/taxonomy.json，之后首页和论文库会出现同一套入口。`;
}}

function patchItemsFor(workflow, fieldName) {{
  const config = patchFieldConfig[fieldName] || patchFieldConfig.status;
  const workflowField = fieldName === "status" ? "status" : fieldName;
  return workflowItems(workflow, workflowField, config.valueKey, config.paperField);
}}

function updatePatchValueOptions(workflow) {{
  const current = statusPatchValue.value;
  const items = patchItemsFor(workflow, statusPatchField.value);
  statusPatchValue.replaceChildren();
  items.forEach(item => {{
    if (!item.value) return;
    const option = new Option(item.value, item.value);
    const definition = definitionText(item);
    option.title = `${{definition.head}} — ${{definition.body}}`;
    statusPatchValue.appendChild(option);
  }});
  const values = items.map(item => item.value).filter(Boolean);
  statusPatchValue.value = values.includes(current) ? current : (values[0] || "");
}}

function statusPatchCsv() {{
  const rows = filteredPapers();
  const field = statusPatchField.value || "status";
  const value = statusPatchValue.value || "";
  const header = ["slug", field];
  const csvRows = [header, ...rows.map(paper => [paper.slug, value])];
  return csvRows.map(row => row.map(csvCell).join(",")).join("\\n") + "\\n";
}}

function renderStatusPatchSummary(rows) {{
  const field = statusPatchField.value || "status";
  const value = statusPatchValue.value || "";
  statusPatchSummary.textContent = rows.length
    ? `将为当前命中的 ${{rows.length}} 篇论文生成 ${{field}}=${{value || "(empty)"}} 的 status_patch.csv；正式写回前先 dry-run。`
    : "当前没有命中论文，patch 只会包含表头。";
}}

function renderChoices(workflow, statusItems) {{
  statusChoices.replaceChildren();
  statusItems.forEach(item => {{
    const value = item.value;
    const definition = definitionText(item);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "status-choice";
    card.innerHTML = `<strong>${{value}}</strong><span>${{countFor("status", value)}} 篇论文</span><span>${{definition.head}}</span><span>${{definition.body}}</span>`;
    card.addEventListener("click", () => {{
      statusValue.value = value;
      renderStatus();
    }});
    statusChoices.appendChild(card);
  }});
  if (!statusItems.length) {{
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "当前 workflow 没有 status 候选。";
    statusChoices.appendChild(empty);
  }}
}}

function filteredPapers() {{
  return statusPayload.papers.filter(paper => (
    (!statusValue.value || paper.status === statusValue.value)
    && (!statusStage.value || paper.reading_stage === statusStage.value)
    && (!statusReview.value || paper.review_stage === statusReview.value)
  ));
}}

function renderRows() {{
  const rows = filteredPapers();
  statusResultCount.textContent = `${{rows.length}} / ${{statusPayload.count}}`;
  statusRows.replaceChildren();
  renderSharedView(rows);
  renderStatusPatchSummary(rows);
  if (!rows.length) {{
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6" class="empty">当前选择没有命中论文。</td>`;
    statusRows.appendChild(row);
    return;
  }}
  rows.forEach(paper => {{
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><a href="${{paper.href}}">${{paper.title_zh || paper.title}}</a><div class="meta">${{paper.slug}}</div></td>
      <td>${{paper.research_line || "Unassigned"}}</td>
      <td>${{paper.status || ""}}</td>
      <td>${{paper.reading_stage || ""}}</td>
      <td>${{paper.review_stage || ""}}</td>
      <td>${{paper.importance || ""}}</td>
    `;
    statusRows.appendChild(row);
  }});
}}

function syncLinks() {{
  openLibrary.href = queryHref("library.html");
  openBoard.href = queryHref("board.html");
  openIndex.href = queryHref("index.html");
  statusShareUrl.value = targetPageHref();
}}

function renderStatus() {{
  const workflow = workflowByName(statusWorkflow.value);
  const statusItems = workflowItems(workflow, "status", "status_values", "status");
  const stageItems = workflowItems(workflow, "reading_stage", "reading_stage_values", "reading_stage");
  const reviewItems = workflowItems(workflow, "review_stage", "review_stage_values", "review_stage");
  fillSelect(statusValue, "全部状态", statusItems, "status");
  fillSelect(statusStage, "全部阅读阶段", stageItems, "reading_stage");
  fillSelect(statusReview, "全部复习阶段", reviewItems, "review_stage");
  renderChoices(workflow, statusItems);
  renderConfig(workflow);
  updatePatchValueOptions(workflow);
  renderRows();
  syncLinks();
}}

function readStatusUrl() {{
  const params = new URLSearchParams(window.location.search);
  statusWorkflow.value = params.get("workflow") || statusPayload.active_status_workflow || statusWorkflow.value;
  renderStatus();
  statusValue.value = params.get("status") || "";
  statusStage.value = params.get("stage") || "";
  statusReview.value = params.get("reviewStage") || "";
  renderStatus();
}}

async function copyText(value, fallbackTitle) {{
  try {{
    await navigator.clipboard.writeText(value);
  }} catch (error) {{
    window.prompt(fallbackTitle, value);
  }}
}}

document.querySelector("#copyStatusUrl").addEventListener("click", () => copyText(statusShareUrl.value, "复制当前链接"));

document.querySelector("#copyStatusView").addEventListener("click", () => copyText(statusSharedViewPreview.value, "复制共享视图"));

document.querySelector("#downloadStatusView").addEventListener("click", () => downloadJson("status_shared_view.json", sharedViewPayload()));

document.querySelector("#copyStatusConfig").addEventListener("click", () => copyText(statusConfigPreview.value, "复制状态配置"));

document.querySelector("#copyStatusPatch").addEventListener("click", () => copyText(statusPatchCsv(), "复制 patch CSV"));

document.querySelector("#downloadStatusPatch").addEventListener("click", () => downloadText("status_patch.csv", statusPatchCsv(), "text/csv;charset=utf-8"));

document.querySelector("#copyStatusPatchDryRun").addEventListener("click", () => copyText("python3 scripts/apply_library_metadata.py docs --input status_patch.csv", "复制 dry-run 命令"));

document.querySelector("#copyStatusPatchWrite").addEventListener("click", () => copyText("python3 scripts/apply_library_metadata.py docs --input status_patch.csv --write", "复制 write 命令"));

document.querySelectorAll(".copy-status-command").forEach(button => {{
  button.dataset.label = button.textContent;
  button.addEventListener("click", async () => {{
    await copyText(button.dataset.command || "", "复制命令");
    button.textContent = "已复制";
    setTimeout(() => button.textContent = button.dataset.label, 1200);
  }});
}});

[statusWorkflow, statusValue, statusStage, statusReview, statusViewName, statusViewPage, statusPatchField, statusPatchValue].forEach(control => {{
  control.addEventListener("input", () => {{
    if (control === statusWorkflow) {{
      statusValue.value = "";
      statusStage.value = "";
      statusReview.value = "";
    }}
    renderStatus();
  }});
}});

readStatusUrl();
</script>
"""
    (report_dir / "status.html").write_text(page_shell("状态选择器", body, extra_css=status_css), encoding="utf-8")


def render_batch(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_batch_payload(papers, report_dir)
    batch_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    dimension_options = "".join(
        f'<option value="{html.escape(str(item["key"]), quote=True)}">{html.escape(str(item["label"]))}</option>'
        for item in payload["dimensions"]
    )
    top_rows = "".join(
        "<tr>"
        f'<td><span class="flag">{html.escape(str(item["severity"]))}</span></td>'
        f"<td>{html.escape(str(item['dimension_label']))}</td>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["value"]))}</a></td>'
        f"<td>{int(item['count'])}</td>"
        f"<td>{int(item['missing_review'])}</td>"
        f"<td>{int(item['missing_taxonomy'])}</td>"
        f"<td>{html.escape(str(item['recommended_action']))}</td>"
        "</tr>"
        for item in payload["top_batches"][:8]
    ) or '<tr><td colspan="7" class="empty">暂无批次。</td></tr>'
    batch_css = """
    .batch-layout {
      display: grid;
      grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .batch-panel {
      position: sticky;
      top: 82px;
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .batch-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .batch-table td,
    .batch-table th {
      vertical-align: top;
    }
    .batch-table code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .batch-table tr.is-active td {
      background: color-mix(in srgb, var(--chip) 72%, white);
    }
    .batch-select {
      margin-top: 6px;
      padding: 4px 8px;
      font-size: 12px;
    }
    .batch-detail {
      display: grid;
      gap: 9px;
      border-top: 1px solid var(--line);
      margin-top: 4px;
      padding-top: 12px;
    }
    .batch-detail h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.25;
    }
    .batch-detail code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .batch-patch {
      display: grid;
      gap: 8px;
      border-top: 1px solid var(--line);
      margin-top: 2px;
      padding-top: 12px;
    }
    .batch-patch label {
      display: grid;
      gap: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .batch-patch input,
    .batch-patch select {
      width: 100%;
    }
    .batch-samples {
      max-width: 320px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    @media (max-width: 920px) {
      .batch-layout { grid-template-columns: 1fr; }
      .batch-panel { position: static; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Batch Planner</div>
  <h1>批次规划</h1>
  <p class="lead">把大量论文按研究线、标签、状态、阅读阶段和复习缺口切成可执行批次。先选批次，再跳回论文库做批量 patch、导出或分派。</p>
  <div class="stats">
    <a class="stat" href="batch.json">Batch JSON</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="scale.html">规模就绪</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">批次 {payload["batch_count"]}</span>
    <span class="stat">高风险 {payload["summary"]["high"]}</span>
  </div>
</header>
<main class="shell">
  <section class="batch-summary">
    <section class="metric-card"><span>批次</span><strong>{payload["batch_count"]}</strong><span>{payload["dimension_count"]} 个维度</span></section>
    <section class="metric-card"><span>高风险</span><strong>{payload["summary"]["high"]}</strong><span>优先整理</span></section>
    <section class="metric-card"><span>中风险</span><strong>{payload["summary"]["medium"]}</strong><span>进入维护队列</span></section>
    <section class="metric-card"><span>缺复习</span><strong>{payload["summary"]["missing_review"]}</strong><span>跨批次累计</span></section>
    <section class="metric-card"><span>缺分类</span><strong>{payload["summary"]["missing_taxonomy"]}</strong><span>跨批次累计</span></section>
  </section>
  <section class="batch-layout">
    <aside class="batch-panel">
      <input id="batchSearch" type="search" placeholder="搜索维度、值、动作或样例论文">
      <select id="batchDimension"><option value="">全部维度</option>{dimension_options}</select>
      <select id="batchSeverity"><option value="">全部风险</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select>
      <select id="batchSort"><option value="priority">优先级</option><option value="count">批次规模</option><option value="missingReview">缺复习</option><option value="missingTaxonomy">缺分类</option><option value="latestYear">最新年份</option><option value="name">名称</option></select>
      <button class="button" id="copyBatchMarkdown" type="button">复制 Markdown 计划</button>
      <button class="button" id="downloadBatchCsv" type="button">下载 CSV</button>
      <button class="button" id="resetBatch" type="button">重置</button>
      <div class="meta" id="batchCount">准备加载批次</div>
      <section class="batch-detail" id="batchDetail">
        <h2 id="batchDetailTitle">选择一个批次</h2>
        <div class="card-flags" id="batchDetailFlags"></div>
        <p class="meta" id="batchDetailAction">点击表格里的“选择”查看执行入口。</p>
        <code id="batchDetailHref">library.html</code>
        <div class="bulk-actions">
          <a class="button" id="openBatch" href="library.html">打开批次</a>
          <button class="button" id="copyBatchLink" type="button">复制链接</button>
          <button class="button" id="copyBatchTask" type="button">复制任务</button>
          <button class="button" id="copyBatchCommand" type="button">复制导出命令</button>
        </div>
        <div class="batch-patch">
          <strong>生成 metadata patch</strong>
          <label>字段
            <select id="batchPatchField">
              <option value="">选择要写回的字段</option>
              <option value="status">status</option>
              <option value="reading_stage">reading_stage</option>
              <option value="review_stage">review_stage</option>
              <option value="next_review">next_review</option>
              <option value="importance">importance</option>
              <option value="research_line">research_line</option>
              <option value="line_role">line_role</option>
              <option value="domains">domains</option>
              <option value="tracks">tracks</option>
              <option value="problems">problems</option>
              <option value="topics">topics</option>
              <option value="methods">methods</option>
            </select>
          </label>
          <label>新值
            <input id="batchPatchValue" type="text" placeholder="例如 reading / 2026-07-01 / KV Cache">
          </label>
          <label>列表字段模式
            <select id="batchPatchListMode">
              <option value="replace">replace</option>
              <option value="append">append</option>
              <option value="remove">remove</option>
            </select>
          </label>
          <div class="bulk-actions">
            <button class="button primary" id="downloadBatchPatch" type="button">下载 patch</button>
            <button class="button" id="copyBatchDryRun" type="button">复制 dry-run</button>
            <button class="button" id="copyBatchWrite" type="button">复制写回命令</button>
          </div>
          <code id="batchPatchPreview">选择批次、字段和值后生成 CSV patch。</code>
        </div>
        <div class="batch-samples" id="batchDetailSamples"></div>
      </section>
    </aside>
    <div>
      <section>
        <h2 class="section-title">优先批次</h2>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>风险</th><th>维度</th><th>值</th><th>论文</th><th>缺复习</th><th>缺分类</th><th>建议</th></tr></thead><tbody>{top_rows}</tbody></table></div>
      </section>
      <section>
        <h2 class="section-title">批次列表</h2>
        <div class="table-wrap"><table class="data-table batch-table"><thead><tr><th>风险</th><th>维度</th><th>批次</th><th>论文</th><th>缺口</th><th>建议动作</th><th>样例</th></tr></thead><tbody id="batchRows"></tbody></table></div>
      </section>
    </div>
  </section>
</main>
<script>
const batchPayload = {batch_json};
const batchRows = document.querySelector("#batchRows");
const batchSearch = document.querySelector("#batchSearch");
const batchDimension = document.querySelector("#batchDimension");
const batchSeverity = document.querySelector("#batchSeverity");
const batchSort = document.querySelector("#batchSort");
const batchCount = document.querySelector("#batchCount");
const batchDetailTitle = document.querySelector("#batchDetailTitle");
const batchDetailFlags = document.querySelector("#batchDetailFlags");
const batchDetailAction = document.querySelector("#batchDetailAction");
const batchDetailHref = document.querySelector("#batchDetailHref");
const batchDetailSamples = document.querySelector("#batchDetailSamples");
const openBatch = document.querySelector("#openBatch");
const copyBatchLink = document.querySelector("#copyBatchLink");
const copyBatchTask = document.querySelector("#copyBatchTask");
const copyBatchCommand = document.querySelector("#copyBatchCommand");
const batchPatchField = document.querySelector("#batchPatchField");
const batchPatchValue = document.querySelector("#batchPatchValue");
const batchPatchListMode = document.querySelector("#batchPatchListMode");
const downloadBatchPatch = document.querySelector("#downloadBatchPatch");
const copyBatchDryRun = document.querySelector("#copyBatchDryRun");
const copyBatchWrite = document.querySelector("#copyBatchWrite");
const batchPatchPreview = document.querySelector("#batchPatchPreview");
let activeBatchId = "";
const batchListFields = new Set(["domains", "tracks", "problems", "topics", "methods", "authors"]);

function batchEscape(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
}}

function batchCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function batchSearchText(item) {{
  return [
    item.dimension_label,
    item.dimension,
    item.value,
    item.severity,
    item.recommended_action,
    ...(item.sample_slugs || []),
    ...(item.sample_titles || []),
  ].join(" ").toLowerCase();
}}

function filteredBatches() {{
  const q = batchSearch.value.trim().toLowerCase();
  const items = (batchPayload.batches || []).filter(item => (
    (!q || batchSearchText(item).includes(q))
    && (!batchDimension.value || item.dimension === batchDimension.value)
    && (!batchSeverity.value || item.severity === batchSeverity.value)
  ));
  const mode = batchSort.value;
  return items.sort((left, right) => {{
    if (mode === "count") return Number(right.count || 0) - Number(left.count || 0) || String(left.value).localeCompare(String(right.value));
    if (mode === "missingReview") return Number(right.missing_review || 0) - Number(left.missing_review || 0) || Number(right.priority || 0) - Number(left.priority || 0);
    if (mode === "missingTaxonomy") return Number(right.missing_taxonomy || 0) - Number(left.missing_taxonomy || 0) || Number(right.priority || 0) - Number(left.priority || 0);
    if (mode === "latestYear") return Number(right.latest_year || 0) - Number(left.latest_year || 0) || Number(right.priority || 0) - Number(left.priority || 0);
    if (mode === "name") return `${{left.dimension_label}} ${{left.value}}`.localeCompare(`${{right.dimension_label}} ${{right.value}}`);
    return Number(right.priority || 0) - Number(left.priority || 0) || Number(right.count || 0) - Number(left.count || 0);
  }});
}}

function gapText(item) {{
  return [
    `重点 ${{item.high_importance}}`,
    `缺复习 ${{item.missing_review}}`,
    `到期 ${{item.due_review}}`,
    `缺分类 ${{item.missing_taxonomy}}`,
    `无代码 ${{item.no_code}}`,
  ].join(" · ");
}}

function renderBatchRows() {{
  const items = filteredBatches();
  if (!items.some(item => item.id === activeBatchId)) activeBatchId = items[0]?.id || "";
  batchCount.textContent = `显示 ${{items.length}} / ${{batchPayload.batch_count}} 个批次`;
  if (!items.length) {{
    batchRows.innerHTML = '<tr><td colspan="7" class="empty">没有匹配批次。</td></tr>';
    renderBatchDetail(null);
    return;
  }}
  batchRows.innerHTML = items.map(item => {{
    const samples = (item.sample_titles || []).slice(0, 4).map((title, index) => {{
      const slug = (item.sample_slugs || [])[index] || "";
      return `<div>${{batchEscape(title)}} <span class="meta">${{batchEscape(slug)}}</span></div>`;
    }}).join("");
    return `<tr data-batch-id="${{batchEscape(item.id)}}" class="${{item.id === activeBatchId ? "is-active" : ""}}">
      <td><span class="flag">${{batchEscape(item.severity)}}</span><br><button class="button batch-select" type="button" data-batch-id="${{batchEscape(item.id)}}">选择</button></td>
      <td>${{batchEscape(item.dimension_label)}}</td>
      <td><a href="${{batchEscape(item.href)}}">${{batchEscape(item.value)}}</a><div class="meta">${{batchEscape(item.dimension)}}</div></td>
      <td>${{Number(item.count || 0)}}</td>
      <td>${{batchEscape(gapText(item))}}</td>
      <td>${{batchEscape(item.recommended_action)}}<div><code>${{batchEscape(item.href)}}</code></div></td>
      <td><div class="batch-samples">${{samples || "-"}}</div></td>
    </tr>`;
  }}).join("");
  renderBatchDetail(items.find(item => item.id === activeBatchId) || items[0]);
}}

function visibleBatchRows() {{
  return filteredBatches();
}}

function activeBatch() {{
  return visibleBatchRows().find(batch => batch.id === activeBatchId) || null;
}}

function batchCsv(items) {{
  const header = ["severity", "dimension", "value", "count", "priority", "high_importance", "missing_review", "due_review", "missing_taxonomy", "no_code", "latest_year", "recommended_action", "href", "slugs", "sample_slugs"];
  const rows = items.map(item => [
    item.severity,
    item.dimension,
    item.value,
    item.count,
    item.priority,
    item.high_importance,
    item.missing_review,
    item.due_review,
    item.missing_taxonomy,
    item.no_code,
    item.latest_year,
    item.recommended_action,
    item.href,
    (item.slugs || []).join(";"),
    (item.sample_slugs || []).join(";"),
  ]);
  return [header, ...rows].map(row => row.map(batchCsvCell).join(",")).join("\\n") + "\\n";
}}

function markdownPlan(items) {{
  return items.slice(0, 40).map(item => (
    `- [ ] ${{item.dimension_label}} / ${{item.value}}: ${{item.count}} papers, risk=${{item.severity}}, action=${{item.recommended_action}} (${{item.href}})`
  )).join("\\n") + "\\n";
}}

function batchTask(item) {{
  if (!item) return "";
  const samples = (item.sample_slugs || []).length ? `\\n  - 样例：${{item.sample_slugs.join(", ")}}` : "";
  const command = item.export_command ? `\\n  - 导出：${{item.export_command}}` : "";
  const patchHint = (item.slugs || []).length ? `\\n  - patch 范围：${{item.slugs.length}} 个 slug` : "";
  return `- [ ] ${{item.dimension_label}} / ${{item.value}}：${{item.recommended_action}}\\n  - 风险：${{item.severity}}；论文：${{item.count}}；缺复习：${{item.missing_review}}；缺分类：${{item.missing_taxonomy}}\\n  - 入口：${{item.href}}${{command}}${{patchHint}}${{samples}}\\n`;
}}

function patchFilename(item) {{
  const slug = String(item?.id || "batch").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "batch";
  return `${{slug}}-metadata-patch.csv`;
}}

function patchInputPath(item) {{
  return `~/Downloads/${{patchFilename(item)}}`;
}}

function shellArg(value) {{
  const text = String(value ?? "");
  if (/^[A-Za-z0-9_./~:-]+$/.test(text)) return text;
  return `'${{text.replaceAll("'", "'\\\"'\\\"'")}}'`;
}}

function batchPatchCsv(item) {{
  const field = batchPatchField.value;
  const value = batchPatchValue.value.trim();
  if (!item || !field || !value) return "";
  const listField = batchListFields.has(field);
  const header = listField ? ["slug", field, "_list_mode"] : ["slug", field];
  const rows = (item.slugs || []).map(slug => listField ? [slug, value, batchPatchListMode.value] : [slug, value]);
  return [header, ...rows].map(row => row.map(batchCsvCell).join(",")).join("\\n") + "\\n";
}}

function batchPatchCommand(item, write) {{
  if (!item || !batchPatchField.value || !batchPatchValue.value.trim()) return "";
  const reportDir = batchPayload.report_dir || "docs";
  const command = `python3 scripts/apply_library_metadata.py ${{shellArg(reportDir)}} --input ${{shellArg(patchInputPath(item))}} --field ${{batchPatchField.value}}`;
  return write ? `${{command}} --write` : command;
}}

function renderBatchPatchState(item) {{
  const field = batchPatchField.value;
  const value = batchPatchValue.value.trim();
  const enabled = Boolean(item && field && value && (item.slugs || []).length);
  batchPatchListMode.disabled = !batchListFields.has(field);
  downloadBatchPatch.disabled = !enabled;
  copyBatchDryRun.disabled = !enabled;
  copyBatchWrite.disabled = !enabled;
  if (!item) {{
    batchPatchPreview.textContent = "选择批次、字段和值后生成 CSV patch。";
  }} else if (!field || !value) {{
    batchPatchPreview.textContent = `当前批次包含 ${{(item.slugs || []).length}} 个 slug；选择字段和值后可下载 patch。`;
  }} else {{
    batchPatchPreview.textContent = `${{patchFilename(item)}} · ${{(item.slugs || []).length}} 行 · ${{field}}=${{value}}`;
  }}
}}

function renderBatchDetail(item) {{
  copyBatchLink.disabled = !item;
  copyBatchTask.disabled = !item;
  copyBatchCommand.disabled = !item || !item.export_command;
  renderBatchPatchState(item);
  if (!item) {{
    batchDetailTitle.textContent = "选择一个批次";
    batchDetailFlags.replaceChildren();
    batchDetailAction.textContent = "当前筛选没有匹配批次。";
    batchDetailHref.textContent = "library.html";
    openBatch.href = "library.html";
    batchDetailSamples.textContent = "";
    renderBatchPatchState(null);
    return;
  }}
  batchDetailTitle.textContent = `${{item.dimension_label}} / ${{item.value}}`;
  batchDetailFlags.innerHTML = [
    item.severity,
    `${{item.count}} 篇`,
    `重点 ${{item.high_importance}}`,
    `缺复习 ${{item.missing_review}}`,
    `缺分类 ${{item.missing_taxonomy}}`,
  ].map(value => `<span class="flag">${{batchEscape(value)}}</span>`).join("");
  batchDetailAction.textContent = item.recommended_action;
  batchDetailHref.textContent = item.export_command || item.href;
  openBatch.href = item.href || "library.html";
  batchDetailSamples.innerHTML = (item.sample_titles || []).slice(0, 6).map((title, index) => {{
    const slug = (item.sample_slugs || [])[index] || "";
    return `<div>${{batchEscape(title)}} <span class="meta">${{batchEscape(slug)}}</span></div>`;
  }}).join("") || "暂无样例。";
  renderBatchPatchState(item);
}}

function downloadText(filename, text, type) {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyText(text, fallbackTitle) {{
  try {{
    await navigator.clipboard.writeText(text);
  }} catch {{
    window.prompt(fallbackTitle, text);
  }}
}}

[batchSearch, batchDimension, batchSeverity, batchSort].forEach(control => control.addEventListener("input", renderBatchRows));
batchRows.addEventListener("click", event => {{
  const button = event.target instanceof Element ? event.target.closest("[data-batch-id]") : null;
  if (!button) return;
  activeBatchId = button.dataset.batchId || "";
  renderBatchRows();
}});
document.querySelector("#downloadBatchCsv").addEventListener("click", () => downloadText("paper_batches.csv", batchCsv(visibleBatchRows()), "text/csv;charset=utf-8"));
document.querySelector("#copyBatchMarkdown").addEventListener("click", () => copyText(markdownPlan(visibleBatchRows()), "复制 Markdown 批次计划"));
copyBatchLink.addEventListener("click", () => {{
  const item = activeBatch();
  if (item) copyText(item.href, "复制批次链接");
}});
copyBatchTask.addEventListener("click", () => {{
  const item = activeBatch();
  if (item) copyText(batchTask(item), "复制批次任务");
}});
copyBatchCommand.addEventListener("click", () => {{
  const item = activeBatch();
  if (item && item.export_command) copyText(item.export_command, "复制导出命令");
}});
[batchPatchField, batchPatchValue, batchPatchListMode].forEach(control => {{
  control.addEventListener("input", () => renderBatchPatchState(activeBatch()));
}});
downloadBatchPatch.addEventListener("click", () => {{
  const item = activeBatch();
  const csv = batchPatchCsv(item);
  if (item && csv) downloadText(patchFilename(item), csv, "text/csv;charset=utf-8");
}});
copyBatchDryRun.addEventListener("click", () => {{
  const item = activeBatch();
  const command = batchPatchCommand(item, false);
  if (command) copyText(command, "复制 dry-run 命令");
}});
copyBatchWrite.addEventListener("click", () => {{
  const item = activeBatch();
  const command = batchPatchCommand(item, true);
  if (command) copyText(command, "复制写回命令");
}});
document.querySelector("#resetBatch").addEventListener("click", () => {{
  batchSearch.value = "";
  batchDimension.value = "";
  batchSeverity.value = "";
  batchSort.value = "priority";
  renderBatchRows();
}});
renderBatchRows();
</script>
"""
    (report_dir / "batch.html").write_text(page_shell("批次规划", body, extra_css=batch_css), encoding="utf-8")


def render_pivot(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_pivot_payload(papers)
    dimension_options = "".join(
        f'<option value="{html.escape(str(item["key"]), quote=True)}">{html.escape(str(item["label"]))}</option>'
        for item in payload["dimensions"]
    )
    preset_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(matrix['row_dimension']))} x {html.escape(str(matrix['column_dimension']))}</td>"
        f"<td>{len(matrix['rows'])}</td>"
        f"<td>{len(matrix['columns'])}</td>"
        f"<td>{matrix['non_empty_cells']}</td>"
        "</tr>"
        for matrix in payload["presets"]
    )
    pivot_json = json.dumps(payload, ensure_ascii=False)
    pivot_css = """
    .pivot-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      gap: 16px;
      align-items: start;
    }
    .pivot-table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      max-height: 68vh;
    }
    .pivot-table {
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .pivot-table th,
    .pivot-table td {
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 8px;
      vertical-align: top;
      min-width: 76px;
    }
    .pivot-table th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--panel);
      text-align: left;
    }
    .pivot-table th:first-child {
      left: 0;
      z-index: 2;
    }
    .pivot-row-header {
      position: sticky;
      left: 0;
      z-index: 1;
      background: var(--panel);
      min-width: 180px;
      max-width: 260px;
    }
    .pivot-cell {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--bg);
      color: var(--ink);
      font-weight: 800;
      cursor: pointer;
    }
    .pivot-cell.empty {
      color: var(--muted);
      background: transparent;
      cursor: default;
    }
    .pivot-cell.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(47, 111, 115, .16);
    }
    .pivot-detail {
      position: sticky;
      top: 82px;
      display: grid;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .pivot-detail h2 { margin: 0; font-size: 18px; }
    .pivot-paper-list {
      display: grid;
      gap: 10px;
      max-height: 56vh;
      overflow: auto;
    }
    .pivot-paper {
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--bg);
    }
    .pivot-paper h3 { margin: 0 0 4px; font-size: 14px; line-height: 1.35; }
    @media (max-width: 960px) {
      .pivot-layout { grid-template-columns: 1fr; }
      .pivot-detail { position: static; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Classification Pivot</div>
  <h1>分类透视表</h1>
  <p class="lead">把任意两个分类或状态维度交叉成矩阵，快速查看论文集中在哪些组合里。适合大量论文下发现过载方向、空白组合和需要拆分的分类。</p>
  <div class="stats">
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="coverage.html">覆盖地图</a>
    <a class="stat" href="balance.html">分类均衡</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="pivot.json">Pivot JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">维度 {len(payload["dimensions"])}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <select id="pivotRowDim" aria-label="行维度">{dimension_options}</select>
    <select id="pivotColDim" aria-label="列维度">{dimension_options}</select>
    <input id="pivotSearch" type="search" placeholder="筛选行/列值">
    <select id="pivotMinCount"><option value="1">显示非空格子</option><option value="2">至少 2 篇</option><option value="3">至少 3 篇</option><option value="5">至少 5 篇</option></select>
    <select id="pivotLimit"><option value="8">Top 8</option><option value="12" selected>Top 12</option><option value="20">Top 20</option><option value="40">Top 40</option></select>
  </div>
</div>
<main class="shell">
  <section>
    <h2 class="section-title">预设矩阵</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>矩阵</th><th>行</th><th>列</th><th>非空格子</th></tr></thead><tbody>{preset_rows}</tbody></table></div>
  </section>
  <section class="pivot-layout">
    <div>
      <div class="results-bar"><strong id="pivotCount">准备生成矩阵</strong><button id="pivotSwap" class="button" type="button">交换行列</button></div>
      <div class="pivot-table-wrap" id="pivotTableWrap"></div>
    </div>
    <aside class="pivot-detail" aria-live="polite">
      <h2 id="pivotDetailTitle">选择一个格子</h2>
      <p id="pivotDetailMeta" class="meta">点击非空格子查看论文列表。</p>
      <div id="pivotPaperList" class="pivot-paper-list"></div>
    </aside>
  </section>
</main>
<script>
const pivotData = {pivot_json};
const rowDimSelect = document.querySelector("#pivotRowDim");
const colDimSelect = document.querySelector("#pivotColDim");
const pivotSearch = document.querySelector("#pivotSearch");
const pivotMinCount = document.querySelector("#pivotMinCount");
const pivotLimit = document.querySelector("#pivotLimit");
const pivotSwap = document.querySelector("#pivotSwap");
const pivotTableWrap = document.querySelector("#pivotTableWrap");
const pivotCount = document.querySelector("#pivotCount");
const pivotDetailTitle = document.querySelector("#pivotDetailTitle");
const pivotDetailMeta = document.querySelector("#pivotDetailMeta");
const pivotPaperList = document.querySelector("#pivotPaperList");
const pivotPapersBySlug = new Map(pivotData.papers.map(paper => [paper.slug, paper]));
const dimensionByKey = new Map(pivotData.dimensions.map(item => [item.key, item]));
let activePivotCell = null;

function pivotValues(paper, dimension) {{
  return (paper.dimensions && Array.isArray(paper.dimensions[dimension])) ? paper.dimensions[dimension] : ["Unassigned"];
}}

function countDimensionValues(dimension) {{
  const counts = new Map();
  pivotData.papers.forEach(paper => {{
    pivotValues(paper, dimension).forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
  }});
  return counts;
}}

function sortedValues(counts, limit, q) {{
  return Array.from(counts.entries())
    .filter(([value]) => !q || String(value).toLowerCase().includes(q))
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .slice(0, limit)
    .map(([value]) => value);
}}

function escapePivotHtml(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[char]));
}}

function buildPivot(rowDim, colDim, limit, q) {{
  const rowCounts = countDimensionValues(rowDim);
  const colCounts = countDimensionValues(colDim);
  const rows = sortedValues(rowCounts, limit, q);
  const cols = sortedValues(colCounts, limit, q);
  const cells = new Map();
  pivotData.papers.forEach(paper => {{
    pivotValues(paper, rowDim).forEach(row => {{
      if (!rows.includes(row)) return;
      pivotValues(paper, colDim).forEach(col => {{
        if (!cols.includes(col)) return;
        const key = `${{row}}\\u0000${{col}}`;
        if (!cells.has(key)) cells.set(key, new Set());
        cells.get(key).add(paper.slug);
      }});
    }});
  }});
  return {{ rows, cols, cells, rowCounts, colCounts }};
}}

function renderPivotDetail(row, col, slugs) {{
  document.querySelectorAll(".pivot-cell").forEach(cell => cell.classList.toggle("active", cell === activePivotCell));
  const rowLabel = dimensionByKey.get(rowDimSelect.value)?.label || rowDimSelect.value;
  const colLabel = dimensionByKey.get(colDimSelect.value)?.label || colDimSelect.value;
  pivotDetailTitle.textContent = `${{rowLabel}}: ${{row}} / ${{colLabel}}: ${{col}}`;
  pivotDetailMeta.textContent = `${{slugs.length}} 篇论文`;
  if (!slugs.length) {{
    pivotPaperList.innerHTML = '<div class="empty">这个组合还没有论文。</div>';
    return;
  }}
  pivotPaperList.innerHTML = slugs
    .map(slug => pivotPapersBySlug.get(slug))
    .filter(Boolean)
    .map(paper => `<article class="pivot-paper"><h3><a href="${{escapePivotHtml(paper.href)}}">${{escapePivotHtml(paper.title_zh || paper.title || paper.slug)}}</a></h3><div class="meta">${{escapePivotHtml(paper.slug)}}</div></article>`)
    .join("");
}}

function renderPivot() {{
  const rowDim = rowDimSelect.value;
  const colDim = colDimSelect.value;
  const limit = Number(pivotLimit.value || 12);
  const minCount = Number(pivotMinCount.value || 1);
  const q = pivotSearch.value.trim().toLowerCase();
  const rowLabel = dimensionByKey.get(rowDim)?.label || rowDim;
  const colLabel = dimensionByKey.get(colDim)?.label || colDim;
  const matrix = buildPivot(rowDim, colDim, limit, q);
  let visibleCells = 0;
  const head = `<thead><tr><th>${{escapePivotHtml(rowLabel)}} \\\\ ${{escapePivotHtml(colLabel)}}</th>${{matrix.cols.map(col => `<th>${{escapePivotHtml(col)}}<div class="meta">${{matrix.colCounts.get(col) || 0}}</div></th>`).join("")}}</tr></thead>`;
  const body = matrix.rows.map(row => {{
    const cells = matrix.cols.map(col => {{
      const key = `${{row}}\\u0000${{col}}`;
      const slugs = Array.from(matrix.cells.get(key) || []);
      const count = slugs.length;
      if (count < minCount) return '<td><button class="pivot-cell empty" type="button" disabled>0</button></td>';
      visibleCells += 1;
      return `<td><button class="pivot-cell" type="button" data-row="${{escapePivotHtml(row)}}" data-col="${{escapePivotHtml(col)}}" data-slugs="${{escapePivotHtml(slugs.join("|"))}}">${{count}}</button></td>`;
    }}).join("");
    return `<tr><th class="pivot-row-header">${{escapePivotHtml(row)}}<div class="meta">${{matrix.rowCounts.get(row) || 0}}</div></th>${{cells}}</tr>`;
  }}).join("");
  pivotTableWrap.innerHTML = `<table class="pivot-table">${{head}}<tbody>${{body || '<tr><td class="empty">没有匹配的行列值。</td></tr>'}}</tbody></table>`;
  pivotCount.textContent = `${{matrix.rows.length}} 行 x ${{matrix.cols.length}} 列，${{visibleCells}} 个非空格子`;
  activePivotCell = null;
  pivotTableWrap.querySelectorAll(".pivot-cell:not(.empty)").forEach(button => {{
    button.addEventListener("click", () => {{
      activePivotCell = button;
      renderPivotDetail(button.dataset.row || "", button.dataset.col || "", (button.dataset.slugs || "").split("|").filter(Boolean));
    }});
  }});
}}

rowDimSelect.value = "research_line";
colDimSelect.value = "method";
[rowDimSelect, colDimSelect, pivotSearch, pivotMinCount, pivotLimit].forEach(control => control.addEventListener("input", renderPivot));
pivotSwap.addEventListener("click", () => {{
  const row = rowDimSelect.value;
  rowDimSelect.value = colDimSelect.value;
  colDimSelect.value = row;
  renderPivot();
}});
renderPivot();
</script>
"""
    (report_dir / "pivot.html").write_text(page_shell("分类透视表", body, extra_css=pivot_css), encoding="utf-8")


def render_taxonomy_map(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_taxonomy_map_payload(papers)
    map_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    field_options = "".join(
        f'<option value="{html.escape(str(field["key"]), quote=True)}">{html.escape(str(field["label"]))}</option>'
        for field in payload["field_order"]
    )
    recommendation_items = "".join(
        f"<li>{html.escape(str(item))}</li>"
        for item in payload["recommendations"]
    )
    cluster_card_parts = []
    for cluster in payload["clusters"]:
        top_items = (cluster.get("top_tracks") or cluster.get("top_topics") or [])[:5]
        chips = "".join(
            f'<span class="chip">{html.escape(str(item["value"]))} · {item["count"]}</span>'
            for item in top_items
        )
        cluster_card_parts.append(
            '<article class="map-cluster">'
            f'<h3><a href="{html.escape(str(cluster["href"]))}">{html.escape(str(cluster["research_line"]))}</a></h3>'
            f'<div class="meta">{cluster["count"]} 篇论文</div>'
            f'<div class="chips">{chips}</div>'
            "</article>"
        )
    cluster_cards = "".join(cluster_card_parts)
    map_css = """
    .map-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .map-layout {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .map-panel {
      position: sticky;
      top: 82px;
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .map-panel h2 { margin: 0; font-size: 18px; }
    .map-recommendations { margin: 0; padding-left: 18px; color: var(--muted); }
    .map-clusters {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .map-cluster {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .map-cluster h3 { margin: 0 0 4px; font-size: 16px; line-height: 1.3; }
    .map-node-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .map-node {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
    }
    .map-node strong {
      display: block;
      line-height: 1.35;
      margin-bottom: 5px;
    }
    .map-node[hidden], .map-edge-row[hidden] { display: none; }
    .map-table code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    @media (max-width: 940px) {
      .map-layout { grid-template-columns: 1fr; }
      .map-panel { position: static; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Taxonomy Map</div>
  <h1>分类图谱</h1>
  <p class="lead">把 research line、domain、track、problem、topic 和 method 之间的共现关系显式画出来。论文数量变多后，可以用它发现过载节点、孤立标签和应该拆分或合并的分类路径。</p>
  <div class="stats">
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="pivot.html">分类透视表</a>
    <a class="stat" href="coverage.html">覆盖地图</a>
    <a class="stat" href="taxonomy_map.json">Map JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">节点 {len(payload["nodes"])}</span>
    <span class="stat">边 {len(payload["edges"])}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="mapSearch" type="search" placeholder="搜索节点、边、slug">
    <select id="mapSource"><option value="">全部起点</option>{field_options}</select>
    <select id="mapTarget"><option value="">全部终点</option>{field_options}</select>
    <select id="mapMinCount"><option value="1">至少 1 篇</option><option value="2">至少 2 篇</option><option value="3">至少 3 篇</option><option value="5">至少 5 篇</option></select>
    <button id="downloadMapCsv" class="button" type="button">下载边 CSV</button>
  </div>
</div>
<main class="shell">
  <section class="map-summary">
    <section class="metric-card"><span>节点</span><strong>{len(payload["nodes"])}</strong><span>分类值</span></section>
    <section class="metric-card"><span>边</span><strong>{len(payload["edges"])}</strong><span>论文共现</span></section>
    <section class="metric-card"><span>研究线簇</span><strong>{len(payload["clusters"])}</strong><span>按 line 聚合</span></section>
    <section class="metric-card"><span>孤立节点</span><strong>{len(payload["isolated_nodes"])}</strong><span>需复核标签</span></section>
  </section>
  <section class="map-clusters">{cluster_cards}</section>
  <section class="map-layout">
    <aside class="map-panel">
      <h2>治理建议</h2>
      <ol class="map-recommendations">{recommendation_items}</ol>
      <div class="meta" id="mapResultCount">准备加载图谱</div>
    </aside>
    <div>
      <section>
        <h2 class="section-title">高频节点</h2>
        <div id="mapNodeGrid" class="map-node-grid"></div>
      </section>
      <section>
        <h2 class="section-title">共现边</h2>
        <div class="table-wrap"><table class="data-table map-table"><thead><tr><th>起点</th><th>终点</th><th>论文</th><th>样例</th><th>入口</th></tr></thead><tbody id="mapEdgeRows"></tbody></table></div>
      </section>
    </div>
  </section>
</main>
<script>
const taxonomyMapData = {map_json};
const mapSearch = document.querySelector("#mapSearch");
const mapSource = document.querySelector("#mapSource");
const mapTarget = document.querySelector("#mapTarget");
const mapMinCount = document.querySelector("#mapMinCount");
const mapResultCount = document.querySelector("#mapResultCount");
const mapNodeGrid = document.querySelector("#mapNodeGrid");
const mapEdgeRows = document.querySelector("#mapEdgeRows");
const downloadMapCsv = document.querySelector("#downloadMapCsv");
const mapTitles = taxonomyMapData.slug_titles || {{}};

function mapEscape(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[char]));
}}

function mapCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function edgeSearchText(edge) {{
  return [
    edge.source_field,
    edge.source_value,
    edge.target_field,
    edge.target_value,
    ...(edge.sample_slugs || []),
  ].join(" ").toLowerCase();
}}

function filteredEdges() {{
  const q = mapSearch.value.trim().toLowerCase();
  const minCount = Number(mapMinCount.value || 1);
  return (taxonomyMapData.edges || []).filter(edge =>
    edge.count >= minCount
    && (!mapSource.value || edge.source_field === mapSource.value)
    && (!mapTarget.value || edge.target_field === mapTarget.value)
    && (!q || edgeSearchText(edge).includes(q))
  );
}}

function filteredNodes(edges) {{
  const q = mapSearch.value.trim().toLowerCase();
  const visibleIds = new Set(edges.flatMap(edge => [edge.source, edge.target]));
  return (taxonomyMapData.nodes || [])
    .filter(node => visibleIds.has(node.id) && (!q || `${{node.field}} ${{node.value}} ${{(node.sample_slugs || []).join(" ")}}`.toLowerCase().includes(q)))
    .sort((a, b) => b.count - a.count || a.field.localeCompare(b.field) || a.value.localeCompare(b.value))
    .slice(0, 24);
}}

function renderMap() {{
  const edges = filteredEdges();
  const nodes = filteredNodes(edges);
  mapResultCount.textContent = `${{nodes.length}} 个节点 / ${{edges.length}} 条边`;
  mapNodeGrid.innerHTML = nodes.map(node => `
    <article class="map-node">
      <strong><a href="${{mapEscape(node.href)}}">${{mapEscape(node.value)}}</a></strong>
      <div class="meta">${{mapEscape(node.label)}} · ${{node.count}} 篇</div>
      <div class="chips">${{(node.sample_slugs || []).slice(0, 3).map(slug => `<span class="chip">${{mapEscape(slug)}}</span>`).join("")}}</div>
    </article>
  `).join("") || '<div class="empty">没有匹配节点。</div>';
  mapEdgeRows.innerHTML = edges.slice(0, 160).map(edge => {{
    const samples = (edge.sample_slugs || []).slice(0, 4).map(slug => `${{slug}} · ${{mapTitles[slug] || ""}}`).join("; ");
    return `<tr class="map-edge-row">
      <td><span class="flag">${{mapEscape(edge.source_field)}}</span><div><a href="${{mapEscape(edge.href)}}">${{mapEscape(edge.source_value)}}</a></div></td>
      <td><span class="flag">${{mapEscape(edge.target_field)}}</span><div>${{mapEscape(edge.target_value)}}</div></td>
      <td>${{edge.count}}</td>
      <td>${{mapEscape(samples || "-")}}</td>
      <td><a href="${{mapEscape(edge.href)}}">打开队列</a></td>
    </tr>`;
  }}).join("") || '<tr><td colspan="5" class="empty">没有匹配边。</td></tr>';
}}

function downloadVisibleEdges() {{
  const rows = filteredEdges();
  if (!rows.length) {{
    window.alert("当前筛选没有边。");
    return;
  }}
  const header = ["source_field", "source_value", "target_field", "target_value", "count", "sample_slugs", "href"];
  const csv = [header, ...rows.map(edge => [
    edge.source_field,
    edge.source_value,
    edge.target_field,
    edge.target_value,
    edge.count,
    (edge.sample_slugs || []).join(";"),
    edge.href,
  ])].map(row => row.map(mapCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "taxonomy_map_edges.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

[mapSearch, mapSource, mapTarget, mapMinCount].forEach(control => control.addEventListener("input", renderMap));
downloadMapCsv.addEventListener("click", downloadVisibleEdges);
renderMap();
</script>
"""
    (report_dir / "taxonomy_map.html").write_text(page_shell("分类图谱", body, extra_css=map_css), encoding="utf-8")


def render_compare(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_compare_payload(papers)
    compare_json = json.dumps(payload, ensure_ascii=False)
    compare_css = """
    .compare-layout {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .compare-picker {
      position: sticky;
      top: 82px;
      display: grid;
      gap: 12px;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .compare-paper-list {
      display: grid;
      gap: 8px;
      max-height: 58vh;
      overflow: auto;
    }
    .compare-paper-button {
      width: 100%;
      display: grid;
      gap: 4px;
      text-align: left;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--bg);
      color: var(--ink);
      cursor: pointer;
    }
    .compare-paper-button.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(47, 111, 115, .16);
    }
    .selected-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .selected-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      color: var(--muted);
      font-size: 13px;
    }
    .selected-chip button {
      width: 22px;
      height: 22px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--bg);
      color: var(--muted);
      cursor: pointer;
    }
    .compare-table-wrap {
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      max-height: 72vh;
    }
    .compare-table {
      width: max-content;
      min-width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    .compare-table th,
    .compare-table td {
      min-width: 190px;
      max-width: 320px;
      padding: 10px;
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      vertical-align: top;
    }
    .compare-table th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--panel);
      text-align: left;
    }
    .compare-field {
      position: sticky;
      left: 0;
      z-index: 2;
      min-width: 150px;
      background: var(--panel);
      font-weight: 800;
    }
    .compare-title-cell strong {
      display: block;
      line-height: 1.35;
      margin-bottom: 6px;
    }
    .compare-value-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .compare-empty { color: var(--muted); }
    @media (max-width: 980px) {
      .compare-layout { grid-template-columns: 1fr; }
      .compare-picker { position: static; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Paper Compare</div>
  <h1>论文对比</h1>
  <p class="lead">把同一研究线、同一方向或临时筛选出的论文并排比较，快速看清分类、状态、复习计划、分数和代码线索的差异。</p>
  <div class="stats">
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="pivot.html">分类透视表</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="workflow.html">工作流中心</a>
    <a class="stat" href="compare.json">Compare JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">推荐集合 {len(payload["suggested_sets"])}</span>
  </div>
</header>
<main class="shell compare-layout">
  <aside class="compare-picker">
    <input id="compareSearch" type="search" placeholder="搜索标题、slug、研究线、分类">
    <select id="compareLine"><option value="">全部研究线</option></select>
    <select id="compareTrack"><option value="">全部方向</option></select>
    <select id="compareStatus"><option value="">全部状态</option></select>
    <select id="comparePreset"><option value="">载入推荐集合</option></select>
    <div class="results-bar"><strong id="compareAvailableCount">0 篇</strong><button id="compareClear" class="button" type="button">清空</button></div>
    <div id="comparePaperList" class="compare-paper-list"></div>
  </aside>
  <section>
    <div class="results-bar">
      <strong id="compareSelectedCount">已选 0 篇</strong>
      <div class="results-actions">
        <button id="compareCopyLink" class="button" type="button">复制当前链接</button>
      </div>
    </div>
    <div id="compareSelectedStrip" class="selected-strip"></div>
    <div id="compareTableWrap" class="compare-table-wrap"></div>
  </section>
</main>
<script>
const compareData = {compare_json};
const comparePapers = compareData.papers || [];
const compareFields = compareData.fields || [];
const compareBySlug = new Map(comparePapers.map(paper => [paper.slug, paper]));
const compareSearch = document.querySelector("#compareSearch");
const compareLine = document.querySelector("#compareLine");
const compareTrack = document.querySelector("#compareTrack");
const compareStatus = document.querySelector("#compareStatus");
const comparePreset = document.querySelector("#comparePreset");
const compareClear = document.querySelector("#compareClear");
const compareCopyLink = document.querySelector("#compareCopyLink");
const compareAvailableCount = document.querySelector("#compareAvailableCount");
const compareSelectedCount = document.querySelector("#compareSelectedCount");
const comparePaperList = document.querySelector("#comparePaperList");
const compareSelectedStrip = document.querySelector("#compareSelectedStrip");
const compareTableWrap = document.querySelector("#compareTableWrap");
let selectedSlugs = [];

function compareEscape(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[char]));
}}

function uniqueSorted(values) {{
  return Array.from(new Set(values.map(value => String(value || "").trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}}

function fillOptions(select, values, placeholder) {{
  const current = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  values.forEach(value => select.appendChild(new Option(value, value)));
  select.value = values.includes(current) ? current : "";
}}

function paperSearchText(paper) {{
  return [
    paper.slug,
    paper.title,
    paper.title_zh,
    paper.title_en,
    paper.research_line,
    paper.line_role,
    ...(paper.domains || []),
    ...(paper.tracks || []),
    ...(paper.problems || []),
    ...(paper.topics || []),
    ...(paper.methods || []),
  ].join(" ").toLowerCase();
}}

function paperMatchesFilters(paper) {{
  const q = compareSearch.value.trim().toLowerCase();
  return (!q || paperSearchText(paper).includes(q))
    && (!compareLine.value || paper.research_line === compareLine.value)
    && (!compareTrack.value || (paper.tracks || []).includes(compareTrack.value))
    && (!compareStatus.value || paper.status === compareStatus.value);
}}

function readCompareState() {{
  const params = new URLSearchParams(window.location.search);
  selectedSlugs = (params.get("slugs") || "")
    .split(",")
    .map(slug => slug.trim())
    .filter(slug => compareBySlug.has(slug));
  if (!selectedSlugs.length) {{
    const firstSet = (compareData.suggested_sets || []).find(item => (item.slugs || []).length);
    selectedSlugs = firstSet ? firstSet.slugs.slice(0, 4) : comparePapers.slice(0, 3).map(paper => paper.slug);
  }}
}}

function writeCompareState() {{
  const url = new URL(window.location.href);
  if (selectedSlugs.length) url.searchParams.set("slugs", selectedSlugs.join(","));
  else url.searchParams.delete("slugs");
  window.history.replaceState(null, "", url);
}}

function togglePaper(slug) {{
  if (selectedSlugs.includes(slug)) selectedSlugs = selectedSlugs.filter(item => item !== slug);
  else selectedSlugs = [...selectedSlugs, slug];
  writeCompareState();
  renderCompare();
}}

function formatCompareValue(value, key) {{
  if (Array.isArray(value)) {{
    if (!value.length) return '<span class="compare-empty">-</span>';
    return `<div class="compare-value-list">${{value.map(item => `<span class="chip">${{compareEscape(item)}}</span>`).join("")}}</div>`;
  }}
  if (key === "has_code") return value ? "有" : "无";
  if (key === "code_url" && value) return `<a href="${{compareEscape(value)}}">code</a>`;
  if (!value && value !== 0) return '<span class="compare-empty">-</span>';
  return compareEscape(value);
}}

function renderAvailablePapers() {{
  const papers = comparePapers.filter(paperMatchesFilters);
  compareAvailableCount.textContent = `${{papers.length}} 篇`;
  comparePaperList.innerHTML = papers.map(paper => {{
    const active = selectedSlugs.includes(paper.slug);
    const labels = [paper.research_line, paper.status, paper.year].filter(Boolean).join(" · ");
    return `<button class="compare-paper-button${{active ? " active" : ""}}" type="button" data-slug="${{compareEscape(paper.slug)}}">
      <strong>${{compareEscape(paper.title_zh || paper.title || paper.slug)}}</strong>
      <span class="meta">${{compareEscape(labels)}}</span>
      <span class="meta">${{compareEscape(paper.slug)}}</span>
    </button>`;
  }}).join("") || '<div class="empty">没有匹配论文。</div>';
  comparePaperList.querySelectorAll("[data-slug]").forEach(button => button.addEventListener("click", () => togglePaper(button.dataset.slug)));
}}

function renderSelectedStrip() {{
  const papers = selectedSlugs.map(slug => compareBySlug.get(slug)).filter(Boolean);
  compareSelectedCount.textContent = `已选 ${{papers.length}} 篇`;
  compareSelectedStrip.innerHTML = papers.map(paper => `
    <span class="selected-chip">${{compareEscape(paper.slug)}}<button type="button" data-remove="${{compareEscape(paper.slug)}}" aria-label="移除 ${{compareEscape(paper.slug)}}">x</button></span>
  `).join("");
  compareSelectedStrip.querySelectorAll("[data-remove]").forEach(button => button.addEventListener("click", () => togglePaper(button.dataset.remove)));
}}

function renderCompareTable() {{
  const papers = selectedSlugs.map(slug => compareBySlug.get(slug)).filter(Boolean);
  if (!papers.length) {{
    compareTableWrap.innerHTML = '<div class="empty">请选择要对比的论文。</div>';
    return;
  }}
  const header = `<thead><tr><th class="compare-field">字段</th>${{papers.map(paper => `
    <th class="compare-title-cell"><strong><a href="${{compareEscape(paper.href)}}">${{compareEscape(paper.title_zh || paper.title || paper.slug)}}</a></strong><span class="meta">${{compareEscape(paper.slug)}}</span></th>
  `).join("")}}</tr></thead>`;
  const rows = compareFields.map(field => `
    <tr>
      <td class="compare-field">${{compareEscape(field.label)}}<div class="meta">${{compareEscape(field.group)}}</div></td>
      ${{papers.map(paper => `<td>${{formatCompareValue(paper[field.key], field.key)}}</td>`).join("")}}
    </tr>
  `).join("");
  compareTableWrap.innerHTML = `<table class="compare-table">${{header}}<tbody>${{rows}}</tbody></table>`;
}}

function renderCompare() {{
  renderAvailablePapers();
  renderSelectedStrip();
  renderCompareTable();
}}

fillOptions(compareLine, uniqueSorted(comparePapers.map(paper => paper.research_line)), "全部研究线");
fillOptions(compareTrack, uniqueSorted(comparePapers.flatMap(paper => paper.tracks || [])), "全部方向");
fillOptions(compareStatus, uniqueSorted(comparePapers.map(paper => paper.status)), "全部状态");
(compareData.suggested_sets || []).forEach((set, index) => {{
  comparePreset.appendChild(new Option(`${{set.name}} (${{(set.slugs || []).length}})`, String(index)));
}});
readCompareState();
[compareSearch, compareLine, compareTrack, compareStatus].forEach(control => control.addEventListener("input", renderCompare));
comparePreset.addEventListener("input", () => {{
  const preset = (compareData.suggested_sets || [])[Number(comparePreset.value)];
  if (!preset) return;
  selectedSlugs = (preset.slugs || []).filter(slug => compareBySlug.has(slug));
  writeCompareState();
  renderCompare();
}});
compareClear.addEventListener("click", () => {{
  selectedSlugs = [];
  writeCompareState();
  renderCompare();
}});
compareCopyLink.addEventListener("click", async () => {{
  writeCompareState();
  try {{
    await navigator.clipboard.writeText(window.location.href);
    compareCopyLink.textContent = "已复制";
    setTimeout(() => compareCopyLink.textContent = "复制当前链接", 1200);
  }} catch (error) {{
    window.prompt("复制当前链接", window.location.href);
  }}
}});
renderCompare();
</script>
"""
    (report_dir / "compare.html").write_text(page_shell("论文对比", body, extra_css=compare_css), encoding="utf-8")


def render_cluster_label_group(labels: dict[str, list[dict[str, Any]]]) -> str:
    parts = []
    for field in ("domains", "tracks", "problems", "topics", "methods"):
        values = labels.get(field, [])[:4] if isinstance(labels, dict) else []
        if not values:
            continue
        chips = "".join(
            f'<span class="cluster-chip">{html.escape(str(item.get("value") or ""))} {html.escape(str(item.get("count") or ""))}</span>'
            for item in values
        )
        parts.append(f'<div><span class="meta">{html.escape(field)}</span><div class="cluster-tags">{chips}</div></div>')
    return "".join(parts) or '<span class="meta">-</span>'


def render_cluster_papers(papers: list[dict[str, Any]]) -> str:
    if not papers:
        return '<span class="meta">-</span>'
    return '<div class="cluster-papers">' + "".join(
        f'<a href="{html.escape(str(paper.get("href") or ""))}">{html.escape(str(paper.get("title") or paper.get("slug") or ""))}</a>'
        for paper in papers[:5]
    ) + "</div>"


def render_clusters(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_clusters_payload(papers)
    risk_label = {"high": "高", "medium": "中", "low": "低"}
    cluster_rows = []
    for cluster in payload["clusters"]:
        split_text = "; ".join(
            f"{item['field']}:{item['value']} ({item['count']})"
            for item in cluster.get("split_candidates", [])[:5]
        )
        status_text = ", ".join(f"{item['value']}:{item['count']}" for item in cluster.get("status_counts", []))
        role_text = ", ".join(f"{item['value']}:{item['count']}" for item in cluster.get("role_counts", []))
        search_text = " ".join(
            [
                str(cluster.get("name") or ""),
                str(cluster.get("owner") or ""),
                str(cluster.get("team") or ""),
                split_text,
                status_text,
                role_text,
                " ".join(str(item.get("value") or "") for values in cluster.get("top_labels", {}).values() for item in values),
            ]
        ).lower()
        cluster_rows.append(
            "<tr class=\"cluster-row\" "
            f"data-risk=\"{html.escape(str(cluster.get('risk') or ''), quote=True)}\" "
            f"data-owner=\"{html.escape(str(cluster.get('owner') or ''), quote=True)}\" "
            f"data-search=\"{html.escape(search_text, quote=True)}\">"
            f"<td><span class=\"flag\">{html.escape(risk_label.get(str(cluster.get('risk')), str(cluster.get('risk') or '-')))}</span><div class=\"meta\">{html.escape(', '.join(cluster.get('risk_reasons', [])[:3]))}</div></td>"
            f"<td><a href=\"{html.escape(str(cluster.get('href') or 'library.html'))}\"><strong>{html.escape(str(cluster.get('name') or 'Unassigned'))}</strong></a><div class=\"meta\">{html.escape(str(cluster.get('owner') or cluster.get('team') or 'Unassigned'))}</div></td>"
            f"<td>{cluster.get('count', 0)}<div class=\"meta\">{float(cluster.get('share') or 0):.0%}</div></td>"
            f"<td>{html.escape(str(cluster.get('year_span') or '-'))}</td>"
            f"<td>{html.escape(role_text or '-')}<div class=\"meta\">{html.escape(status_text or '-')}</div></td>"
            f"<td>{render_cluster_label_group(cluster.get('top_labels', {}))}</td>"
            f"<td>{html.escape(split_text or '-')}</td>"
            f"<td>{render_cluster_papers(cluster.get('representative_papers', []))}</td>"
            "</tr>"
        )
    owner_values = sorted({str(cluster.get("owner") or "") for cluster in payload["clusters"] if cluster.get("owner")})
    owner_options = "".join(f'<option value="{html.escape(owner)}">{html.escape(owner)}</option>' for owner in owner_values)
    recommendations = "".join(f"<li>{html.escape(item)}</li>" for item in payload["recommendations"])
    clusters_css = """
    .cluster-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .cluster-controls {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .cluster-tags, .cluster-papers {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .cluster-chip, .cluster-papers a {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
      font-size: 12px;
    }
    .cluster-row[hidden] { display: none; }
    .cluster-table td { vertical-align: top; }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Research Clusters</div>
  <h1>研究簇驾驶舱</h1>
  <p class="lead">按研究线聚合论文簇，显示 owner、角色/状态分布、top taxonomy labels、代表论文和拆分候选。适合在论文数量增长后判断哪些方向需要拆分、合并或补充分类。</p>
  <div class="stats">
    <a class="stat" href="clusters.json">Clusters JSON</a>
    <a class="stat" href="routing.html">分类路由器</a>
    <a class="stat" href="taxonomy_map.html">分类图谱</a>
    <a class="stat" href="coverage.html">覆盖地图</a>
    <a class="stat" href="ownership.html">Owner 工作台</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">簇 {payload["cluster_count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="cluster-summary">
    <section class="metric-card"><span>研究簇</span><strong>{payload["cluster_count"]}</strong><span>按 research_line 聚合</span></section>
    <section class="metric-card"><span>最大簇占比</span><strong>{float(payload["largest_cluster_share"]):.0%}</strong><span>过高时考虑拆分</span></section>
    <section class="metric-card"><span>高风险簇</span><strong>{sum(1 for cluster in payload["clusters"] if cluster.get("risk") == "high")}</strong><span>优先治理</span></section>
    <section class="metric-card"><span>中风险簇</span><strong>{sum(1 for cluster in payload["clusters"] if cluster.get("risk") == "medium")}</strong><span>关注演化</span></section>
  </section>
  <section>
    <h2 class="section-title">治理建议</h2>
    <ul>{recommendations}</ul>
  </section>
  <section>
    <h2 class="section-title">研究簇</h2>
    <div class="cluster-controls">
      <input id="clusterSearch" type="search" placeholder="搜索研究线、标签、owner">
      <select id="clusterRisk"><option value="">全部风险</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select>
      <select id="clusterOwner"><option value="">全部 owner</option>{owner_options}</select>
      <button id="downloadClustersCsv" class="button" type="button">下载 CSV</button>
      <button id="copyClusterPlan" class="button" type="button">复制治理计划</button>
      <span class="stat" id="clusterCount">0 clusters</span>
    </div>
    <div class="table-wrap"><table class="data-table cluster-table"><thead><tr><th>风险</th><th>研究簇</th><th>论文</th><th>年份</th><th>角色 / 状态</th><th>Top labels</th><th>拆分候选</th><th>代表论文</th></tr></thead><tbody id="clusterRows">{"".join(cluster_rows)}</tbody></table></div>
  </section>
</main>
<script>
const clusterRows = Array.from(document.querySelectorAll("#clusterRows tr"));
const clusterSearch = document.querySelector("#clusterSearch");
const clusterRisk = document.querySelector("#clusterRisk");
const clusterOwner = document.querySelector("#clusterOwner");
const clusterCount = document.querySelector("#clusterCount");
const downloadClustersCsv = document.querySelector("#downloadClustersCsv");
const copyClusterPlan = document.querySelector("#copyClusterPlan");

function clusterCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function visibleClusterRows() {{
  return clusterRows.filter(row => !row.hidden);
}}

function renderClusterRows() {{
  const q = clusterSearch.value.trim().toLowerCase();
  const risk = clusterRisk.value;
  const owner = clusterOwner.value;
  clusterRows.forEach(row => {{
    const hitSearch = !q || (row.dataset.search || "").includes(q);
    const hitRisk = !risk || row.dataset.risk === risk;
    const hitOwner = !owner || row.dataset.owner === owner;
    row.hidden = !(hitSearch && hitRisk && hitOwner);
  }});
  clusterCount.textContent = `${{visibleClusterRows().length}} clusters`;
}}

function downloadClusters() {{
  const header = ["risk", "cluster", "papers", "years", "roles_status", "labels", "split_candidates", "representatives"];
  const rows = visibleClusterRows().map(row => Array.from(row.children).map(cell => cell.textContent.trim().replace(/\\s+/g, " ")));
  if (!rows.length) return;
  const csv = [header, ...rows].map(row => row.map(clusterCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "research_clusters.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyPlan() {{
  const lines = visibleClusterRows().map(row => {{
    const cells = Array.from(row.children).map(cell => cell.textContent.trim().replace(/\\s+/g, " "));
    return `- [ ] ${{cells[1]}}: risk=${{cells[0]}}, papers=${{cells[2]}}, split=${{cells[6]}}`;
  }});
  const text = lines.join("\\n");
  try {{
    await navigator.clipboard.writeText(text);
    copyClusterPlan.textContent = "已复制";
    setTimeout(() => copyClusterPlan.textContent = "复制治理计划", 1200);
  }} catch (error) {{
    window.prompt("复制治理计划", text);
  }}
}}

[clusterSearch, clusterRisk, clusterOwner].forEach(control => control.addEventListener("input", renderClusterRows));
downloadClustersCsv.addEventListener("click", downloadClusters);
copyClusterPlan.addEventListener("click", copyPlan);
renderClusterRows();
</script>
"""
    (report_dir / "clusters.html").write_text(page_shell("研究簇驾驶舱", body, extra_css=clusters_css), encoding="utf-8")


def render_roadmap(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_roadmap_payload(papers)
    roadmap_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    owners = sorted({item["owner"] for item in payload["roadmaps"] if item.get("owner") and item.get("owner") != "unassigned"})
    owner_options = "".join(f'<option value="{html.escape(owner, quote=True)}">{html.escape(owner)}</option>' for owner in owners)
    action_rows = "".join(
        "<tr>"
        f"<td>{int(action.get('priority') or 0)}</td>"
        f'<td><a href="{html.escape(page_query_href("library.html", line=str(action.get("line") or "")))}">{html.escape(str(action.get("line") or ""))}</a></td>'
        f"<td>{html.escape(str(action.get('type') or ''))}</td>"
        f"<td>{html.escape(str(action.get('label') or ''))}</td>"
        f'<td><a href="{html.escape(str(action.get("href") or ""))}">打开</a></td>'
        "</tr>"
        for action in payload["actions"][:20]
    ) or '<tr><td colspan="5" class="empty">暂无路线图行动。</td></tr>'
    roadmap_css = """
    .roadmap-layout {
      display: grid;
      grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
      gap: 16px;
      align-items: start;
    }
    .roadmap-panel {
      position: sticky;
      top: 82px;
      display: grid;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .roadmap-card {
      display: grid;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
      margin-bottom: 14px;
    }
    .roadmap-card header {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 0;
    }
    .roadmap-card h2 {
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
    }
    .roadmap-score {
      min-width: 48px;
      height: 42px;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #edf3f1;
      color: var(--accent);
      font-weight: 800;
    }
    .roadmap-sections {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
    }
    .roadmap-mini {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: color-mix(in srgb, var(--panel) 88%, white);
    }
    .roadmap-mini h3 {
      margin: 0 0 6px;
      font-size: 14px;
      line-height: 1.3;
    }
    .roadmap-list {
      margin: 0;
      padding-left: 18px;
      color: var(--muted);
    }
    .roadmap-list li { margin: 3px 0; }
    .roadmap-card[hidden] { display: none; }
    @media (max-width: 920px) {
      .roadmap-layout { grid-template-columns: 1fr; }
      .roadmap-panel { position: static; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Research Roadmap</div>
  <h1>研究路线图</h1>
  <p class="lead">把每条 research line 组织成可执行路线：阶段覆盖、里程碑年份、代表论文、维护风险和下一步行动。适合论文库变大后做季度规划或开源协作分工。</p>
  <div class="stats">
    <a class="stat" href="roadmap.json">Roadmap JSON</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="clusters.html">研究簇</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="intake.html">批量导入</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">研究线 {payload["line_count"]}</span>
    <span class="stat">行动 {len(payload["actions"])}</span>
  </div>
</header>
<main class="shell">
  <section class="roadmap-layout">
    <aside class="roadmap-panel">
      <input id="roadmapSearch" type="search" placeholder="搜索研究线、owner、标签、论文">
      <select id="roadmapRisk"><option value="">全部风险</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select>
      <select id="roadmapOwner"><option value="">全部 owner</option>{owner_options}</select>
      <select id="roadmapRoleGap"><option value="">全部角色覆盖</option><option value="yes">有缺口</option><option value="no">角色完整</option></select>
      <button class="button" id="downloadRoadmapCsv" type="button">下载路线 CSV</button>
      <button class="button" id="copyRoadmapMarkdown" type="button">复制 Markdown 路线图</button>
      <button class="button" id="resetRoadmap" type="button">重置</button>
      <div class="meta" id="roadmapCount">准备加载路线图</div>
    </aside>
    <div>
      <section>
        <h2 class="section-title">优先行动</h2>
        <div class="table-wrap"><table class="data-table"><thead><tr><th>优先级</th><th>研究线</th><th>类型</th><th>行动</th><th>入口</th></tr></thead><tbody>{action_rows}</tbody></table></div>
      </section>
      <section>
        <h2 class="section-title">研究线路线</h2>
        <div id="roadmapCards"></div>
      </section>
    </div>
  </section>
</main>
<script>
const roadmapPayload = {roadmap_json};
const roadmapSearch = document.querySelector("#roadmapSearch");
const roadmapRisk = document.querySelector("#roadmapRisk");
const roadmapOwner = document.querySelector("#roadmapOwner");
const roadmapRoleGap = document.querySelector("#roadmapRoleGap");
const roadmapCount = document.querySelector("#roadmapCount");
const roadmapCards = document.querySelector("#roadmapCards");

function roadmapEscape(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
}}

function roadmapCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function roadmapSearchText(item) {{
  return [
    item.line,
    item.owner,
    item.team,
    item.cadence,
    ...(item.missing_roles || []),
    ...(item.top_topics || []).map(topic => topic.name),
    ...(item.top_methods || []).map(method => method.name),
    ...(item.representative_papers || []).flatMap(paper => [paper.slug, paper.title, paper.title_zh]),
    ...(item.actions || []).map(action => action.label),
  ].join(" ").toLowerCase();
}}

function filteredRoadmaps() {{
  const q = roadmapSearch.value.trim().toLowerCase();
  return (roadmapPayload.roadmaps || []).filter(item => (
    (!q || roadmapSearchText(item).includes(q))
    && (!roadmapRisk.value || item.risk === roadmapRisk.value)
    && (!roadmapOwner.value || item.owner === roadmapOwner.value)
    && (!roadmapRoleGap.value || (roadmapRoleGap.value === "yes" ? (item.missing_roles || []).length : !(item.missing_roles || []).length))
  ));
}}

function chips(values) {{
  return (values || []).map(value => `<span class="chip">${{roadmapEscape(value)}}</span>`).join("");
}}

function countChips(values) {{
  return (values || []).map(item => `<span class="chip">${{roadmapEscape(item.name)}} ${{item.count}}</span>`).join("");
}}

function renderRoadmapCards() {{
  const items = filteredRoadmaps();
  roadmapCount.textContent = `显示 ${{items.length}} / ${{roadmapPayload.line_count}} 条研究线`;
  roadmapCards.innerHTML = items.map(item => {{
    const milestones = (item.milestones || []).map(milestone => `${{milestone.year}}:${{milestone.count}}`).join(" · ") || "-";
    const papers = (item.representative_papers || []).map(paper => `<li><a href="${{roadmapEscape(paper.href)}}">${{roadmapEscape(paper.title_zh || paper.title || paper.slug)}}</a> <span class="meta">${{roadmapEscape(paper.role)}} · ${{roadmapEscape(paper.year)}}</span></li>`).join("") || '<li class="meta">暂无代表论文。</li>';
    const actions = (item.actions || []).slice(0, 5).map(action => `<li><a href="${{roadmapEscape(action.href)}}">${{roadmapEscape(action.label)}}</a></li>`).join("");
    return `<article class="roadmap-card" data-risk="${{roadmapEscape(item.risk)}}">
      <header>
        <div>
          <h2><a href="${{roadmapEscape(item.href)}}">${{roadmapEscape(item.line)}}</a></h2>
          <div class="meta">${{roadmapEscape(item.owner || "unassigned")}}${{item.team ? " · " + roadmapEscape(item.team) : ""}}${{item.cadence ? " · " + roadmapEscape(item.cadence) : ""}}</div>
        </div>
        <div class="roadmap-score">${{item.score}}</div>
      </header>
      <div class="card-flags"><span class="flag">${{roadmapEscape(item.risk)}}</span><span class="flag">${{item.count}} 篇</span><span class="flag">${{roadmapEscape(item.first_year || "-")}}-${{roadmapEscape(item.latest_year || "-")}}</span></div>
      <div class="roadmap-sections">
        <section class="roadmap-mini"><h3>角色覆盖</h3><div class="chips">${{chips(Object.entries(item.role_counts || {{}}).map(([role, count]) => `${{role}} ${{count}}`))}}</div><div class="meta">缺口：${{(item.missing_roles || []).join(", ") || "-"}}</div></section>
        <section class="roadmap-mini"><h3>里程碑</h3><div class="meta">${{roadmapEscape(milestones)}}</div></section>
        <section class="roadmap-mini"><h3>Top Topics</h3><div class="chips">${{countChips(item.top_topics)}}</div></section>
        <section class="roadmap-mini"><h3>Top Methods</h3><div class="chips">${{countChips(item.top_methods)}}</div></section>
      </div>
      <div class="roadmap-sections">
        <section class="roadmap-mini"><h3>代表论文</h3><ol class="roadmap-list">${{papers}}</ol></section>
        <section class="roadmap-mini"><h3>下一步</h3><ol class="roadmap-list">${{actions || '<li class="meta">保持观察。</li>'}}</ol></section>
      </div>
    </article>`;
  }}).join("") || '<div class="empty">没有匹配路线。</div>';
}}

function roadmapsToCsv(items) {{
  const header = ["line", "owner", "team", "risk", "score", "count", "first_year", "latest_year", "missing_roles", "top_action"];
  return [header, ...items.map(item => [
    item.line,
    item.owner,
    item.team,
    item.risk,
    item.score,
    item.count,
    item.first_year || "",
    item.latest_year || "",
    (item.missing_roles || []).join(";"),
    ((item.actions || [])[0] || {{}}).label || "",
  ])].map(row => row.map(roadmapCsvCell).join(",")).join("\\n") + "\\n";
}}

function markdownPlan(items) {{
  return items.map(item => {{
    const actions = (item.actions || []).slice(0, 5).map(action => `- [ ] ${{action.label}}`).join("\\n");
    return `## ${{item.line}}\\n- Owner: ${{item.owner || "unassigned"}}\\n- Risk: ${{item.risk}} / score ${{item.score}}\\n- Papers: ${{item.count}}\\n- Missing roles: ${{(item.missing_roles || []).join(", ") || "-"}}\\n${{actions}}`;
  }}).join("\\n\\n");
}}

function downloadText(filename, text, type) {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyText(text, fallbackTitle) {{
  try {{
    await navigator.clipboard.writeText(text);
  }} catch {{
    window.prompt(fallbackTitle, text);
  }}
}}

[roadmapSearch, roadmapRisk, roadmapOwner, roadmapRoleGap].forEach(control => control.addEventListener("input", renderRoadmapCards));
document.querySelector("#downloadRoadmapCsv").addEventListener("click", () => downloadText("research_roadmap.csv", roadmapsToCsv(filteredRoadmaps()), "text/csv;charset=utf-8"));
document.querySelector("#copyRoadmapMarkdown").addEventListener("click", () => copyText(markdownPlan(filteredRoadmaps()), "复制 Markdown 路线图"));
document.querySelector("#resetRoadmap").addEventListener("click", () => {{
  roadmapSearch.value = "";
  roadmapRisk.value = "";
  roadmapOwner.value = "";
  roadmapRoleGap.value = "";
  renderRoadmapCards();
}});
renderRoadmapCards();
</script>
"""
    (report_dir / "roadmap.html").write_text(page_shell("研究路线图", body, extra_css=roadmap_css), encoding="utf-8")


def render_scale(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_scale_payload(report_dir, papers, inbox_items)
    status_label = {
        "ready": "规模健康",
        "watch": "需要观察",
        "needs_governance": "需要治理",
    }.get(str(payload["readiness_label"]), str(payload["readiness_label"]))
    severity_label = {"high": "高", "medium": "中", "low": "低", "none": "无"}
    bottleneck_rows = "".join(
        "<tr>"
        f'<td><span class="flag">{html.escape(severity_label.get(str(item["severity"]), str(item["severity"])))}</span></td>'
        f"<td>{html.escape(str(item['area']))}</td>"
        f"<td>{html.escape(str(item['signal']))}</td>"
        f"<td>{html.escape(str(item['recommendation']))}</td>"
        f'<td><a href="{html.escape(str(item["href"]))}">打开</a></td>'
        f"<td>{'<code>' + html.escape(str(item.get('command') or '')) + '</code>' if item.get('command') else '-'}</td>"
        "</tr>"
        for item in payload["bottlenecks"]
    )
    projection_rows = "".join(
        "<tr>"
        f"<td>{item['paper_count']}</td>"
        f"<td>{format_bytes(int(item['search_index_bytes']))}</td>"
        f"<td>{format_bytes(int(item['papers_json_bytes']))}</td>"
        f"<td>{format_bytes(int(item['taxonomy_map_bytes']))}</td>"
        f"<td>{item['estimated_actions']}</td>"
        f"<td>{html.escape(str(item['recommended_mode']))}</td>"
        "</tr>"
        for item in payload["capacity_projection"]
    )
    resource_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["href"]))}</a></td>'
        f"<td>{'<span class=\"flag\">ok</span>' if item.get('exists') else '<span class=\"flag\">missing</span>'}</td>"
        f"<td>{format_bytes(int(item.get('size_bytes') or 0))}</td>"
        "</tr>"
        for item in payload["resource_sizes"]
    )
    tier_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['tier']))}</td>"
        f"<td>{html.escape(str(item['paper_range']))}</td>"
        f"<td>{html.escape(str(item['mode']))}</td>"
        f"<td>{html.escape(str(item['priority']))}</td>"
        "</tr>"
        for item in payload["scale_tiers"]
    )
    queue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(group))}</td>"
        f"<td>{html.escape(str(name))}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for group, queues in payload["queue_sizes"].items()
        for name, count in (queues.items() if isinstance(queues, dict) else [(group, queues)])
    )
    scale_css = """
    .scale-status {
      display: grid;
      grid-template-columns: minmax(220px, 300px) 1fr;
      gap: 16px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .scale-score {
      display: grid;
      place-items: center;
      min-height: 210px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      text-align: center;
      padding: 18px;
    }
    .scale-score strong {
      display: block;
      font-size: 58px;
      line-height: 1;
    }
    .scale-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
    }
    .scale-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }
    .scale-controls select, .scale-controls input { max-width: 220px; }
    .scale-table code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    .bottleneck-row[hidden] { display: none; }
    @media (max-width: 860px) {
      .scale-status { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Scale Readiness</div>
  <h1>规模就绪</h1>
  <p class="lead">从大库运维角度检查论文数量增长后的容量、索引体量、分类复杂度和治理队列。适合决定什么时候拆分类、分派 owner、做桌面缓存或分页索引。</p>
  <div class="stats">
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="taxonomy_map.html">分类图谱</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="release.html">发布摘要</a>
    <a class="stat" href="scale.json">Scale JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">状态 {html.escape(status_label)}</span>
  </div>
</header>
<main class="shell">
  <section class="scale-status">
    <div class="scale-score">
      <div>
        <span class="meta">Readiness score</span>
        <strong>{payload["readiness_score"]}</strong>
        <span class="flag">{html.escape(status_label)}</span>
      </div>
    </div>
    <div class="scale-summary">
      <section class="metric-card"><span>研究线</span><strong>{payload["line_count"]}</strong><span>最大占比 {payload["largest_line_share"]:.0%}</span></section>
      <section class="metric-card"><span>分类节点</span><strong>{payload["taxonomy_node_count"]}</strong><span>图谱节点</span></section>
      <section class="metric-card"><span>分类边</span><strong>{payload["taxonomy_edge_count"]}</strong><span>{payload["taxonomy_edges_per_paper"]} / paper</span></section>
      <section class="metric-card"><span>状态体系</span><strong>{payload["status_workflow"]["workflow_count"]}</strong><span>active {html.escape(str(payload["status_workflow"]["active"] or "-"))}</span></section>
      <section class="metric-card"><span>风险项</span><strong>{len(payload["bottlenecks"])}</strong><span>按优先级排序</span></section>
    </div>
  </section>
  <section>
    <h2 class="section-title">动态状态体系</h2>
    <div class="metric-grid">
      <section class="metric-card"><span>Active workflow</span><strong>{html.escape(str(payload["status_workflow"]["active"] or "-"))}</strong><span><a href="workflow.html">打开工作流中心</a></span></section>
      <section class="metric-card"><span>Status 候选</span><strong>{payload["status_workflow"]["status_count"]}</strong><span>当前状态列/筛选选项</span></section>
      <section class="metric-card"><span>Reading stage</span><strong>{payload["status_workflow"]["reading_stage_count"]}</strong><span>阅读深度候选</span></section>
      <section class="metric-card"><span>Review stage</span><strong>{payload["status_workflow"]["review_stage_count"]}</strong><span>复习阶段候选</span></section>
    </div>
  </section>
  <section>
    <h2 class="section-title">规模瓶颈</h2>
    <div class="scale-controls">
      <input id="scaleSearch" type="search" placeholder="搜索 area、signal、建议">
      <select id="scaleSeverity"><option value="">全部优先级</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option><option value="none">无</option></select>
      <button id="downloadScaleRisks" class="button" type="button">下载风险 CSV</button>
    </div>
    <div class="table-wrap"><table class="data-table scale-table"><thead><tr><th>优先级</th><th>区域</th><th>信号</th><th>建议</th><th>入口</th><th>命令</th></tr></thead><tbody id="scaleRiskRows">{bottleneck_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">容量投影</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>论文数</th><th>Search index</th><th>Papers JSON</th><th>Taxonomy map</th><th>行动项估计</th><th>建议模式</th></tr></thead><tbody>{projection_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">核心资源体量</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>资源</th><th>状态</th><th>大小</th></tr></thead><tbody>{resource_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">扩展阶段</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>阶段</th><th>规模</th><th>模式</th><th>优先事项</th></tr></thead><tbody>{tier_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">队列规模</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>分组</th><th>队列</th><th>数量</th></tr></thead><tbody>{queue_rows}</tbody></table></div>
  </section>
</main>
<script>
const scaleRows = Array.from(document.querySelectorAll("#scaleRiskRows tr"));
const scaleSearch = document.querySelector("#scaleSearch");
const scaleSeverity = document.querySelector("#scaleSeverity");
const downloadScaleRisks = document.querySelector("#downloadScaleRisks");

function scaleCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function visibleScaleRows() {{
  return scaleRows.filter(row => !row.hidden);
}}

function renderScaleRows() {{
  const q = scaleSearch.value.trim().toLowerCase();
  const severity = scaleSeverity.value;
  scaleRows.forEach(row => {{
    const cells = Array.from(row.children).map(cell => cell.textContent || "");
    const rowSeverity = row.children[0]?.textContent?.trim() || "";
    const hitSeverity = !severity || (
      (severity === "high" && rowSeverity === "高")
      || (severity === "medium" && rowSeverity === "中")
      || (severity === "low" && rowSeverity === "低")
      || (severity === "none" && rowSeverity === "无")
    );
    const hitSearch = !q || cells.join(" ").toLowerCase().includes(q);
    row.hidden = !(hitSeverity && hitSearch);
  }});
}}

function downloadRisks() {{
  const header = ["severity", "area", "signal", "recommendation", "entry", "command"];
  const rows = visibleScaleRows().map(row => Array.from(row.children).map(cell => cell.textContent.trim()));
  if (!rows.length) {{
    window.alert("当前没有匹配风险项。");
    return;
  }}
  const csv = [header, ...rows].map(row => row.map(scaleCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "scale_bottlenecks.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

[scaleSearch, scaleSeverity].forEach(control => control.addEventListener("input", renderScaleRows));
downloadScaleRisks.addEventListener("click", downloadRisks);
renderScaleRows();
</script>
"""
    (report_dir / "scale.html").write_text(page_shell("规模就绪", body, extra_css=scale_css), encoding="utf-8")


OWNERSHIP_QUEUE_LABELS = {
    "missing_taxonomy": "缺分类",
    "needs_review_plan": "缺复习",
    "due_review": "复习到期",
    "freshness_due": "时效到期",
    "stale": "过期",
    "no_code_observation": "缺代码",
}


def render_queue_summary(queues: Any) -> str:
    if not isinstance(queues, dict):
        return '<span class="meta">-</span>'
    visible = [(key, int(value or 0)) for key, value in queues.items() if int(value or 0) > 0]
    if not visible:
        return '<span class="meta">无待办</span>'
    return '<div class="queue-stack">' + "".join(
        f'<span class="queue-pill">{html.escape(OWNERSHIP_QUEUE_LABELS.get(str(key), str(key)))} <strong>{value}</strong></span>'
        for key, value in visible
    ) + "</div>"


def render_owner_line_links(lines: Any) -> str:
    if not isinstance(lines, list) or not lines:
        return '<span class="meta">-</span>'
    links = []
    for line in lines[:6]:
        if not isinstance(line, dict):
            continue
        href = str(line.get("href") or "library.html")
        label = str(line.get("line") or "Unassigned")
        count = int(line.get("count") or 0)
        links.append(f'<a href="{html.escape(href)}">{html.escape(label)} · {count}</a>')
    if len(lines) > 6:
        links.append(f'<span class="meta">+{len(lines) - 6}</span>')
    return '<div class="line-links">' + "".join(links) + "</div>"


def render_ownership(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_ownership_payload(papers)
    risk_label = {"high": "高", "medium": "中", "low": "低"}
    owner_rows = "".join(
        "<tr class=\"ownership-row\" "
        f"data-risk=\"{html.escape(str(owner.get('risk') or ''))}\" "
        f"data-team=\"{html.escape(str(owner.get('team') or ''))}\" "
        f"data-search=\"{html.escape(' '.join([str(owner.get('owner') or ''), str(owner.get('team') or ''), ' '.join(str(line.get('line') or '') for line in owner.get('lines', []))]).lower())}\">"
        f"<td><span class=\"flag\">{html.escape(risk_label.get(str(owner.get('risk')), str(owner.get('risk') or '-')))}</span></td>"
        f"<td><strong>{html.escape(str(owner.get('owner') or 'Unassigned'))}</strong><div class=\"meta\">{html.escape(str(owner.get('team') or '-'))}</div></td>"
        f"<td>{owner.get('line_count', 0)}</td>"
        f"<td>{owner.get('paper_count', 0)}</td>"
        f"<td>{owner.get('risk_points', 0)}</td>"
        f"<td>{render_queue_summary(owner.get('queues', {}))}</td>"
        f"<td>{render_owner_line_links(owner.get('lines', []))}</td>"
        "</tr>"
        for owner in payload["owners"]
    )
    line_rows = "".join(
        "<tr class=\"ownership-line-row\" "
        f"data-risk=\"{html.escape(str(line.get('risk') or ''))}\" "
        f"data-team=\"{html.escape(str(line.get('team') or ''))}\" "
        f"data-search=\"{html.escape(' '.join([str(line.get('line') or ''), str(line.get('owner') or ''), str(line.get('team') or ''), ' '.join(str(slug) for slug in line.get('sample_slugs', []))]).lower())}\">"
        f"<td><span class=\"flag\">{html.escape(risk_label.get(str(line.get('risk')), str(line.get('risk') or '-')))}</span></td>"
        f"<td><a href=\"{html.escape(str(line.get('href') or 'library.html'))}\">{html.escape(str(line.get('line') or 'Unassigned'))}</a><div class=\"meta\">{html.escape(str(line.get('cadence') or '-'))}</div></td>"
        f"<td>{html.escape(str(line.get('owner') or 'Unassigned'))}<div class=\"meta\">{html.escape(str(line.get('team') or '-'))}</div></td>"
        f"<td>{line.get('count', 0)}</td>"
        f"<td>{line.get('avg_importance', 0)}</td>"
        f"<td>{line.get('code_coverage', 0)}%</td>"
        f"<td>{render_queue_summary(line.get('queues', {}))}</td>"
        "</tr>"
        for line in payload["lines"]
    )
    team_values = sorted({str(owner.get("team") or "") for owner in payload["owners"] if owner.get("team")})
    team_options = "".join(f'<option value="{html.escape(team)}">{html.escape(team)}</option>' for team in team_values)
    ownership_css = """
    .ownership-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }
    .ownership-toolbar input,
    .ownership-toolbar select {
      max-width: 220px;
    }
    .ownership-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .queue-stack {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .queue-pill {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      background: var(--panel);
      font-size: 12px;
      white-space: nowrap;
    }
    .line-links {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .line-links a {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
      font-size: 12px;
    }
    .ownership-row[hidden],
    .ownership-line-row[hidden] { display: none; }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Ownership Operations</div>
  <h1>Owner 工作台</h1>
  <p class="lead">按研究线 owner 聚合论文数量、分类缺口、复习计划、报告时效和代码观察缺口。论文变多后可以直接按负责人分派治理队列。</p>
  <div class="stats">
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="coverage.html">覆盖地图</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="ownership.json">Ownership JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">Owners {payload["owner_count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="ownership-grid">
    <section class="metric-card"><span>Owner 数</span><strong>{payload["owner_count"]}</strong><span>含未分派队列</span></section>
    <section class="metric-card"><span>研究线</span><strong>{len(payload["lines"])}</strong><span>按风险排序</span></section>
    <section class="metric-card"><span>未分派线</span><strong>{payload["unassigned_line_count"]}</strong><span>需要补 research_line_owners</span></section>
    <section class="metric-card"><span>高风险 owner</span><strong>{sum(1 for owner in payload["owners"] if owner.get("risk") == "high")}</strong><span>优先处理</span></section>
  </section>
  <section>
    <h2 class="section-title">Owner 队列</h2>
    <div class="ownership-toolbar">
      <input id="ownershipSearch" type="search" placeholder="搜索 owner、team、研究线">
      <select id="ownershipRisk"><option value="">全部风险</option><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select>
      <select id="ownershipTeam"><option value="">全部 team</option>{team_options}</select>
      <button id="downloadOwnershipCsv" class="button" type="button">下载 CSV</button>
      <button id="copyOwnershipChecklist" class="button" type="button">复制清单</button>
      <span class="stat" id="ownershipCount">0 owner</span>
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>风险</th><th>Owner</th><th>线</th><th>论文</th><th>风险分</th><th>队列</th><th>研究线</th></tr></thead><tbody id="ownershipRows">{owner_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">研究线明细</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>风险</th><th>研究线</th><th>Owner</th><th>论文</th><th>重要性</th><th>代码覆盖</th><th>队列</th></tr></thead><tbody id="ownershipLineRows">{line_rows}</tbody></table></div>
  </section>
</main>
<script>
const ownershipRows = Array.from(document.querySelectorAll("#ownershipRows tr"));
const ownershipLineRows = Array.from(document.querySelectorAll("#ownershipLineRows tr"));
const ownershipSearch = document.querySelector("#ownershipSearch");
const ownershipRisk = document.querySelector("#ownershipRisk");
const ownershipTeam = document.querySelector("#ownershipTeam");
const ownershipCount = document.querySelector("#ownershipCount");
const downloadOwnershipCsv = document.querySelector("#downloadOwnershipCsv");
const copyOwnershipChecklist = document.querySelector("#copyOwnershipChecklist");

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function rowMatches(row, q, risk, team) {{
  const search = row.dataset.search || "";
  return (!q || search.includes(q)) && (!risk || row.dataset.risk === risk) && (!team || row.dataset.team === team);
}}

function visibleOwnerRows() {{
  return ownershipRows.filter(row => !row.hidden);
}}

function renderOwnershipRows() {{
  const q = ownershipSearch.value.trim().toLowerCase();
  const risk = ownershipRisk.value;
  const team = ownershipTeam.value;
  ownershipRows.forEach(row => row.hidden = !rowMatches(row, q, risk, team));
  ownershipLineRows.forEach(row => row.hidden = !rowMatches(row, q, risk, team));
  ownershipCount.textContent = `${{visibleOwnerRows().length}} owner`;
}}

function downloadOwnership() {{
  const rows = visibleOwnerRows().map(row => Array.from(row.children).map(cell => cell.textContent.trim()));
  if (!rows.length) {{
    window.alert("当前没有匹配 owner。");
    return;
  }}
  const header = ["risk", "owner", "line_count", "paper_count", "risk_points", "queues", "lines"];
  const csv = [header, ...rows].map(row => row.map(csvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ownership_workload.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyChecklist() {{
  const lines = visibleOwnerRows().map(row => {{
    const cells = Array.from(row.children).map(cell => cell.textContent.trim().replace(/\\s+/g, " "));
    return `- [ ] ${{cells[1]}}: risk=${{cells[0]}}, papers=${{cells[3]}}, queues=${{cells[5]}}`;
  }});
  if (!lines.length) {{
    window.alert("当前没有匹配 owner。");
    return;
  }}
  const text = lines.join("\\n");
  try {{
    await navigator.clipboard.writeText(text);
    copyOwnershipChecklist.textContent = "已复制";
    setTimeout(() => copyOwnershipChecklist.textContent = "复制清单", 1200);
  }} catch (error) {{
    window.prompt("复制 owner 清单", text);
  }}
}}

[ownershipSearch, ownershipRisk, ownershipTeam].forEach(control => control.addEventListener("input", renderOwnershipRows));
downloadOwnershipCsv.addEventListener("click", downloadOwnership);
copyOwnershipChecklist.addEventListener("click", copyChecklist);
renderOwnershipRows();
</script>
"""
    (report_dir / "ownership.html").write_text(page_shell("Owner 工作台", body, extra_css=ownership_css), encoding="utf-8")


def render_routing(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_routing_payload(papers)
    routing_data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    sample_options = "".join(
        f'<option value="{html.escape(str(paper.get("title_en") or paper.get("title") or paper["slug"]), quote=True)}">{html.escape(str(paper.get("title_zh") or paper["slug"]))}</option>'
        for paper in papers[:20]
    )
    routing_css = """
    .routing-layout {
      display: grid;
      grid-template-columns: minmax(280px, 420px) 1fr;
      gap: 16px;
      align-items: start;
    }
    .routing-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .routing-panel textarea {
      min-height: 240px;
      resize: vertical;
    }
    .routing-panel label {
      display: grid;
      gap: 6px;
      margin-bottom: 12px;
    }
    .routing-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }
    .routing-score {
      font-variant-numeric: tabular-nums;
      color: var(--accent);
      font-weight: 700;
    }
    .routing-results {
      display: grid;
      gap: 16px;
    }
    .routing-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .routing-tags a,
    .routing-tags span {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 7px;
      background: var(--panel);
      color: var(--text);
      text-decoration: none;
      font-size: 12px;
    }
    .routing-patch {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f8faf9;
      padding: 12px;
    }
    @media (max-width: 900px) {
      .routing-layout { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Classification Router</div>
  <h1>新论文分类路由器</h1>
  <p class="lead">粘贴论文标题、摘要或方法描述，页面会根据当前知识库的研究线、taxonomy 标签和相似论文给出可解释的分类建议。适合新增论文前先做 intake triage。</p>
  <div class="stats">
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="taxonomy_map.html">分类图谱</a>
    <a class="stat" href="routing.json">Routing JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">研究线 {payload["line_count"]}</span>
    <span class="stat">标签 {payload["label_count"]}</span>
  </div>
</header>
<main class="shell routing-layout">
  <section class="routing-panel">
    <label><span>标题或方法名</span><input id="routingTitle" list="routingSamples" placeholder="Paste paper title or method name"></label>
    <datalist id="routingSamples">{sample_options}</datalist>
    <label><span>摘要 / introduction 片段 / 备注</span><textarea id="routingAbstract" placeholder="Paste abstract, intro paragraph, or your notes"></textarea></label>
    <label><span>关键词提示</span><input id="routingKeywords" placeholder="attention, diffusion, serving, kernel"></label>
    <div class="routing-actions">
      <button id="runRouting" class="button" type="button">推荐分类</button>
      <button id="copyRoutingPatch" class="button" type="button">复制 frontmatter patch</button>
      <button id="clearRouting" class="button" type="button">清空</button>
    </div>
    <p class="meta">推荐只作为 intake 初筛；写入前仍建议在 `docs/library.html` 或 `docs/taxonomy.html` 里复核。</p>
  </section>
  <section class="routing-results">
    <section>
      <h2 class="section-title">推荐研究线</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Score</th><th>研究线</th><th>Owner</th><th>匹配词</th><th>入口</th></tr></thead><tbody id="routingLineRows"></tbody></table></div>
    </section>
    <section>
      <h2 class="section-title">推荐标签</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>字段</th><th>标签</th><th>Score</th><th>样本数</th><th>匹配词</th></tr></thead><tbody id="routingLabelRows"></tbody></table></div>
    </section>
    <section>
      <h2 class="section-title">相似论文</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>Score</th><th>论文</th><th>研究线</th><th>匹配词</th></tr></thead><tbody id="routingPaperRows"></tbody></table></div>
    </section>
    <section>
      <h2 class="section-title">建议 patch</h2>
      <pre class="routing-patch" id="routingPatch">等待输入。</pre>
    </section>
  </section>
</main>
<script>
const routingData = {routing_data_json};
const routingStopwords = new Set(routingData.tokenizer?.stopwords || []);
const fieldLabels = {{
  domains: "domains",
  tracks: "tracks",
  problems: "problems",
  topics: "topics",
  methods: "methods",
}};
const routingTitle = document.querySelector("#routingTitle");
const routingAbstract = document.querySelector("#routingAbstract");
const routingKeywords = document.querySelector("#routingKeywords");
const routingLineRows = document.querySelector("#routingLineRows");
const routingLabelRows = document.querySelector("#routingLabelRows");
const routingPaperRows = document.querySelector("#routingPaperRows");
const routingPatch = document.querySelector("#routingPatch");
const runRouting = document.querySelector("#runRouting");
const copyRoutingPatch = document.querySelector("#copyRoutingPatch");
const clearRouting = document.querySelector("#clearRouting");

function escapeHtml(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[char]));
}}

function normalizeAsciiToken(value) {{
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim()
    .split(/\\s+/)
    .filter(Boolean)
    .map(token => token.length > 3 && token.endsWith("s") ? token.slice(0, -1) : token)
    .filter(token => token && !routingStopwords.has(token));
}}

function routingTokens(text) {{
  const counts = new Map();
  const matches = String(text || "").match(/[A-Za-z0-9][A-Za-z0-9.+-]{{1,}}|[\\u4e00-\\u9fff]{{2,}}/g) || [];
  for (const raw of matches) {{
    if (/^[A-Za-z0-9.+-]+$/.test(raw)) {{
      const parts = normalizeAsciiToken(raw);
      for (const part of parts) {{
        if (part.length >= 3 || part === "ai" || part === "kv") counts.set(part, (counts.get(part) || 0) + 1);
      }}
      if (parts.length > 1) {{
        const phrase = parts.join(" ");
        counts.set(phrase, (counts.get(phrase) || 0) + 2);
      }}
    }} else {{
      const token = raw.toLowerCase();
      if (token.length >= 2) counts.set(token, (counts.get(token) || 0) + 1);
    }}
  }}
  return counts;
}}

function scoreProfile(profile, inputTerms, nameValue = "") {{
  let score = 0;
  const matched = [];
  for (const item of profile.terms || []) {{
    const count = inputTerms.get(item.term) || 0;
    if (count) {{
      score += count * Number(item.weight || 0);
      matched.push(`${{item.term}}:${{Math.round(Number(item.weight || 0))}}`);
    }}
  }}
  const inputText = [routingTitle.value, routingAbstract.value, routingKeywords.value].join(" ").toLowerCase();
  const name = String(nameValue || "").toLowerCase();
  if (name && inputText.includes(name)) score += 40;
  return {{ ...profile, score, matched: matched.slice(0, 8) }};
}}

function ranked(items, inputTerms, nameKey, limit = 5) {{
  return items
    .map(item => scoreProfile(item, inputTerms, item[nameKey]))
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || Number(b.count || 0) - Number(a.count || 0))
    .slice(0, limit);
}}

function tagsHtml(values) {{
  return `<div class="routing-tags">${{values.map(value => `<span>${{escapeHtml(value)}}</span>`).join("")}}</div>`;
}}

function renderRouting() {{
  const text = [routingTitle.value, routingAbstract.value, routingKeywords.value].join(" ");
  const inputTerms = routingTokens(text);
  const lines = ranked(routingData.line_profiles || [], inputTerms, "line", 5);
  const labels = ranked(routingData.label_profiles || [], inputTerms, "value", 12);
  const papers = ranked(routingData.paper_signatures || [], inputTerms, "title", 8);
  routingLineRows.innerHTML = lines.length ? lines.map(item => `
    <tr>
      <td class="routing-score">${{Math.round(item.score)}}</td>
      <td><strong>${{escapeHtml(item.line)}}</strong><div class="routing-tags">${{(item.top_labels || []).slice(0, 5).map(label => `<span>${{escapeHtml(label.label)}} ${{label.count}}</span>`).join("")}}</div></td>
      <td>${{escapeHtml(item.owner || item.team || "-")}}<div class="meta">${{escapeHtml(item.team || "")}}</div></td>
      <td>${{tagsHtml(item.matched)}}</td>
      <td><a href="${{escapeHtml(item.href)}}">打开</a></td>
    </tr>
  `).join("") : '<tr><td colspan="5" class="empty">输入更多标题、摘要或关键词后再推荐。</td></tr>';
  routingLabelRows.innerHTML = labels.length ? labels.map(item => `
    <tr>
      <td>${{escapeHtml(fieldLabels[item.field] || item.field)}}</td>
      <td><a href="${{escapeHtml(item.href)}}">${{escapeHtml(item.value)}}</a></td>
      <td class="routing-score">${{Math.round(item.score)}}</td>
      <td>${{item.count || 0}}</td>
      <td>${{tagsHtml(item.matched)}}</td>
    </tr>
  `).join("") : '<tr><td colspan="5" class="empty">暂无标签建议。</td></tr>';
  routingPaperRows.innerHTML = papers.length ? papers.map(item => `
    <tr>
      <td class="routing-score">${{Math.round(item.score)}}</td>
      <td><a href="${{escapeHtml(item.href)}}">${{escapeHtml(item.title)}}</a><div class="meta">${{escapeHtml(item.slug)}}</div></td>
      <td>${{escapeHtml(item.research_line || "-")}}</td>
      <td>${{tagsHtml(item.matched)}}</td>
    </tr>
  `).join("") : '<tr><td colspan="4" class="empty">暂无相似论文。</td></tr>';
  const byField = new Map();
  for (const item of labels) {{
    if (!byField.has(item.field)) byField.set(item.field, []);
    byField.get(item.field).push(item.value);
  }}
  const bestLine = lines[0]?.line || "";
  const patchLines = [
    bestLine ? `research_line: "${{bestLine}}"` : "research_line: ",
    "domains:",
    ...(byField.get("domains") || []).slice(0, 2).map(value => `  - ${{value}}`),
    "tracks:",
    ...(byField.get("tracks") || []).slice(0, 2).map(value => `  - ${{value}}`),
    "problems:",
    ...(byField.get("problems") || []).slice(0, 2).map(value => `  - ${{value}}`),
    "topics:",
    ...(byField.get("topics") || []).slice(0, 4).map(value => `  - ${{value}}`),
    "methods:",
    ...(byField.get("methods") || []).slice(0, 4).map(value => `  - ${{value}}`),
  ];
  routingPatch.textContent = patchLines.join("\\n");
}}

runRouting.addEventListener("click", renderRouting);
[routingTitle, routingAbstract, routingKeywords].forEach(control => control.addEventListener("input", renderRouting));
copyRoutingPatch.addEventListener("click", async () => {{
  const text = routingPatch.textContent || "";
  try {{
    await navigator.clipboard.writeText(text);
    copyRoutingPatch.textContent = "已复制";
    setTimeout(() => copyRoutingPatch.textContent = "复制 frontmatter patch", 1200);
  }} catch (error) {{
    window.prompt("复制 frontmatter patch", text);
  }}
}});
clearRouting.addEventListener("click", () => {{
  routingTitle.value = "";
  routingAbstract.value = "";
  routingKeywords.value = "";
  renderRouting();
}});
renderRouting();
</script>
"""
    (report_dir / "routing.html").write_text(page_shell("新论文分类路由器", body, extra_css=routing_css), encoding="utf-8")


def render_onboarding(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_onboarding_payload(report_dir, papers, inbox_items)
    check_rows = "".join(
        "<tr>"
        f"<td><span class=\"flag\">{'ok' if item.get('exists') else 'missing'}</span></td>"
        f"<td><a href=\"{html.escape(str(item.get('href') or ''))}\">{html.escape(str(item.get('label') or ''))}</a></td>"
        f"<td><code>{html.escape(str(item.get('path') or ''))}</code></td>"
        "</tr>"
        for item in payload["readiness_checks"]
    )
    path_cards = "".join(
        f"""<article class="onboarding-card" data-search="{html.escape(' '.join([str(path.get('title') or ''), str(path.get('id') or ''), ' '.join(path.get('recommended_pages', []))]).lower(), quote=True)}">
  <div class="card-head">
    <span class="flag">{html.escape(str(path.get("id") or ""))}</span>
    <a href="{html.escape(str(path.get("entry") or "index.html"))}">{html.escape(str(path.get("title") or ""))}</a>
  </div>
  <p class="meta">Issue / PR: <code>{html.escape(str(path.get("issue_template") or ""))}</code></p>
  <p class="meta">Contract: <a href="{html.escape(str(path.get("contract") or ""))}">{html.escape(str(path.get("contract") or ""))}</a></p>
  <div class="chips">{"".join(f'<a class="chip" href="{html.escape(page)}">{html.escape(page)}</a>' for page in path.get("recommended_pages", []))}</div>
  <div class="command-stack">{"".join(f'<button class="button copy-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command)}</button>' for command in path.get("commands", []))}</div>
</article>"""
        for path in payload["contribution_paths"]
    )
    step_rows = "".join(
        "<tr>"
        f"<td>{step['order']}</td>"
        f"<td><a href=\"{html.escape(str(step['href']))}\">{html.escape(str(step['title']))}</a><div class=\"meta\">{html.escape(str(step['why']))}</div></td>"
        f"<td>{'<button class=\"button copy-command\" type=\"button\" data-command=\"' + html.escape(str(step.get('command')), quote=True) + '\">' + html.escape(str(step.get('command'))) + '</button>' if step.get('command') else '-'}</td>"
        "</tr>"
        for step in payload["quickstart_steps"]
    )
    contract_rows = "".join(
        "<tr>"
        f"<td><a href=\"{html.escape(str(contract['href']))}\">{html.escape(str(contract['href']))}</a></td>"
        f"<td>{html.escape(str(contract['description']))}</td>"
        "</tr>"
        for contract in payload["contracts"]
    )
    command_rows = "".join(
        "<tr>"
        f"<td><a href=\"{html.escape(str(command['href']))}\">{html.escape(str(command['label']))}</a></td>"
        f"<td><button class=\"button copy-command\" type=\"button\" data-command=\"{html.escape(str(command['command']), quote=True)}\">{html.escape(str(command['command']))}</button></td>"
        "</tr>"
        for command in payload["command_groups"]
    )
    bootstrap = "".join(f'<a class="stat" href="{html.escape(file)}">{html.escape(file)}</a>' for file in payload["bootstrap_files"])
    onboarding_css = """
    .onboarding-hero {
      display: grid;
      grid-template-columns: minmax(220px, 280px) 1fr;
      gap: 16px;
      align-items: stretch;
      margin-bottom: 18px;
    }
    .readiness-score {
      display: grid;
      place-items: center;
      min-height: 210px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      text-align: center;
      padding: 18px;
    }
    .readiness-score strong {
      display: block;
      font-size: 54px;
      line-height: 1;
    }
    .onboarding-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }
    .onboarding-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
      display: grid;
      gap: 10px;
    }
    .card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .card-head a {
      font-weight: 700;
      color: var(--text);
      text-decoration: none;
    }
    .command-stack {
      display: grid;
      gap: 6px;
    }
    .command-stack .button,
    td .button {
      justify-content: flex-start;
      white-space: normal;
      text-align: left;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
    .onboarding-toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .onboarding-card[hidden] { display: none; }
    @media (max-width: 820px) {
      .onboarding-hero { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Open Source Onboarding</div>
  <h1>开源上手控制台</h1>
  <p class="lead">把贡献入口、质量门、数据契约和常用命令收在一个页面里。适合新贡献者、第二台机器、未来桌面软件或 DMG 首次打开时快速理解这个知识库怎么维护。</p>
  <div class="stats">
    <a class="stat" href="onboarding.json">Onboarding JSON</a>
    <a class="stat" href="catalog.html">数据目录</a>
    <a class="stat" href="release.html">发布摘要</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="routing.html">分类路由器</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">Inbox {payload["inbox_count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="onboarding-hero">
    <div class="readiness-score">
      <div>
        <span class="meta">Open-source readiness</span>
        <strong>{html.escape(str(payload["readiness_score"]))}</strong>
        <span class="flag">{payload["readiness_passed"]}/{payload["readiness_total"]} checks</span>
      </div>
    </div>
    <div class="metric-grid">
      <section class="metric-card"><span>贡献路径</span><strong>{len(payload["contribution_paths"])}</strong><span>intake / quality / taxonomy / release</span></section>
      <section class="metric-card"><span>契约文件</span><strong>{len(payload["contracts"])}</strong><span>schema 和模板</span></section>
      <section class="metric-card"><span>启动数据</span><strong>{len(payload["bootstrap_files"])}</strong><span>给脚本或桌面端读取</span></section>
      <section class="metric-card"><span>常用命令</span><strong>{len(payload["command_groups"])}</strong><span>可一键复制</span></section>
    </div>
  </section>
  <section>
    <h2 class="section-title">贡献路径</h2>
    <div class="onboarding-toolbar">
      <input id="onboardingSearch" type="search" placeholder="搜索 intake、taxonomy、release">
      <span class="stat" id="onboardingCount">0 paths</span>
    </div>
    <div class="onboarding-grid" id="onboardingPaths">{path_cards}</div>
  </section>
  <section>
    <h2 class="section-title">快速开始</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>#</th><th>步骤</th><th>命令</th></tr></thead><tbody>{step_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">开源就绪检查</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>状态</th><th>资产</th><th>路径</th></tr></thead><tbody>{check_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">数据契约</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>用途</th></tr></thead><tbody>{contract_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">常用命令</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>场景</th><th>命令</th></tr></thead><tbody>{command_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">启动数据</h2>
    <div class="stats">{bootstrap}</div>
  </section>
</main>
<script>
const onboardingCards = Array.from(document.querySelectorAll(".onboarding-card"));
const onboardingSearch = document.querySelector("#onboardingSearch");
const onboardingCount = document.querySelector("#onboardingCount");

function renderOnboardingCards() {{
  const q = onboardingSearch.value.trim().toLowerCase();
  onboardingCards.forEach(card => {{
    card.hidden = q && !(card.dataset.search || "").includes(q);
  }});
  onboardingCount.textContent = `${{onboardingCards.filter(card => !card.hidden).length}} paths`;
}}

async function copyCommand(command, button) {{
  try {{
    await navigator.clipboard.writeText(command);
    const original = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => button.textContent = original, 1200);
  }} catch (error) {{
    window.prompt("复制命令", command);
  }}
}}

document.querySelectorAll(".copy-command").forEach(button => {{
  button.addEventListener("click", () => copyCommand(button.dataset.command || "", button));
}});
onboardingSearch.addEventListener("input", renderOnboardingCards);
renderOnboardingCards();
</script>
"""
    (report_dir / "onboarding.html").write_text(page_shell("开源上手控制台", body, extra_css=onboarding_css), encoding="utf-8")


def render_catalog(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_catalog_payload(report_dir, papers, inbox_items)
    resource_rows = []
    for item in payload["data_resources"]:
        collections = ", ".join(
            f"{entry.get('key')}:{entry.get('count')}"
            for entry in item.get("collections", [])[:6]
        )
        keys = ", ".join(str(key) for key in item.get("top_level_keys", [])[:8])
        consumers = ", ".join(str(value) for value in item.get("consumers", []))
        resource_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["href"]))}</a></td>'
            f"<td>{html.escape(str(item.get('description') or ''))}</td>"
            f"<td><span class=\"flag\">{'ok' if item.get('exists') else 'missing'}</span></td>"
            f"<td>{html.escape(str(item.get('declared_count') if item.get('declared_count') is not None else '-'))}</td>"
            f"<td>{html.escape(str(item.get('size_bytes') or 0))}</td>"
            f"<td>{html.escape(keys or '-')}</td>"
            f"<td>{html.escape(collections or '-')}</td>"
            f"<td>{html.escape(consumers or '-')}</td>"
            "</tr>"
        )
    page_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(page["href"]))}">{html.escape(str(page["title"]))}</a></td>'
        f"<td>{html.escape(str(page['kind']))}</td>"
        f"<td>{html.escape(str(page['description']))}</td>"
        "</tr>"
        for page in payload["pages"]
    )
    contract_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(contract["href"]))}">{html.escape(str(contract["href"]))}</a></td>'
        f"<td>{html.escape(str(contract['description']))}</td>"
        "</tr>"
        for contract in payload["contracts"]
    )
    recipe_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(recipe['name']))}</td>"
        f"<td><code>{html.escape(str(recipe['command']))}</code></td>"
        f"<td>{html.escape(', '.join(str(value) for value in recipe.get('uses', [])))}</td>"
        f"<td>{html.escape(', '.join(str(value) for value in recipe.get('outputs', [])))}</td>"
        "</tr>"
        for recipe in payload["integration_recipes"]
    )
    bootstrap_files = "".join(
        f'<span class="chip">{html.escape(str(item))}</span>'
        for item in payload["recommended_bootstrap_files"]
    )
    catalog_css = """
    .catalog-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .catalog-summary .metric-card strong { font-size: 24px; }
    .catalog-bootstrap {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 18px;
    }
    .catalog-table code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Data Catalog</div>
  <h1>数据目录</h1>
  <p class="lead">把 wiki 页面、机器可读 JSON 和数据契约整理成一个接入目录。适合后续桌面软件、DMG 封装、开源贡献者或外部脚本快速发现可用数据源。</p>
  <div class="stats">
    <a class="stat" href="release.html">发布摘要</a>
    <a class="stat" href="manifest.json">Manifest JSON</a>
    <a class="stat" href="catalog.json">Catalog JSON</a>
    <a class="stat" href="workflow.html">工作流中心</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">数据 {payload["data_file_count"]}</span>
    <span class="stat">页面 {payload["page_count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="catalog-summary">
    <section class="metric-card"><span>论文</span><strong>{payload["count"]}</strong><span>当前报告数量</span></section>
    <section class="metric-card"><span>Inbox</span><strong>{payload["inbox_count"]}</strong><span>候选论文队列</span></section>
    <section class="metric-card"><span>页面</span><strong>{payload["page_count"]}</strong><span>可打开入口</span></section>
    <section class="metric-card"><span>数据文件</span><strong>{payload["data_file_count"]}</strong><span>JSON 接入点</span></section>
    <section class="metric-card"><span>契约</span><strong>{payload["contract_count"]}</strong><span>模板与 schema</span></section>
  </section>
  <section>
    <h2 class="section-title">推荐启动文件</h2>
    <div class="catalog-bootstrap">{bootstrap_files}</div>
  </section>
  <section>
    <h2 class="section-title">机器数据</h2>
    <div class="table-wrap"><table class="data-table catalog-table"><thead><tr><th>文件</th><th>用途</th><th>状态</th><th>Count</th><th>Bytes</th><th>顶层字段</th><th>集合</th><th>消费者</th></tr></thead><tbody>{"".join(resource_rows)}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">页面入口</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>页面</th><th>类型</th><th>用途</th></tr></thead><tbody>{page_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">数据契约</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>用途</th></tr></thead><tbody>{contract_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">集成 Recipes</h2>
    <div class="table-wrap"><table class="data-table catalog-table"><thead><tr><th>场景</th><th>命令 / 读取方式</th><th>输入</th><th>输出</th></tr></thead><tbody>{recipe_rows}</tbody></table></div>
  </section>
</main>
"""
    (report_dir / "catalog.html").write_text(page_shell("数据目录", body, extra_css=catalog_css), encoding="utf-8")


def render_intake(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_intake_payload(papers, inbox_items)
    intake_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    examples = "\n".join(payload["examples"])
    command_buttons = "".join(
        f'<button class="button copy-intake-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command.split()[1] if len(command.split()) > 1 else command)}</button>'
        for command in payload["commands"]
    )
    intake_css = """
    .intake-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
      gap: 16px;
      align-items: start;
    }
    .intake-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }
    .intake-panel textarea {
      width: 100%;
      min-height: 260px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      padding: 12px;
      font: 14px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .intake-fields {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .intake-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .intake-summary {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .intake-summary .metric-card { min-height: 102px; }
    .intake-status-new_candidate { color: #1f6f4a; font-weight: 700; }
    .intake-status-library_duplicate,
    .intake-status-inbox_duplicate,
    .intake-status-paste_duplicate { color: #8a5d3b; font-weight: 700; }
    @media (max-width: 920px) { .intake-layout { grid-template-columns: 1fr; } }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Bulk Intake</div>
  <h1>批量导入</h1>
  <p class="lead">把一批论文链接、arXiv id 或标题先放进 intake，浏览器会和当前论文库及 inbox 做去重，导出可写入 `docs/inbox.csv` 的候选 CSV。</p>
  <div class="stats">
    <a class="stat" href="intake.json">Intake JSON</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="routing.html">分类路由器</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="guides/inbox.schema.json">Inbox Schema</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">Inbox {payload["inbox_count"]}</span>
  </div>
</header>
<main class="shell">
  <section class="intake-layout">
    <div class="intake-panel">
      <textarea id="intakePaste" spellcheck="false" placeholder="{html.escape(examples, quote=True)}"></textarea>
      <div class="intake-fields">
        <input id="intakeTags" placeholder="tags">
        <input id="intakeNote" placeholder="note">
        <select id="intakePriority">
          <option value="normal">normal</option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
        <input id="intakeAddedAt" type="date" value="{html.escape(str(payload["defaults"]["added_at"]), quote=True)}">
      </div>
      <div class="intake-actions">
        <button class="button primary" type="button" id="parseIntake">解析去重</button>
        <button class="button" type="button" id="downloadIntakeCsv">下载候选 CSV</button>
        <button class="button" type="button" id="copyIntakeCsv">复制候选 CSV</button>
        <button class="button" type="button" id="copyIntakeCommand">复制写入命令</button>
        <button class="button" type="button" id="clearIntake">清空</button>
      </div>
    </div>
    <aside class="intake-panel">
      <h2 class="section-title">导入概览</h2>
      <div class="intake-summary">
        <section class="metric-card"><span>解析</span><strong id="intakeTotal">0</strong><span>有效输入</span></section>
        <section class="metric-card"><span>新候选</span><strong id="intakeNew">0</strong><span>可导出</span></section>
        <section class="metric-card"><span>库内重复</span><strong id="intakeLibraryDup">0</strong><span>已读或已有报告</span></section>
        <section class="metric-card"><span>队列重复</span><strong id="intakeInboxDup">0</strong><span>已在 inbox</span></section>
      </div>
      <h2 class="section-title">命令</h2>
      <div class="bulk-actions">{command_buttons}</div>
      <p class="meta">CSV 文件名固定为 candidate_inbox.csv；先 dry-run，再加 --write 合并。</p>
    </aside>
  </section>
  <section>
    <h2 class="section-title">候选明细</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>状态</th><th>标题</th><th>链接</th><th>匹配</th><th>备注</th></tr></thead><tbody id="intakeRows"><tr><td colspan="5" class="empty">等待输入。</td></tr></tbody></table></div>
  </section>
</main>
<script>
const intakePayload = {intake_json};
const intakePaste = document.querySelector("#intakePaste");
const intakeTags = document.querySelector("#intakeTags");
const intakeNote = document.querySelector("#intakeNote");
const intakePriority = document.querySelector("#intakePriority");
const intakeAddedAt = document.querySelector("#intakeAddedAt");
const intakeRows = document.querySelector("#intakeRows");
const intakeTotal = document.querySelector("#intakeTotal");
const intakeNew = document.querySelector("#intakeNew");
const intakeLibraryDup = document.querySelector("#intakeLibraryDup");
const intakeInboxDup = document.querySelector("#intakeInboxDup");
let intakeResults = [];
const arxivPattern = /\\b(\\d{{4}}\\.\\d{{4,5}})(?:v\\d+)?\\b/i;
const urlPattern = /https?:\\/\\/[^\\s\\])<>"']+/i;

function escapeHtml(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
}}

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function normalizeLink(value) {{
  return String(value || "").trim().replace(/\\/+$/, "").toLowerCase();
}}

function normalizeTitleKey(value) {{
  return String(value || "")
    .toLowerCase()
    .replace(/https?:\\/\\/[^\\s\\])<>"']+/g, " ")
    .replace(/\\b\\d{{4}}\\.\\d{{4,5}}(?:v\\d+)?\\b/g, " ")
    .replace(/[^a-z0-9\\u4e00-\\u9fff]+/g, " ")
    .replace(/\\s+/g, " ")
    .trim();
}}

function arxivKey(value) {{
  const match = String(value || "").match(arxivPattern);
  return match ? match[1] : "";
}}

const libraryArxiv = new Set((intakePayload.existing_papers || []).map(item => item.arxiv_key).filter(Boolean));
const libraryTitles = new Map();
const libraryLinks = new Map();
(intakePayload.existing_papers || []).forEach(item => {{
  (item.title_keys || []).forEach(key => libraryTitles.set(key, item));
  (item.link_keys || []).forEach(key => libraryLinks.set(key, item));
}});
const inboxArxiv = new Set((intakePayload.inbox_items || []).map(item => item.arxiv_key).filter(Boolean));
const inboxTitles = new Map();
const inboxLinks = new Map();
(intakePayload.inbox_items || []).forEach(item => {{
  if (item.title_key) inboxTitles.set(item.title_key, item);
  if (item.link_key) inboxLinks.set(item.link_key, item);
}});

function parseLine(line) {{
  const text = line.trim();
  if (!text) return null;
  const linkMatch = text.match(urlPattern);
  const link = linkMatch ? linkMatch[0].replace(/[.,;]+$/, "") : "";
  const arxiv = arxivKey(text);
  let title = text;
  if (link) title = title.replace(link, " ");
  title = title.replace(/[|,;]+/g, " ").replace(/\\s+/g, " ").trim();
  if (!title || title === arxiv) title = arxiv || link;
  return {{
    raw: text,
    title,
    link: link || (arxiv ? `https://arxiv.org/abs/${{arxiv}}` : ""),
    arxiv_key: arxiv,
    title_key: normalizeTitleKey(title),
    link_key: normalizeLink(link || (arxiv ? `https://arxiv.org/abs/${{arxiv}}` : "")),
  }};
}}

function classifyCandidate(candidate, seen) {{
  const seenKey = candidate.arxiv_key || candidate.link_key || candidate.title_key || candidate.raw.toLowerCase();
  if (seen.has(seenKey)) {{
    return {{ status: "paste_duplicate", match: seenKey, note: "same paste batch" }};
  }}
  seen.add(seenKey);
  if (candidate.arxiv_key && libraryArxiv.has(candidate.arxiv_key)) {{
    return {{ status: "library_duplicate", match: candidate.arxiv_key, note: "arxiv already in library" }};
  }}
  if (candidate.link_key && libraryLinks.has(candidate.link_key)) {{
    return {{ status: "library_duplicate", match: candidate.link_key, note: "link already in library" }};
  }}
  if (candidate.title_key && libraryTitles.has(candidate.title_key)) {{
    return {{ status: "library_duplicate", match: candidate.title_key, note: "title already in library" }};
  }}
  if (candidate.arxiv_key && inboxArxiv.has(candidate.arxiv_key)) {{
    return {{ status: "inbox_duplicate", match: candidate.arxiv_key, note: "arxiv already in inbox" }};
  }}
  if (candidate.link_key && inboxLinks.has(candidate.link_key)) {{
    return {{ status: "inbox_duplicate", match: candidate.link_key, note: "link already in inbox" }};
  }}
  if (candidate.title_key && inboxTitles.has(candidate.title_key)) {{
    return {{ status: "inbox_duplicate", match: candidate.title_key, note: "title already in inbox" }};
  }}
  return {{ status: "new_candidate", match: "", note: "ready for inbox" }};
}}

function parseIntakeLines() {{
  const seen = new Set();
  return intakePaste.value
    .split(/\\n+/)
    .map(parseLine)
    .filter(Boolean)
    .map(candidate => ({{ ...candidate, ...classifyCandidate(candidate, seen) }}));
}}

function rowsToCsv(rows) {{
  const header = intakePayload.csv_columns || ["title", "link", "status", "priority", "tags", "note", "added_at"];
  const values = rows.map(row => ({{
    title: row.title,
    link: row.link,
    status: intakePayload.defaults?.status || "queued",
    priority: intakePriority.value || intakePayload.defaults?.priority || "normal",
    tags: intakeTags.value.trim(),
    note: intakeNote.value.trim(),
    added_at: intakeAddedAt.value || intakePayload.defaults?.added_at || "",
  }}));
  return [header, ...values.map(item => header.map(key => item[key] || ""))]
    .map(row => row.map(csvCell).join(","))
    .join("\\n") + "\\n";
}}

function candidateRows() {{
  return intakeResults.filter(row => row.status === "new_candidate");
}}

function renderIntakeRows() {{
  intakeRows.replaceChildren();
  if (!intakeResults.length) {{
    const empty = document.createElement("tr");
    empty.innerHTML = `<td colspan="5" class="empty">等待输入。</td>`;
    intakeRows.appendChild(empty);
    return;
  }}
  intakeResults.forEach(row => {{
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="intake-status-${{escapeHtml(row.status)}}">${{escapeHtml(row.status)}}</td>
      <td><strong>${{escapeHtml(row.title)}}</strong><div class="meta">${{escapeHtml(row.arxiv_key || "")}}</div></td>
      <td>${{row.link ? `<a href="${{escapeHtml(row.link)}}">${{escapeHtml(row.link)}}</a>` : ""}}</td>
      <td>${{escapeHtml(row.match || "")}}</td>
      <td>${{escapeHtml(row.note || "")}}</td>
    `;
    intakeRows.appendChild(tr);
  }});
}}

function renderIntake() {{
  intakeResults = parseIntakeLines();
  const counts = intakeResults.reduce((acc, row) => {{
    acc[row.status] = (acc[row.status] || 0) + 1;
    return acc;
  }}, {{}});
  intakeTotal.textContent = String(intakeResults.length);
  intakeNew.textContent = String(counts.new_candidate || 0);
  intakeLibraryDup.textContent = String(counts.library_duplicate || 0);
  intakeInboxDup.textContent = String((counts.inbox_duplicate || 0) + (counts.paste_duplicate || 0));
  renderIntakeRows();
}}

function downloadText(filename, text, type) {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyText(text, fallbackTitle) {{
  try {{
    await navigator.clipboard.writeText(text);
    return true;
  }} catch {{
    window.prompt(fallbackTitle, text);
    return false;
  }}
}}

document.querySelector("#parseIntake").addEventListener("click", renderIntake);
document.querySelector("#downloadIntakeCsv").addEventListener("click", () => {{
  renderIntake();
  const rows = candidateRows();
  if (!rows.length) {{
    window.alert("没有可导出的新候选。");
    return;
  }}
  downloadText("candidate_inbox.csv", rowsToCsv(rows), "text/csv;charset=utf-8");
}});
document.querySelector("#copyIntakeCsv").addEventListener("click", async () => {{
  renderIntake();
  const rows = candidateRows();
  if (!rows.length) {{
    window.alert("没有可复制的新候选。");
    return;
  }}
  await copyText(rowsToCsv(rows), "复制候选 CSV");
}});
document.querySelector("#copyIntakeCommand").addEventListener("click", async () => {{
  await copyText("python3 scripts/apply_inbox_items.py docs --input candidate_inbox.csv", "复制写入命令");
}});
document.querySelector("#clearIntake").addEventListener("click", () => {{
  intakePaste.value = "";
  renderIntake();
}});
document.querySelectorAll(".copy-intake-command").forEach(button => {{
  button.dataset.label = button.textContent;
  button.addEventListener("click", async () => {{
    const copied = await copyText(button.dataset.command || "", "复制命令");
    if (copied) {{
      button.textContent = "已复制";
      setTimeout(() => button.textContent = button.dataset.label, 1200);
    }}
  }});
}});
intakePaste.addEventListener("input", renderIntake);
renderIntake();
</script>
"""
    (report_dir / "intake.html").write_text(page_shell("批量导入", body, extra_css=intake_css), encoding="utf-8")


def render_inbox_row(item: dict[str, Any]) -> str:
    tags = "".join(f'<span class="chip">{html.escape(tag)}</span>' for tag in item.get("tags", []))
    link = str(item.get("link") or "")
    link_html = f'<a href="{html.escape(link)}">{html.escape(link)}</a>' if link else ""
    duplicate = '<span class="flag">已在库中</span>' if item.get("duplicate") else ""
    tags_text = "; ".join(str(tag) for tag in item.get("tags", []) if tag)
    prompt_bits = [
        item.get("title") or "",
        item.get("link") or "",
        item.get("arxiv_id") or "",
    ]
    prompt = " ".join(str(bit) for bit in prompt_bits if bit).strip()
    return f"""<tr
  data-search="{html.escape(' '.join(str(value) for value in [item.get('title'), item.get('link'), item.get('arxiv_id'), item.get('note'), *item.get('tags', [])] if value).lower(), quote=True)}"
  data-id="{html.escape(str(item.get("id") or ""), quote=True)}"
  data-title="{html.escape(str(item.get("title") or ""), quote=True)}"
  data-link="{html.escape(str(item.get("link") or ""), quote=True)}"
  data-arxiv-id="{html.escape(str(item.get("arxiv_id") or ""), quote=True)}"
  data-status="{html.escape(str(item.get("status") or ""), quote=True)}"
  data-priority="{html.escape(str(item.get("priority") or ""), quote=True)}"
  data-tags="{html.escape(tags_text, quote=True)}"
  data-note="{html.escape(str(item.get("note") or ""), quote=True)}"
  data-added-at="{html.escape(str(item.get("added_at") or ""), quote=True)}"
  data-duplicate="{"yes" if item.get("duplicate") else "no"}">
  <td class="library-title">
    <strong>{html.escape(str(item.get("title") or "Untitled"))}</strong>
    <div class="meta">{link_html}</div>
    <div class="meta">{html.escape(str(item.get("arxiv_id") or ""))}</div>
  </td>
  <td><span class="flag">{html.escape(str(item.get("status") or "queued"))}</span><div class="meta">{html.escape(str(item.get("priority") or "normal"))}</div></td>
  <td><div class="chips">{tags}</div></td>
  <td>{html.escape(str(item.get("note") or ""))}</td>
  <td>{duplicate}<div class="meta">{html.escape(str(item.get("added_at") or ""))}</div></td>
  <td><button class="button copy-prompt" type="button" data-prompt="{html.escape(prompt, quote=True)}">复制任务</button></td>
</tr>"""


def render_inbox(report_dir: Path, items: list[dict[str, Any]]) -> None:
    rows = "\n".join(render_inbox_row(item) for item in items)
    statuses = inbox_counts(items, "status")
    priorities = inbox_counts(items, "priority")
    duplicate_count = sum(1 for item in items if item.get("duplicate"))
    empty = "" if rows else '<tr><td colspan="6" class="empty">还没有 inbox.csv。可以在 docs/inbox.csv 中添加 title,link,status,priority,tags,note。</td></tr>'
    body = f"""
<header class="shell">
  <div class="eyebrow">Paper Inbox</div>
  <h1>论文待处理池</h1>
  <p class="lead">把临时发现的论文链接先放进 inbox，集中筛选、去重和复制给阅读流程。适合一次性管理很多候选论文。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="inbox.json">Inbox JSON</a>
    <span class="stat">候选 {len(items)}</span>
    <span class="stat">疑似重复 {duplicate_count}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="inboxSearch" type="search" placeholder="搜索标题、链接、arxiv、标签、备注">
    <select id="inboxStatus"><option value="">全部状态</option>{render_topic_options(statuses)}</select>
    <select id="inboxPriority"><option value="">全部优先级</option>{render_topic_options(priorities)}</select>
    <select id="inboxDuplicate"><option value="">重复状态</option><option value="yes">疑似已在库中</option><option value="no">新候选</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="inboxCount">显示 {len(items)} / {len(items)} 条</strong>
    <div class="results-actions">
      <button id="copyVisiblePrompts" class="button" type="button">复制当前筛选任务</button>
      <button id="downloadInboxCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyInboxTemplate" class="button" type="button">复制 CSV 模板</button>
    </div>
  </div>
  <div class="table-wrap">
    <table class="library-table">
      <thead><tr><th>论文</th><th>状态</th><th>标签</th><th>备注</th><th>去重</th><th>操作</th></tr></thead>
      <tbody id="inboxRows">{rows or empty}</tbody>
    </table>
  </div>
</main>
<script>
const inboxRows = Array.from(document.querySelectorAll("#inboxRows tr[data-search]"));
const inboxSearch = document.querySelector("#inboxSearch");
const inboxStatus = document.querySelector("#inboxStatus");
const inboxPriority = document.querySelector("#inboxPriority");
const inboxDuplicate = document.querySelector("#inboxDuplicate");
const inboxCount = document.querySelector("#inboxCount");
const copyVisiblePrompts = document.querySelector("#copyVisiblePrompts");
const downloadInboxCsv = document.querySelector("#downloadInboxCsv");
const copyInboxTemplate = document.querySelector("#copyInboxTemplate");
let visibleInboxRows = [...inboxRows];
const inboxCsvHeader = ["id", "title", "link", "status", "priority", "tags", "note", "added_at"];

function promptForRow(row) {{
  const button = row.querySelector(".copy-prompt");
  return button ? `请按 AutoPaperReader 工作流阅读这篇论文：${{button.dataset.prompt}}` : "";
}}

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function inboxRowsToCsv(rows) {{
  const body = rows.map(row => [
    row.dataset.id,
    row.dataset.title,
    row.dataset.link,
    row.dataset.status,
    row.dataset.priority,
    row.dataset.tags,
    row.dataset.note,
    row.dataset.addedAt,
  ]);
  return [inboxCsvHeader, ...body].map(row => row.map(csvCell).join(",")).join("\\n") + "\\n";
}}

function downloadText(filename, text, type) {{
  const blob = new Blob([text], {{ type }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyText(text, fallbackTitle) {{
  try {{
    await navigator.clipboard.writeText(text);
    return true;
  }} catch {{
    window.prompt(fallbackTitle, text);
    return false;
  }}
}}

function renderInbox() {{
  const q = inboxSearch.value.trim().toLowerCase();
  let visible = 0;
  visibleInboxRows = [];
  inboxRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!inboxStatus.value || row.dataset.status === inboxStatus.value)
      && (!inboxPriority.value || row.dataset.priority === inboxPriority.value)
      && (!inboxDuplicate.value || row.dataset.duplicate === inboxDuplicate.value);
    row.hidden = !hit;
    if (hit) {{
      visible += 1;
      visibleInboxRows.push(row);
    }}
  }});
  inboxCount.textContent = `显示 ${{visible}} / ${{inboxRows.length}} 条`;
}}

[inboxSearch, inboxStatus, inboxPriority, inboxDuplicate].forEach(el => el.addEventListener("input", renderInbox));
copyVisiblePrompts.addEventListener("click", async () => {{
  const prompts = visibleInboxRows.map(promptForRow).filter(Boolean);
  if (!prompts.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const text = prompts.map((prompt, index) => `${{index + 1}}. ${{prompt}}`).join("\\n");
  const copied = await copyText(text, "复制当前筛选任务");
  copyVisiblePrompts.textContent = copied ? `已复制 ${{prompts.length}} 条` : "复制当前筛选任务";
  if (copied) setTimeout(() => copyVisiblePrompts.textContent = "复制当前筛选任务", 1400);
}});
downloadInboxCsv.addEventListener("click", () => {{
  if (!visibleInboxRows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  downloadText("inbox_filtered.csv", inboxRowsToCsv(visibleInboxRows), "text/csv;charset=utf-8");
}});
copyInboxTemplate.addEventListener("click", async () => {{
  const template = inboxCsvHeader.join(",") + "\\n" + ["paper-1", "Paper title", "https://arxiv.org/abs/0000.00000", "queued", "medium", "tag-a; tag-b", "why this matters", ""].map(csvCell).join(",") + "\\n";
  const copied = await copyText(template, "复制 inbox.csv 模板");
  copyInboxTemplate.textContent = copied ? "已复制模板" : "复制 CSV 模板";
  if (copied) setTimeout(() => copyInboxTemplate.textContent = "复制 CSV 模板", 1400);
}});
document.querySelectorAll(".copy-prompt").forEach(button => {{
  button.addEventListener("click", async () => {{
    const prompt = `请按 AutoPaperReader 工作流阅读这篇论文：${{button.dataset.prompt}}`;
    const copied = await copyText(prompt, "复制任务");
    if (copied) {{
      button.textContent = "已复制";
      setTimeout(() => button.textContent = "复制任务", 1200);
    }}
  }});
}});
renderInbox();
</script>
"""
    (report_dir / "inbox.html").write_text(page_shell("论文待处理池", body), encoding="utf-8")


def render_review_row(item: dict[str, Any]) -> str:
    state_label = {
        "due": "待复习",
        "needs_plan": "需建计划",
        "scheduled": "已计划",
    }.get(str(item.get("state") or ""), str(item.get("state") or "unknown"))
    next_text = item.get("next_review") or f'建议 {item.get("suggested_next_review")}'
    return f"""<tr>
  <td class="library-title">
    <strong><a href="{html.escape(str(item.get("html_path") or ""))}">{html.escape(str(item.get("title_zh") or item.get("title") or item.get("slug")))}</a></strong>
    <div class="meta">{html.escape(str(item.get("slug") or ""))}</div>
  </td>
  <td>{html.escape(str(item.get("research_line") or "Unassigned"))}<div class="meta">{html.escape(str(item.get("line_role") or ""))}</div></td>
  <td><span class="flag">{html.escape(state_label)}</span><div class="meta">{html.escape(str(item.get("review_stage") or "未设置阶段"))}</div></td>
  <td>{html.escape(str(next_text))}<div class="meta">间隔 {html.escape(str(item.get("interval_days") or "-"))} 天</div></td>
  <td><div class="score-grid"><span>I {html.escape(str(item.get("importance") or "-"))}</span><span>C {html.escape(str(item.get("confidence") or "-"))}</span><span>R {html.escape(str(item.get("reproducibility") or "-"))}</span></div></td>
  <td>{html.escape(str(item.get("priority") or 0))}</td>
</tr>"""


def render_review(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    plan = build_review_plan(papers)
    items = plan["items"]
    rows = "\n".join(render_review_row(item) for item in items)
    queue_cards = "".join(
        f'<section class="metric-card"><span>{html.escape(name)}</span><strong>{len(slugs)}</strong><span>{html.escape(", ".join(slugs[:3]))}</span></section>'
        for name, slugs in plan["queues"].items()
    )
    body = f"""
<header class="shell">
  <div class="eyebrow">Review Planner</div>
  <h1>复习计划</h1>
  <p class="lead">根据 importance、confidence、reproducibility、last_reviewed 与 next_review 生成复习队列。没有写入报告的项目会给出建议日期，便于后续批量补 frontmatter。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="review.json">复习 JSON</a>
    <span class="stat">论文 {len(items)}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">队列</h2>
    <div class="metric-grid">{queue_cards}</div>
  </section>
  <section>
    <h2 class="section-title">复习条目</h2>
    <div class="results-bar">
      <strong>建议写回：{len(plan["queues"].get("needs_plan", []))} 篇需建计划</strong>
      <div class="results-actions">
        <button id="downloadReviewPatch" class="button" type="button">下载建议 CSV</button>
      </div>
    </div>
    <div class="table-wrap">
      <table class="library-table">
        <thead><tr><th>论文</th><th>研究线</th><th>状态</th><th>下次复习</th><th>评分</th><th>优先级</th></tr></thead>
        <tbody>{rows if rows else '<tr><td colspan="6">暂无论文。</td></tr>'}</tbody>
      </table>
    </div>
  </section>
</main>
<script>
const reviewItems = window.PAPER_WIKI.review_items || [];
const downloadReviewPatch = document.querySelector("#downloadReviewPatch");

function reviewCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function downloadReviewCsv(filename, rows) {{
  const csv = rows.map(row => row.map(reviewCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

downloadReviewPatch.addEventListener("click", () => {{
  const rows = reviewItems
    .filter(item => item.state === "needs_plan" && item.suggested_next_review)
    .map(item => [item.slug, item.suggested_next_review, item.review_stage || "fresh"]);
  if (!rows.length) {{
    window.alert("当前没有需要写回的建议复习计划。");
    return;
  }}
  downloadReviewCsv("review_plan_patch.csv", [["slug", "next_review", "review_stage"], ...rows]);
}});
</script>
"""
    (report_dir / "review.html").write_text(page_shell("复习计划", body, {"review_items": items}), encoding="utf-8")


def render_freshness(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    report = build_freshness_report(papers)
    items = report["items"]
    state_labels = {
        "due": "待复习",
        "needs_plan": "需建计划",
        "stale": "已过期",
        "aging": "变旧中",
        "current": "新鲜",
    }
    metric_html = "".join(
        f'<section class="metric-card"><span>{html.escape(state_labels.get(state, state))}</span><strong>{count}</strong><span>{html.escape(state)}</span></section>'
        for state, count in report["summary"]["states"].items()
    )
    line_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(page_query_href("library.html", line=line["research_line"]))}">{html.escape(str(line["research_line"]))}</a></td>'
        f"<td>{line['count']}</td>"
        f"<td>{line['average_score']}</td>"
        f"<td><span class=\"flag\">{html.escape(str(line['risk']))}</span></td>"
        f"<td>{html.escape(json.dumps(line['state_counts'], ensure_ascii=False, sort_keys=True))}</td>"
        f"<td>{html.escape('; '.join(line['actions']) or '保持观察')}</td>"
        "</tr>"
        for line in report["line_health"]
    )

    def row(item: dict[str, Any]) -> str:
        actions = "".join(f'<span class="chip">{html.escape(action)}</span>' for action in item.get("actions", []))
        reasons = "".join(f'<span class="chip">{html.escape(reason)}</span>' for reason in item.get("reasons", []))
        searchable = " ".join(
            str(value)
            for value in [
                item.get("title"),
                item.get("title_zh"),
                item.get("research_line"),
                item.get("state"),
                *item.get("reasons", []),
                *item.get("actions", []),
            ]
            if value
        ).lower()
        return f"""<tr
  data-search="{html.escape(searchable, quote=True)}"
  data-state="{html.escape(str(item.get("state") or ""), quote=True)}"
  data-line="{html.escape(str(item.get("research_line") or ""), quote=True)}"
  data-score="{html.escape(str(item.get("score") or 0), quote=True)}"
  data-age="{html.escape(str(item.get("age_days") or 0), quote=True)}"
  data-slug="{html.escape(str(item.get("slug") or ""), quote=True)}">
  <td class="library-title">
    <strong><a href="{html.escape(str(item.get("html_path") or ""))}">{html.escape(str(item.get("title_zh") or item.get("title") or item.get("slug")))}</a></strong>
    <div class="meta">{html.escape(str(item.get("slug") or ""))}</div>
  </td>
  <td>{html.escape(str(item.get("research_line") or "Unassigned"))}<div class="meta">{html.escape(str(item.get("line_role") or ""))}</div></td>
  <td><span class="flag">{html.escape(state_labels.get(str(item.get("state")), str(item.get("state"))))}</span><div class="meta">score {item.get("score")}</div></td>
  <td>{html.escape(str(item.get("last_reviewed") or "-"))}<div class="meta">age {html.escape(str(item.get("age_days") if item.get("age_days") is not None else "-"))} days</div></td>
  <td>{html.escape(str(item.get("next_review") or "-"))}<div class="meta">year age {html.escape(str(item.get("year_age") if item.get("year_age") is not None else "-"))}</div></td>
  <td><div class="chips">{reasons}</div></td>
  <td><div class="chips">{actions}</div></td>
</tr>"""

    rows = "".join(row(item) for item in items)
    line_options = render_topic_options({str(line["research_line"]): int(line["count"]) for line in report["line_health"]})
    freshness_json = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    freshness_css = """
    .freshness-controls {
      display: grid;
      grid-template-columns: minmax(240px, 2fr) repeat(3, minmax(150px, 1fr));
      gap: 10px;
      align-items: center;
    }
    .freshness-controls input,
    .freshness-controls select {
      width: 100%;
    }
    @media (max-width: 900px) {
      .freshness-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Freshness Governance</div>
  <h1>时效治理</h1>
  <p class="lead">集中查看报告是否过期、是否缺复习计划、哪些研究线需要检索后续工作。适合论文库变大后做周期性维护。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="freshness.json">Freshness JSON</a>
    <span class="stat">论文 {report["count"]}</span>
    <span class="stat">平均分 {report["summary"]["average_score"]}</span>
    <span class="stat">日期 {html.escape(str(report["today"]))}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">新鲜度状态</h2>
    <div class="metric-grid">{metric_html}</div>
  </section>
  <section>
    <h2 class="section-title">研究线健康度</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>研究线</th><th>论文</th><th>平均分</th><th>风险</th><th>状态分布</th><th>建议动作</th></tr></thead><tbody>{line_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">报告时效队列</h2>
    <div class="freshness-controls">
      <input id="freshnessSearch" type="search" placeholder="搜索标题、研究线、原因或动作">
      <select id="freshnessState"><option value="">全部状态</option>{render_topic_options(report["summary"]["states"])}</select>
      <select id="freshnessLine"><option value="">全部研究线</option>{line_options}</select>
      <select id="freshnessSort"><option value="risk">风险优先</option><option value="score">分数低到高</option><option value="age">最久未复盘</option><option value="line">研究线 A-Z</option></select>
      <strong id="freshnessCount">{len(items)} 条</strong>
    </div>
    <div class="results-actions">
      <button id="downloadFreshnessCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyFreshnessQueue" class="button" type="button">复制治理队列</button>
    </div>
    <div class="table-wrap"><table class="library-table"><thead><tr><th>论文</th><th>研究线</th><th>状态</th><th>上次复盘</th><th>下次复习</th><th>原因</th><th>建议动作</th></tr></thead><tbody id="freshnessRows">{rows}</tbody></table></div>
  </section>
</main>
<script>
const freshnessData = {freshness_json};
const freshnessSearch = document.querySelector("#freshnessSearch");
const freshnessState = document.querySelector("#freshnessState");
const freshnessLine = document.querySelector("#freshnessLine");
const freshnessSort = document.querySelector("#freshnessSort");
const freshnessCount = document.querySelector("#freshnessCount");
const freshnessBody = document.querySelector("#freshnessRows");
const freshnessRows = Array.from(document.querySelectorAll("#freshnessRows tr"));
const downloadFreshnessCsv = document.querySelector("#downloadFreshnessCsv");
const copyFreshnessQueue = document.querySelector("#copyFreshnessQueue");
const freshnessRank = {{ due: 0, needs_plan: 1, stale: 2, aging: 3, current: 4 }};

function visibleFreshnessRows() {{
  return freshnessRows.filter(row => !row.hidden);
}}

function csvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function sortFreshnessRows(rows) {{
  const mode = freshnessSort.value;
  return rows.sort((a, b) => {{
    if (mode === "score") return Number(a.dataset.score || 0) - Number(b.dataset.score || 0) || a.dataset.slug.localeCompare(b.dataset.slug);
    if (mode === "age") return Number(b.dataset.age || 0) - Number(a.dataset.age || 0) || a.dataset.slug.localeCompare(b.dataset.slug);
    if (mode === "line") return a.dataset.line.localeCompare(b.dataset.line) || a.dataset.slug.localeCompare(b.dataset.slug);
    return (freshnessRank[a.dataset.state] ?? 9) - (freshnessRank[b.dataset.state] ?? 9) || Number(a.dataset.score || 0) - Number(b.dataset.score || 0);
  }});
}}

function renderFreshnessRows() {{
  const q = freshnessSearch.value.trim().toLowerCase();
  let visible = 0;
  freshnessRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!freshnessState.value || row.dataset.state === freshnessState.value)
      && (!freshnessLine.value || row.dataset.line === freshnessLine.value);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  sortFreshnessRows(freshnessRows).forEach(row => freshnessBody.appendChild(row));
  freshnessCount.textContent = `${{visible}} / ${{freshnessRows.length}} 条`;
}}

function currentFreshnessItems() {{
  const visibleSlugs = new Set(visibleFreshnessRows().map(row => row.dataset.slug));
  return freshnessData.filter(item => visibleSlugs.has(item.slug));
}}

downloadFreshnessCsv.addEventListener("click", () => {{
  const header = ["slug", "title", "research_line", "state", "score", "last_reviewed", "next_review", "age_days", "year_age", "reasons", "actions"];
  const rows = currentFreshnessItems().map(item => [item.slug, item.title_zh || item.title, item.research_line, item.state, item.score, item.last_reviewed, item.next_review, item.age_days ?? "", item.year_age ?? "", (item.reasons || []).join("; "), (item.actions || []).join("; ")]);
  const csv = [header, ...rows].map(row => row.map(csvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "freshness_queue.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}});

copyFreshnessQueue.addEventListener("click", async () => {{
  const lines = ["# Freshness Queue", ""];
  currentFreshnessItems().forEach(item => {{
    lines.push(`- [ ] ${{item.slug}} ${{item.title_zh || item.title}}`);
    lines.push(`  - State: ${{item.state}}, score ${{item.score}}, line ${{item.research_line || "Unassigned"}}`);
    lines.push(`  - Actions: ${{(item.actions || []).join("; ")}}`);
  }});
  const text = lines.join("\\n");
  try {{
    await navigator.clipboard.writeText(text);
    copyFreshnessQueue.textContent = "已复制队列";
    setTimeout(() => copyFreshnessQueue.textContent = "复制治理队列", 1400);
  }} catch {{
    window.prompt("复制治理队列", text);
  }}
}});

[freshnessSearch, freshnessState, freshnessLine, freshnessSort].forEach(control => control.addEventListener("input", renderFreshnessRows));
renderFreshnessRows();
</script>
"""
    (report_dir / "freshness.html").write_text(page_shell("时效治理", body, extra_css=freshness_css), encoding="utf-8")


def render_quality_issue_row(issue: dict[str, Any]) -> str:
    missing = ", ".join(issue.get("missing_fields") or []) or "-"
    weak = ", ".join(issue.get("weak_fields") or []) or "-"
    review = "到期" if issue.get("due_review") else "-"
    title = issue.get("title_zh") or issue.get("title") or issue.get("slug")
    href = f"{html.escape(str(issue.get('slug') or ''))}.html"
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(str(title))}</a><div class="meta">{html.escape(str(issue.get("research_line") or ""))}</div></td>'
        f"<td>{html.escape(str(issue.get('score') or 0))}</td>"
        f"<td>{html.escape(missing)}</td>"
        f"<td>{html.escape(weak)}</td>"
        f"<td>{html.escape(review)}</td>"
        "</tr>"
    )


def render_quality_drift_row(item: dict[str, Any]) -> str:
    title = item.get("title_zh") or item.get("title") or item.get("slug")
    href = f"{html.escape(str(item.get('slug') or ''))}.html"
    allowed = ", ".join(str(value) for value in item.get("allowed", []))
    return (
        "<tr>"
        f'<td><a href="{href}">{html.escape(str(title))}</a></td>'
        f"<td>{html.escape(str(item.get('field') or ''))}</td>"
        f"<td><span class=\"flag\">{html.escape(str(item.get('value') or ''))}</span></td>"
        f"<td>{html.escape(allowed)}</td>"
        "</tr>"
    )


def render_quality_inbox_row(item: dict[str, Any]) -> str:
    title = item.get("title") or item.get("arxiv_id") or item.get("link") or "Untitled"
    link = str(item.get("link") or "")
    link_html = f'<a href="{html.escape(link)}">{html.escape(link)}</a>' if link else ""
    return (
        "<tr>"
        f"<td>{html.escape(str(title))}<div class=\"meta\">{html.escape(str(item.get('arxiv_id') or ''))}</div></td>"
        f"<td>{link_html}</td>"
        f"<td>{html.escape(str(item.get('status') or 'queued'))}</td>"
        f"<td>{html.escape(str(item.get('note') or ''))}</td>"
        "</tr>"
    )


def render_dedupe_group_row(group: dict[str, Any]) -> str:
    paper_links = []
    for paper in group.get("papers", []):
        title = paper.get("title_zh") or paper.get("title") or paper.get("slug")
        href = str(paper.get("href") or f"{paper.get('slug')}.html")
        paper_links.append(f'<a href="{html.escape(href)}">{html.escape(str(title))}</a>')
    item_titles = [
        f"{item.get('id')}: {item.get('title')}"
        for item in group.get("items", [])
    ]
    slugs = ", ".join(str(slug) for slug in group.get("slugs", []))
    item_ids = ", ".join(str(item_id) for item_id in group.get("item_ids", []))
    search_text = " ".join(
        str(value or "")
        for value in [
            group.get("scope"),
            group.get("kind"),
            group.get("key"),
            slugs,
            item_ids,
            " ".join(paper_links),
            " ".join(item_titles),
        ]
    ).lower()
    checklist = (
        f"- [ ] {group.get('scope')} / {group.get('kind')} / {group.get('key')}: "
        f"{group.get('recommended_action')}"
    )
    return (
        f'<tr data-scope="{html.escape(str(group.get("scope") or ""), quote=True)}"'
        f' data-severity="{html.escape(str(group.get("severity") or ""), quote=True)}"'
        f' data-kind="{html.escape(str(group.get("kind") or ""), quote=True)}"'
        f' data-search="{html.escape(search_text, quote=True)}">'
        f"<td><span class=\"flag\">{html.escape(str(group.get('scope') or ''))}</span>"
        f"<div class=\"meta\">{html.escape(str(group.get('id') or ''))}</div></td>"
        f"<td>{html.escape(str(group.get('kind') or ''))}<div class=\"meta\">{html.escape(str(group.get('key') or ''))}</div></td>"
        f"<td><span class=\"flag\">{html.escape(str(group.get('severity') or ''))}</span><div class=\"meta\">{html.escape(str(group.get('count') or 0))} entries</div></td>"
        f"<td>{', '.join(paper_links) if paper_links else html.escape(', '.join(item_titles))}</td>"
        f"<td>{html.escape(slugs or item_ids)}</td>"
        f"<td>{html.escape(str(group.get('recommended_action') or ''))}</td>"
        f'<td><button class="button copy-dedupe-row" type="button" data-checklist="{html.escape(checklist, quote=True)}">复制</button></td>'
        "</tr>"
    )


def render_dedupe(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_dedupe_report(papers, inbox_items)
    groups = payload["report_groups"] + payload["inbox_groups"]
    rows = "".join(render_dedupe_group_row(group) for group in groups)
    table = (
        '<table class="data-table"><thead><tr><th>范围</th><th>依据</th><th>优先级</th><th>对象</th><th>ID</th><th>建议动作</th><th>复制</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        if rows
        else '<div class="empty">当前没有发现重复报告或重复候选。</div>'
    )
    metrics = [
        ("重复组", str(payload["group_count"]), "library + inbox"),
        ("库内重复", str(payload["duplicate_report_count"]), "report groups"),
        ("候选重复", str(payload["inbox_duplicate_count"]), "inbox groups"),
        ("高优先级", str(payload["summary"]["high"]), "merge first"),
        ("中优先级", str(payload["summary"]["medium"]), "triage"),
    ]
    metric_html = "".join(
        f'<section class="metric-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><span>{html.escape(note)}</span></section>'
        for label, value, note in metrics
    )
    command_buttons = "".join(
        f'<button class="button copy-dedupe-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command)}</button>'
        for command in payload["commands"]
    )
    body = f"""
<header class="shell">
  <div class="eyebrow">Dedupe Governance</div>
  <h1>去重工作台</h1>
  <p class="lead">把库内重复报告、候选池撞车和 inbox 内部重复集中到一个治理视图，适合在批量导入论文前后做清理。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="intake.html">批量导入</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="dedupe.json">Dedupe JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">候选 {payload["inbox_count"]}</span>
    <span class="stat">生成时间 {html.escape(payload["generated_at"])}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">去重摘要</h2>
    <div class="metric-grid">{metric_html}</div>
  </section>
  <section>
    <h2 class="section-title">筛选</h2>
    <div class="filter-grid">
      <input id="dedupeSearch" type="search" placeholder="搜索标题、slug、arXiv、候选 id">
      <select id="dedupeScope">
        <option value="">全部范围</option>
        <option value="library">库内报告</option>
        <option value="inbox">候选池</option>
      </select>
      <select id="dedupeSeverity">
        <option value="">全部优先级</option>
        <option value="high">high</option>
        <option value="medium">medium</option>
        <option value="low">low</option>
      </select>
      <select id="dedupeKind">
        <option value="">全部依据</option>
      </select>
    </div>
    <div class="results-bar">
      <strong><span id="dedupeVisibleCount">{len(groups)}</span> 组可见</strong>
      <div class="results-actions">
        <button id="downloadDedupeCsv" class="button" type="button">下载 CSV</button>
        <button id="copyDedupeMarkdown" class="button" type="button">复制清单</button>
        <button id="copyDedupeCommands" class="button" type="button">复制命令</button>
      </div>
    </div>
  </section>
  <section>
    <h2 class="section-title">重复项</h2>
    <div class="table-wrap">{table}</div>
  </section>
  <section>
    <h2 class="section-title">治理命令</h2>
    <div class="command-panel"><div class="bulk-actions">{command_buttons}</div></div>
  </section>
</main>
<script>
const dedupeGroups = [...(window.PAPER_WIKI.report_groups || []), ...(window.PAPER_WIKI.inbox_groups || [])];
const dedupeRows = Array.from(document.querySelectorAll("[data-scope]"));
const dedupeSearch = document.querySelector("#dedupeSearch");
const dedupeScope = document.querySelector("#dedupeScope");
const dedupeSeverity = document.querySelector("#dedupeSeverity");
const dedupeKind = document.querySelector("#dedupeKind");
const dedupeVisibleCount = document.querySelector("#dedupeVisibleCount");

function dedupeCsvCell(value) {{
  const text = Array.isArray(value) ? value.join("; ") : String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? '"' + text.replaceAll('"', '""') + '"'
    : text;
}}

function visibleDedupeGroups() {{
  const visibleIds = new Set(dedupeRows.filter(row => !row.hidden).map(row => row.querySelector(".meta")?.textContent || ""));
  return dedupeGroups.filter(group => visibleIds.has(group.id));
}}

function renderDedupe() {{
  const query = (dedupeSearch.value || "").trim().toLowerCase();
  const scope = dedupeScope.value;
  const severity = dedupeSeverity.value;
  const kind = dedupeKind.value;
  let count = 0;
  dedupeRows.forEach(row => {{
    const match = (!query || (row.dataset.search || "").includes(query))
      && (!scope || row.dataset.scope === scope)
      && (!severity || row.dataset.severity === severity)
      && (!kind || row.dataset.kind === kind);
    row.hidden = !match;
    if (match) count += 1;
  }});
  dedupeVisibleCount.textContent = String(count);
}}

function downloadDedupeCsv() {{
  const columns = window.PAPER_WIKI.csv_columns || [];
  const lines = [columns.join(",")];
  visibleDedupeGroups().forEach(group => {{
    lines.push(columns.map(column => dedupeCsvCell(group[column])).join(","));
  }});
  const blob = new Blob([lines.join("\\n")], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "dedupe_review.csv";
  link.click();
  URL.revokeObjectURL(url);
}}

function dedupeMarkdown(groups) {{
  if (!groups.length) return "- [x] 当前没有可见重复项";
  return groups.map(group => `- [ ] ${{group.scope}} / ${{group.kind}} / ${{group.key}}: ${{group.recommended_action}}`).join("\\n");
}}

async function copyDedupeText(text, label, button) {{
  try {{
    await navigator.clipboard.writeText(text);
    const original = button.textContent;
    button.textContent = label;
    setTimeout(() => button.textContent = original, 1200);
  }} catch {{
    window.prompt("复制内容", text);
  }}
}}

new Set(dedupeGroups.map(group => group.kind).filter(Boolean)).forEach(kind => {{
  const option = document.createElement("option");
  option.value = kind;
  option.textContent = kind;
  dedupeKind.appendChild(option);
}});

[dedupeSearch, dedupeScope, dedupeSeverity, dedupeKind].forEach(control => {{
  control.addEventListener("input", renderDedupe);
  control.addEventListener("change", renderDedupe);
}});
document.querySelector("#downloadDedupeCsv").addEventListener("click", downloadDedupeCsv);
document.querySelector("#copyDedupeMarkdown").addEventListener("click", event => copyDedupeText(dedupeMarkdown(visibleDedupeGroups()), "已复制", event.currentTarget));
document.querySelector("#copyDedupeCommands").addEventListener("click", event => copyDedupeText((window.PAPER_WIKI.commands || []).join("\\n"), "已复制", event.currentTarget));
document.querySelectorAll(".copy-dedupe-row").forEach(button => {{
  button.addEventListener("click", () => copyDedupeText(button.dataset.checklist || "", "已复制", button));
}});
document.querySelectorAll(".copy-dedupe-command").forEach(button => {{
  button.addEventListener("click", () => copyDedupeText(button.dataset.command || "", "已复制", button));
}});
renderDedupe();
</script>
"""
    (report_dir / "dedupe.html").write_text(page_shell("去重工作台", body, data=payload), encoding="utf-8")


def render_alias_suggestion_row(item: dict[str, Any]) -> str:
    aliases = item.get("aliases") or {}
    alias_text = ", ".join(f"{alias} -> {canonical}" for alias, canonical in aliases.items())
    fields = ", ".join(str(field) for field in item.get("fields", []))
    slugs = ", ".join(str(slug) for slug in item.get("slugs", [])[:8])
    snippet = html.escape(json.dumps({"label_aliases": aliases}, ensure_ascii=False, indent=2))
    return (
        "<tr>"
        f"<td><strong>{html.escape(str(item.get('canonical') or ''))}</strong><div class=\"meta\">{html.escape(fields)}</div></td>"
        f"<td>{html.escape(alias_text)}</td>"
        f"<td>{html.escape(slugs)}{' ...' if len(item.get('slugs', [])) > 8 else ''}</td>"
        f"<td><pre class=\"config-snippet\"><code>{snippet}</code></pre></td>"
        "</tr>"
    )


def render_duplicate_report_row(item: dict[str, Any]) -> str:
    paper_links = []
    for paper in item.get("papers", []):
        title = paper.get("title_zh") or paper.get("title") or paper.get("slug")
        href = str(paper.get("html_path") or f"{paper.get('slug')}.html")
        paper_links.append(f'<a href="{html.escape(href)}">{html.escape(str(title))}</a>')
    return (
        "<tr>"
        f"<td>{html.escape(str(item.get('reason') or ''))}</td>"
        f"<td>{html.escape(str(item.get('value') or ''))}</td>"
        f"<td>{', '.join(paper_links)}</td>"
        f"<td>{html.escape(', '.join(str(slug) for slug in item.get('slugs', [])))}</td>"
        "</tr>"
    )


def render_taxonomy_load_row(item: dict[str, Any]) -> str:
    title = item.get("title_zh") or item.get("title") or item.get("slug")
    href = str(item.get("html_path") or f"{item.get('slug')}.html")
    signals = "".join(f'<span class="flag">{html.escape(str(signal))}</span>' for signal in item.get("signals", []))
    return (
        "<tr>"
        f'<td><a href="{html.escape(href)}">{html.escape(str(title))}</a><div class="meta">{html.escape(str(item.get("research_line") or ""))}</div></td>'
        f"<td>{html.escape(str(item.get('structure_count') or 0))}</td>"
        f"<td>{html.escape(str(item.get('topic_count') or 0))}</td>"
        f"<td>{html.escape(str(item.get('method_count') or 0))}</td>"
        f"<td>{signals}</td>"
        f"<td>{html.escape(str(item.get('recommendation') or ''))}</td>"
        "</tr>"
    )


def render_quality(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    quality = build_quality_report(papers)
    issue_rows = "".join(render_quality_issue_row(issue) for issue in quality["issues"])
    taxonomy_load_rows = "".join(render_taxonomy_load_row(item) for item in quality["taxonomy_load"])
    drift_rows = "".join(render_quality_drift_row(item) for item in quality["taxonomy_drift"])
    alias_rows = "".join(render_alias_suggestion_row(item) for item in quality["label_alias_suggestions"])
    duplicate_report_rows = "".join(render_duplicate_report_row(item) for item in quality["duplicate_reports"])
    duplicate_inbox = [item for item in inbox_items if item.get("duplicate")]
    duplicate_rows = "".join(render_quality_inbox_row(item) for item in duplicate_inbox)

    issue_table = (
        '<table class="data-table"><thead><tr><th>论文</th><th>分数</th><th>缺失字段</th><th>弱字段</th><th>复习</th></tr></thead>'
        f"<tbody>{issue_rows}</tbody></table>"
        if issue_rows
        else '<div class="empty">暂无质量问题。</div>'
    )
    drift_table = (
        '<table class="data-table"><thead><tr><th>论文</th><th>字段</th><th>当前值</th><th>允许值</th></tr></thead>'
        f"<tbody>{drift_rows}</tbody></table>"
        if drift_rows
        else '<div class="empty">暂无 taxonomy drift。</div>'
    )
    taxonomy_load_table = (
        '<table class="data-table"><thead><tr><th>论文</th><th>结构标签</th><th>Topic</th><th>Method</th><th>信号</th><th>建议</th></tr></thead>'
        f"<tbody>{taxonomy_load_rows}</tbody></table>"
        if taxonomy_load_rows
        else '<div class="empty">分类粒度稳定。</div>'
    )
    duplicate_table = (
        '<table class="data-table"><thead><tr><th>候选论文</th><th>链接</th><th>状态</th><th>备注</th></tr></thead>'
        f"<tbody>{duplicate_rows}</tbody></table>"
        if duplicate_rows
        else '<div class="empty">暂无疑似重复候选。</div>'
    )
    alias_table = (
        '<table class="data-table"><thead><tr><th>建议规范值</th><th>建议别名</th><th>涉及论文</th><th>taxonomy.json 片段</th></tr></thead>'
        f"<tbody>{alias_rows}</tbody></table>"
        if alias_rows
        else '<div class="empty">暂无标签归一化建议。</div>'
    )
    duplicate_report_table = (
        '<table class="data-table"><thead><tr><th>重复依据</th><th>匹配值</th><th>论文</th><th>Slug</th></tr></thead>'
        f"<tbody>{duplicate_report_rows}</tbody></table>"
        if duplicate_report_rows
        else '<div class="empty">暂无库内重复报告。</div>'
    )
    queue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td>{len(slugs)}</td>"
        f"<td>{html.escape(', '.join(slugs[:10]))}{' ...' if len(slugs) > 10 else ''}</td>"
        "</tr>"
        for name, slugs in quality["queues"].items()
    )
    queue_table = (
        '<table class="data-table"><thead><tr><th>队列</th><th>数量</th><th>样例 slug</th></tr></thead>'
        f"<tbody>{queue_rows}</tbody></table>"
    )
    metrics = [
        ("质量分", str(quality["quality_score"]), "综合得分"),
        ("分类覆盖", quality["coverage"]["taxonomy"], "必要字段"),
        ("复习计划", quality["coverage"]["review_plan"], "next_review"),
        ("漂移项", str(len(quality["taxonomy_drift"])), "taxonomy drift"),
        ("粒度提示", str(len(quality["taxonomy_load"])), "taxonomy load"),
        ("别名建议", str(len(quality["label_alias_suggestions"])), "label aliases"),
        ("库内重复", str(len(quality["duplicate_reports"])), "duplicate reports"),
        ("重复候选", str(len(duplicate_inbox)), "inbox"),
    ]
    metric_html = "".join(
        f'<section class="metric-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><span>{html.escape(note)}</span></section>'
        for label, value, note in metrics
    )
    quality_commands = [
        ("质量门禁", "python3 scripts/check_quality.py docs"),
        ("严格校验", "python3 scripts/validate_wiki.py docs --strict-taxonomy"),
        ("预览候选论文导入", "python3 scripts/apply_inbox_items.py docs --input <candidate_csv>"),
        ("写入候选论文导入", "python3 scripts/apply_inbox_items.py docs --input <candidate_csv> --write"),
        ("预览元数据写入", "python3 scripts/apply_library_metadata.py docs --input <csv>"),
        ("预览别名写入", "python3 scripts/apply_taxonomy_aliases.py docs"),
        ("写入别名建议", "python3 scripts/apply_taxonomy_aliases.py docs --write"),
        ("预览状态流写入", "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json>"),
        ("写入状态流配置", "python3 scripts/apply_status_workflow.py docs --input <taxonomy_status_workflow.json> --write"),
        ("预览共享视图写入", "python3 scripts/apply_shared_views.py docs --input <shared_views.json>"),
        ("写入共享视图", "python3 scripts/apply_shared_views.py docs --input <shared_views.json> --write"),
        ("导出统一行动清单", "python3 scripts/export_actions.py docs --output docs/exports/actions.md"),
        ("导出统一项目任务", "python3 scripts/export_actions.py docs --format project --output docs/exports/actions-project.csv"),
        ("导出批次清单", "python3 scripts/export_batches.py docs --output docs/exports/batches.md"),
        ("导出批次项目任务", "python3 scripts/export_batches.py docs --format project --severity high --output docs/exports/batches-project.csv"),
        ("导出批次复习 patch", "python3 scripts/export_batches.py docs --format patch --gap review --field review_stage --set-value due --output docs/exports/batches-review-patch.csv"),
        ("导出覆盖缺口清单", "python3 scripts/export_coverage.py docs --output docs/exports/coverage.md"),
        ("导出覆盖项目任务", "python3 scripts/export_coverage.py docs --format project --risk high --risk medium --output docs/exports/coverage-project.csv"),
        ("导出覆盖 topic patch", "python3 scripts/export_coverage.py docs --format patch --field topics --set-value <topic> --output docs/exports/coverage-topic-patch.csv"),
        ("导出研究缺口清单", "python3 scripts/export_gaps.py docs --output docs/exports/gaps.md"),
        ("导出研究缺口项目任务", "python3 scripts/export_gaps.py docs --format project --min-priority 20 --output docs/exports/gaps-project.csv"),
        ("导出视图目录清单", "python3 scripts/export_views.py docs --output docs/exports/views.md"),
        ("导出桌面侧边栏视图", "python3 scripts/export_views.py docs --format sidebar --min-count 1 --output docs/exports/views-sidebar.json"),
        ("导出视图状态 patch", "python3 scripts/export_views.py docs --format patch --view <view_id_or_name> --field status --set-value reading --output docs/exports/views-status-patch.csv"),
        ("导出集合清单", "python3 scripts/export_collections.py docs --output docs/exports/collections.md"),
        ("导出集合项目任务", "python3 scripts/export_collections.py docs --format project --output docs/exports/collections-project.csv"),
        ("导出 Owner 工作量", "python3 scripts/export_ownership.py docs --output docs/exports/ownership.md"),
        ("导出 Owner 项目任务", "python3 scripts/export_ownership.py docs --format project --only-open-queues --output docs/exports/ownership-project.csv"),
        ("导出路线图清单", "python3 scripts/export_roadmap.py docs --output docs/exports/roadmap.md"),
        ("导出路线图项目任务", "python3 scripts/export_roadmap.py docs --format project --output docs/exports/roadmap-project.csv"),
        ("导出治理清单", "python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md"),
        ("导出高优先级 CSV", "python3 scripts/export_taxonomy_actions.py docs --format csv --severity high --output docs/exports/taxonomy-actions.csv"),
        ("导出项目任务", "python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv"),
        ("导出合并补丁模板", "python3 scripts/export_taxonomy_actions.py docs --format patch --action merge_candidate --output docs/exports/taxonomy-action-patch.csv"),
        ("导出均衡任务", "python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --output docs/exports/taxonomy-balance-project.csv"),
        ("导出粒度审计", "python3 scripts/export_taxonomy_load.py docs --format csv --output docs/exports/taxonomy-load.csv"),
        ("导出分类补丁", "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv"),
    ]
    command_buttons = "".join(
        f'<button class="button copy-quality-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(label)}</button>'
        for label, command in quality_commands
    )

    body = f"""
<header class="shell">
  <div class="eyebrow">Quality Gate</div>
  <h1>质量治理</h1>
  <p class="lead">把分类漂移、弱元数据、复习计划和候选论文去重集中到一个发布前检查视图。适合论文库变大后做持续治理。</p>
  <div class="stats">
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="quality.json">质量 JSON</a>
    <span class="stat">论文 {quality["count"]}</span>
    <span class="stat">生成时间 {html.escape(quality["generated_at"])}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">质量门禁</h2>
    <div class="metric-grid">{metric_html}</div>
  </section>
  <section>
    <h2 class="section-title">治理命令</h2>
    <div class="command-panel">
      <div class="bulk-actions">{command_buttons}</div>
      <p class="meta">复制后在仓库根目录执行；带 --write 的命令会修改文件，建议先运行对应预览命令。</p>
    </div>
  </section>
  <section>
    <h2 class="section-title">待处理问题</h2>
    <div class="table-wrap">{issue_table}</div>
  </section>
  <section>
    <h2 class="section-title">Taxonomy Drift</h2>
    <div class="table-wrap">{drift_table}</div>
  </section>
  <section>
    <h2 class="section-title">分类粒度审计</h2>
    <div class="results-bar">
      <strong>{len(quality["taxonomy_load"])} 篇需要检查分类粒度</strong>
      <div class="results-actions"><button id="downloadTaxonomyLoad" class="button" type="button">下载粒度 CSV</button></div>
    </div>
    <div class="table-wrap">{taxonomy_load_table}</div>
  </section>
  <section>
    <h2 class="section-title">标签归一化建议</h2>
    <div class="table-wrap">{alias_table}</div>
  </section>
  <section>
    <h2 class="section-title">库内重复报告</h2>
    <div class="table-wrap">{duplicate_report_table}</div>
  </section>
  <section>
    <h2 class="section-title">候选去重</h2>
    <div class="table-wrap">{duplicate_table}</div>
  </section>
  <section>
    <h2 class="section-title">队列摘要</h2>
    {queue_table}
  </section>
</main>
<script>
async function copyQualityCommand(button) {{
  const command = button.dataset.command || "";
  try {{
    await navigator.clipboard.writeText(command);
    button.textContent = "已复制";
    setTimeout(() => button.textContent = button.dataset.label, 1200);
  }} catch {{
    window.prompt("复制命令", command);
  }}
}}

document.querySelectorAll(".copy-quality-command").forEach(button => {{
  button.dataset.label = button.textContent;
  button.addEventListener("click", () => copyQualityCommand(button));
}});

const taxonomyLoadItems = window.PAPER_WIKI.taxonomy_load || [];
const downloadTaxonomyLoad = document.querySelector("#downloadTaxonomyLoad");

function qualityCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function downloadTaxonomyLoadCsv() {{
  if (!taxonomyLoadItems.length) {{
    window.alert("当前没有分类粒度提示。");
    return;
  }}
  const header = ["slug", "title", "research_line", "structure_count", "topic_count", "method_count", "tag_count", "signals", "recommendation"];
  const rows = taxonomyLoadItems.map(item => [
    item.slug,
    item.title_zh || item.title,
    item.research_line,
    item.structure_count,
    item.topic_count,
    item.method_count,
    item.tag_count,
    (item.signals || []).join("; "),
    item.recommendation,
  ]);
  const csv = [header, ...rows].map(row => row.map(qualityCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "taxonomy_load_audit.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

if (downloadTaxonomyLoad) downloadTaxonomyLoad.addEventListener("click", downloadTaxonomyLoadCsv);
</script>
"""
    quality_css = "\n".join(
        [
            "    .config-snippet {",
            "      margin: 0;",
            "      padding: 10px;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      background: #f8fafc;",
            "      overflow-x: auto;",
            "      font-size: 12px;",
            "      line-height: 1.5;",
            "    }",
            "    .command-panel {",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      background: var(--panel);",
            "      padding: 12px;",
            "    }",
        ]
    )
    (report_dir / "quality.html").write_text(
        page_shell("质量治理", body, {"taxonomy_load": quality["taxonomy_load"]}, quality_css),
        encoding="utf-8",
    )


def render_actions(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_action_center(papers, inbox_items)
    actions = payload["actions"]
    group_options = "".join(
        f'<option value="{html.escape(group, quote=True)}">{html.escape(group)} ({count})</option>'
        for group, count in sorted(payload["summary"]["groups"].items())
    )
    severity_options = "".join(
        f'<option value="{html.escape(severity, quote=True)}">{html.escape(severity)} ({count})</option>'
        for severity, count in sorted(payload["summary"]["severity"].items())
    )
    source_values = Counter(str(item["source"]) for item in actions)
    source_options = "".join(
        f'<option value="{html.escape(source, quote=True)}">{html.escape(source)} ({count})</option>'
        for source, count in sorted(source_values.items())
    )

    def row(action: dict[str, Any]) -> str:
        slugs = ", ".join(str(slug) for slug in action.get("slugs", [])[:3])
        more = len(action.get("slugs", [])) - 3
        if more > 0:
            slugs += f" +{more}"
        command = str(action.get("command") or "")
        return (
            f'<tr data-group="{html.escape(str(action["group"]), quote=True)}" '
            f'data-severity="{html.escape(str(action["severity"]), quote=True)}" '
            f'data-source="{html.escape(str(action["source"]), quote=True)}" '
            f'data-priority="{int(action["priority"])}" '
            f'data-title="{html.escape(str(action["title"]), quote=True)}" '
            f'data-detail="{html.escape(str(action["detail"]), quote=True)}" '
            f'data-href="{html.escape(str(action["href"]), quote=True)}" '
            f'data-command="{html.escape(command, quote=True)}" '
            f'data-search="{html.escape(" ".join([str(action["group"]), str(action["severity"]), str(action["source"]), str(action["title"]), str(action["detail"]), slugs, command]).lower(), quote=True)}">'
            f'<td><span class="flag">{html.escape(str(action["severity"]))}</span><div class="meta">P{int(action["priority"])}</div></td>'
            f'<td><a href="{html.escape(str(action["href"]))}">{html.escape(str(action["title"]))}</a><div class="meta">{html.escape(str(action["detail"]))}</div></td>'
            f'<td>{html.escape(str(action["group"]))}</td>'
            f'<td>{html.escape(str(action["source"]))}</td>'
            f'<td>{html.escape(slugs or "-")}</td>'
            f'<td>{"<code>" + html.escape(command) + "</code>" if command else "-"}</td>'
            "</tr>"
        )

    rows = "".join(row(action) for action in actions)
    actions_json = json.dumps(actions, ensure_ascii=False).replace("</", "<\\/")
    actions_css = """
    .actions-controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(140px, 190px)) repeat(3, auto);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .actions-controls input,
    .actions-controls select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px 12px;
      color: var(--ink);
      font: inherit;
    }
    .actions-table {
      min-width: 1040px;
    }
    .actions-table code {
      white-space: normal;
      overflow-wrap: anywhere;
    }
    @media (max-width: 900px) {
      .actions-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Action Center</div>
  <h1>行动中心</h1>
  <p class="lead">把复习、质量、分类治理、重复项和 inbox 高优先级候选汇成一个统一队列。适合论文库变大后集中分派任务、导出项目清单和周复盘。</p>
  <div class="stats">
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="actions.json">Actions JSON</a>
    <span class="stat">任务 {payload["count"]}</span>
    <span class="stat">High {payload["summary"]["severity"].get("high", 0)}</span>
    <span class="stat">Medium {payload["summary"]["severity"].get("medium", 0)}</span>
  </div>
</header>
<main class="shell">
  <section class="metric-grid">
    <section class="metric-card"><span>全部任务</span><strong>{payload["count"]}</strong><span>统一运营队列</span></section>
    <section class="metric-card"><span>高优先级</span><strong>{payload["summary"]["severity"].get("high", 0)}</strong><span>发布或维护优先处理</span></section>
    <section class="metric-card"><span>分类任务</span><strong>{payload["summary"]["groups"].get("taxonomy", 0)}</strong><span>标签、粒度和 drift</span></section>
    <section class="metric-card"><span>复习任务</span><strong>{payload["summary"]["groups"].get("review", 0)}</strong><span>到期或缺计划</span></section>
  </section>
  <section>
    <h2 class="section-title">统一队列</h2>
    <div class="actions-controls">
      <input id="actionSearch" type="search" placeholder="搜索标题、详情、slug、命令">
      <select id="actionGroup"><option value="">全部分组</option>{group_options}</select>
      <select id="actionSeverity"><option value="">全部优先级</option>{severity_options}</select>
      <select id="actionSource"><option value="">全部来源</option>{source_options}</select>
      <strong id="actionCount">{len(actions)} 项</strong>
      <button id="downloadActionsCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyActionsMarkdown" class="button" type="button">复制任务清单</button>
    </div>
    <div class="table-wrap">
      <table class="data-table actions-table"><thead><tr><th>优先级</th><th>任务</th><th>分组</th><th>来源</th><th>论文</th><th>命令</th></tr></thead><tbody id="actionRows">{rows}</tbody></table>
    </div>
  </section>
</main>
<script>
const actionPayload = {actions_json};
const actionSearch = document.querySelector("#actionSearch");
const actionGroup = document.querySelector("#actionGroup");
const actionSeverity = document.querySelector("#actionSeverity");
const actionSource = document.querySelector("#actionSource");
const actionCount = document.querySelector("#actionCount");
const actionBody = document.querySelector("#actionRows");
const actionRows = Array.from(document.querySelectorAll("#actionRows tr"));
const downloadActionsCsv = document.querySelector("#downloadActionsCsv");
const copyActionsMarkdown = document.querySelector("#copyActionsMarkdown");
const actionSeverityRank = {{ high: 0, medium: 1, low: 2, none: 3 }};

function visibleActionRows() {{
  return actionRows.filter(row => !row.hidden);
}}

function actionCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function sortActionRows(rows) {{
  return [...rows].sort((a, b) => {{
    const severity = (actionSeverityRank[a.dataset.severity] ?? 9) - (actionSeverityRank[b.dataset.severity] ?? 9);
    if (severity) return severity;
    return Number(b.dataset.priority || 0) - Number(a.dataset.priority || 0) || a.dataset.title.localeCompare(b.dataset.title);
  }});
}}

function renderActionRows() {{
  const q = actionSearch.value.trim().toLowerCase();
  const group = actionGroup.value;
  const severity = actionSeverity.value;
  const source = actionSource.value;
  let visible = 0;
  actionRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!group || row.dataset.group === group)
      && (!severity || row.dataset.severity === severity)
      && (!source || row.dataset.source === source);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  sortActionRows(actionRows).forEach(row => actionBody.appendChild(row));
  actionCount.textContent = `${{visible}} / ${{actionRows.length}} 项`;
}}

function filteredActions() {{
  const visibleIds = new Set(visibleActionRows().map(row => `${{row.dataset.group}}:${{row.dataset.title}}`));
  return actionPayload.filter(action => visibleIds.has(`${{action.group}}:${{action.title}}`));
}}

function downloadCurrentActions() {{
  const actions = filteredActions();
  if (!actions.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const header = ["id", "group", "severity", "priority", "title", "detail", "href", "source", "slugs", "command"];
  const rows = actions.map(action => [action.id, action.group, action.severity, action.priority, action.title, action.detail, action.href, action.source, (action.slugs || []).join(";"), action.command || ""]);
  const csv = [header, ...rows].map(row => row.map(actionCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "actions_filtered.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyActionsQueue() {{
  const actions = filteredActions();
  if (!actions.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const lines = ["# AutoPaperReader Action Queue", ""];
  actions.forEach(action => {{
    lines.push(`- [ ] ${{action.severity}} / P${{action.priority}} / ${{action.group}}: [${{action.title}}](${{action.href}})`);
    lines.push(`  - Source: ${{action.source}}`);
    if (action.detail) lines.push(`  - Detail: ${{action.detail}}`);
    if (action.slugs && action.slugs.length) lines.push(`  - Slugs: ${{action.slugs.join(", ")}}`);
    if (action.command) lines.push("  - Command: `" + action.command + "`");
  }});
  const text = lines.join("\\n") + "\\n";
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt("复制任务清单", text);
  }}
}}

[actionSearch, actionGroup, actionSeverity, actionSource].forEach(control => control.addEventListener("input", renderActionRows));
downloadActionsCsv.addEventListener("click", downloadCurrentActions);
copyActionsMarkdown.addEventListener("click", copyActionsQueue);
renderActionRows();
</script>
"""
    (report_dir / "actions.html").write_text(page_shell("行动中心", body, extra_css=actions_css), encoding="utf-8")


def render_release(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    manifest = build_manifest(report_dir, papers, inbox_items)
    status_label = "可发布" if manifest["publish_ready"] else "需治理"
    check_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td><span class=\"flag\">{'通过' if passed else '待处理'}</span></td>"
        "</tr>"
        for name, passed in manifest["publish_checks"].items()
    )
    page_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(page["href"])}">{html.escape(page["title"])}</a></td>'
        f"<td>{html.escape(page['kind'])}</td>"
        f"<td>{html.escape(page['description'])}</td>"
        "</tr>"
        for page in manifest["pages"]
    )
    data_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(file["href"])}">{html.escape(file["href"])}</a></td>'
        f"<td>{html.escape(file['description'])}</td>"
        "</tr>"
        for file in manifest["data_files"]
    )
    contract_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(file["href"])}">{html.escape(file["href"])}</a></td>'
        f"<td>{html.escape(file['description'])}</td>"
        "</tr>"
        for file in manifest["contract_files"]
    )
    artifact_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["href"]))}</a><div class="meta">{html.escape(str(item["description"]))}</div></td>'
        f"<td>{html.escape(str(item['kind']))}</td>"
        f"<td><span class=\"flag\">{html.escape(str(item['status']))}</span></td>"
        f"<td>{html.escape(str(item.get('size_bytes') or '-'))}</td>"
        f"<td><code>{html.escape(str(item.get('sha256') or '-'))}</code></td>"
        "</tr>"
        for item in manifest["artifact_inventory"]
    )
    queue_rows = "".join(
        "<tr>"
        f"<td>{html.escape(group)}</td>"
        f"<td>{html.escape(name)}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for group, queues in manifest["queue_sizes"].items()
        for name, count in queues.items()
    )
    recipe_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(recipe['label']))}<div class=\"meta\">{html.escape(str(recipe['id']))}</div></td>"
        f"<td>{html.escape(str(recipe['kind']))}</td>"
        f"<td>{html.escape(str(recipe.get('output') or '-'))}</td>"
        f"<td><span class=\"flag\">{'writes' if recipe.get('mutates') else 'read-only'}</span></td>"
        f"<td><code>{html.escape(str(recipe['command']))}</code></td>"
        f'<td><button class="button copy-release-command" type="button" data-command="{html.escape(str(recipe["command"]), quote=True)}">复制</button></td>'
        "</tr>"
        for recipe in manifest["command_recipes"]
    )
    recipe_by_id = {str(recipe["id"]): recipe for recipe in manifest["command_recipes"]}
    playbook_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(playbook['label']))}<div class=\"meta\">{html.escape(str(playbook['id']))}</div></td>"
        f"<td>{html.escape(str(playbook['description']))}</td>"
        f"<td>{'<br>'.join(html.escape(str(recipe_by_id.get(step, {}).get('label', step))) for step in playbook.get('steps', []))}</td>"
        f'<td><button class="button copy-release-command" type="button" data-command="{html.escape(chr(10).join(str(recipe_by_id.get(step, {}).get("command", step)) for step in playbook.get("steps", [])), quote=True)}">复制命令组</button></td>'
        "</tr>"
        for playbook in manifest.get("governance_playbooks", [])
    )
    command_html = "\n".join(html.escape(command) for command in manifest["commands"])
    line_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(page_query_href("library.html", line=line["name"]))}">{html.escape(line["name"])}</a></td>'
        f"<td>{line['count']}</td>"
        f"<td>{html.escape(str(line.get('code_coverage') or ''))}</td>"
        f"<td>{html.escape(str(line.get('avg_importance') or ''))}</td>"
        "</tr>"
        for line in manifest["research_lines"]
    )
    body = f"""
<header class="shell">
  <div class="eyebrow">Release Manifest</div>
  <h1>知识库发布摘要</h1>
  <p class="lead">面向开源、团队同步或桌面软件封装的发布视图：集中展示当前论文库质量、页面入口、机器可读数据、运营队列和推荐检查命令。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="manifest.json">Manifest JSON</a>
    <span class="stat">状态 {html.escape(status_label)}</span>
    <span class="stat">论文 {manifest["count"]}</span>
    <span class="stat">质量分 {manifest["quality_score"]}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">发布状态</h2>
    <div class="metric-grid">
      <section class="metric-card"><span>状态</span><strong>{html.escape(status_label)}</strong><span>publish_ready = {str(manifest["publish_ready"]).lower()}</span></section>
      <section class="metric-card"><span>质量分</span><strong>{manifest["quality_score"]}</strong><span>元数据和复习综合分</span></section>
      <section class="metric-card"><span>分类覆盖</span><strong>{html.escape(str(manifest["coverage"]["taxonomy"]))}</strong><span>必要 taxonomy 字段</span></section>
      <section class="metric-card"><span>代码覆盖</span><strong>{html.escape(str(manifest["coverage"]["code_observation"]))}</strong><span>代码观察或线索</span></section>
      <section class="metric-card"><span>库内重复</span><strong>{manifest["queue_sizes"]["quality"].get("duplicate_reports", 0)}</strong><span>重复报告组相关论文</span></section>
    </div>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>检查项</th><th>状态</th></tr></thead><tbody>{check_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">页面入口</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>页面</th><th>类型</th><th>用途</th></tr></thead><tbody>{page_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">机器可读数据</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>用途</th></tr></thead><tbody>{data_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">数据契约</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>文件</th><th>用途</th></tr></thead><tbody>{contract_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">Artifact Inventory</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>产物</th><th>类型</th><th>状态</th><th>Bytes</th><th>SHA-256</th></tr></thead><tbody>{artifact_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">队列规模</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>分组</th><th>队列</th><th>数量</th></tr></thead><tbody>{queue_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">研究线摘要</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>研究线</th><th>论文</th><th>代码覆盖</th><th>平均重要性</th></tr></thead><tbody>{line_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">推荐命令</h2>
    <pre class="config-snippet"><code>{command_html}</code></pre>
  </section>
  <section>
    <h2 class="section-title">命令 Recipes</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>命令</th><th>类型</th><th>输出</th><th>写入</th><th>CLI</th><th>操作</th></tr></thead><tbody>{recipe_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">治理 Playbooks</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>批次</th><th>用途</th><th>步骤</th><th>操作</th></tr></thead><tbody>{playbook_rows}</tbody></table></div>
  </section>
</main>
<script>
async function copyReleaseCommand(button) {{
  const command = button.dataset.command || "";
  try {{
    await navigator.clipboard.writeText(command);
    const oldText = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => button.textContent = oldText, 1400);
  }} catch (error) {{
    window.prompt("复制命令", command);
  }}
}}
document.querySelectorAll(".copy-release-command").forEach(button => {{
  button.addEventListener("click", () => copyReleaseCommand(button));
}});
</script>
"""
    release_css = "\n".join(
        [
            "    .config-snippet {",
            "      margin: 0;",
            "      padding: 12px;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      background: #f8fafc;",
            "      overflow-x: auto;",
            "      font-size: 13px;",
            "      line-height: 1.55;",
            "    }",
        ]
    )
    (report_dir / "release.html").write_text(page_shell("知识库发布摘要", body, extra_css=release_css), encoding="utf-8")


def render_snapshot(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    snapshot = build_snapshot_payload(report_dir, papers, inbox_items)
    check_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td><span class=\"flag\">{'通过' if passed else '待处理'}</span></td>"
        "</tr>"
        for name, passed in snapshot["publish_checks"].items()
    )
    risk_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for name, count in snapshot["risk_queue_sizes"].items()
    )
    action_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['group']))}</td>"
        f"<td>{item['count']}</td>"
        "</tr>"
        for item in snapshot["action_groups"]
    )
    line_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(page_query_href("library.html", line=str(line.get("name") or "")))}">{html.escape(str(line.get("name") or ""))}</a></td>'
        f"<td>{line.get('count')}</td>"
        f"<td>{html.escape(str(line.get('code_coverage') or ''))}</td>"
        f"<td>{html.escape(str(line.get('avg_importance') or ''))}</td>"
        "</tr>"
        for line in snapshot["research_lines"]
    )
    policy_rows = "".join(
        "<tr>"
        f"<td>{html.escape(section)}</td>"
        f"<td><code>{html.escape(json.dumps(values, ensure_ascii=False, sort_keys=True))}</code></td>"
        "</tr>"
        for section, values in snapshot["governance_policy"].items()
    )
    artifact_rows = "".join(
        "<tr>"
        f'<td><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["href"]))}</a></td>'
        f"<td>{html.escape(str(item.get('kind') or ''))}</td>"
        f"<td><span class=\"flag\">{html.escape(str(item.get('status') or ''))}</span></td>"
        f"<td><code>{html.escape(str(item.get('sha256') or ''))}</code></td>"
        "</tr>"
        for item in snapshot["artifact_summary"]["hashes"][:80]
    )
    body = f"""
<header class="shell">
  <div class="eyebrow">Governance Snapshot</div>
  <h1>治理快照</h1>
  <p class="lead">当前知识库的可审计基线：发布状态、治理队列、策略阈值、研究线摘要和关键产物哈希。适合开源协作、桌面软件同步和周期性复盘。</p>
  <div class="stats">
    <a class="stat" href="release.html">发布摘要</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="actions.html">行动中心</a>
    <a class="stat" href="snapshot.json">Snapshot JSON</a>
    <a class="stat" href="manifest.json">Manifest JSON</a>
    <span class="stat">ID {html.escape(snapshot["snapshot_id"])}</span>
    <span class="stat">论文 {snapshot["count"]}</span>
    <span class="stat">状态 {'可发布' if snapshot["publish_ready"] else '需治理'}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">基线指标</h2>
    <div class="metric-grid">
      <section class="metric-card"><span>质量分</span><strong>{snapshot["quality_score"]}</strong><span>metadata / review / code</span></section>
      <section class="metric-card"><span>分类覆盖</span><strong>{html.escape(str(snapshot["coverage"]["taxonomy"]))}</strong><span>必要 taxonomy 字段</span></section>
      <section class="metric-card"><span>复习计划</span><strong>{html.escape(str(snapshot["coverage"]["review_plan"]))}</strong><span>next_review 覆盖</span></section>
      <section class="metric-card"><span>Artifact</span><strong>{snapshot["artifact_summary"]["count"]}</strong><span>缺失 {len(snapshot["artifact_summary"]["missing"])}</span></section>
    </div>
  </section>
  <section>
    <h2 class="section-title">发布检查</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>检查项</th><th>状态</th></tr></thead><tbody>{check_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">风险队列</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>队列</th><th>数量</th></tr></thead><tbody>{risk_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">行动分布</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>分组</th><th>数量</th></tr></thead><tbody>{action_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">研究线摘要</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>研究线</th><th>论文</th><th>代码覆盖</th><th>平均重要性</th></tr></thead><tbody>{line_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">治理策略</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>策略组</th><th>阈值</th></tr></thead><tbody>{policy_rows}</tbody></table></div>
  </section>
  <section>
    <h2 class="section-title">Artifact Hashes</h2>
    <div class="table-wrap"><table class="data-table"><thead><tr><th>产物</th><th>类型</th><th>状态</th><th>SHA-256</th></tr></thead><tbody>{artifact_rows}</tbody></table></div>
  </section>
</main>
"""
    (report_dir / "snapshot.html").write_text(page_shell("治理快照", body), encoding="utf-8")


def render_dashboard(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    quality = build_quality_report(papers)
    review_plan = build_review_plan(papers)
    today = dt.date.today().isoformat()
    total = len(papers)
    with_code = sum(1 for paper in papers if paper.get("has_code"))
    high_importance = [paper for paper in papers if int(paper.get("importance") or 0) >= 5]
    due_review = [
        paper
        for paper in papers
        if paper.get("next_review") and str(paper.get("next_review")) <= today
    ]
    missing_taxonomy = [
        paper
        for paper in papers
        if not paper.get("domains")
        or not paper.get("tracks")
        or not paper.get("topics")
        or not paper.get("methods")
        or paper.get("research_line") == "Unassigned"
        or not paper.get("line_role")
    ]
    no_code_observation = [paper for paper in papers if not paper.get("has_code")]
    no_review_plan = [paper for paper in papers if not paper.get("next_review")]

    metrics = [
        ("论文", str(total), "已纳入 wiki 的报告数"),
        ("质量分", str(quality["quality_score"]), "元数据、复习计划和代码观察综合分"),
        ("研究线", str(len(scalar_counts(papers, "research_line"))), "有明确 research_line 的脉络"),
        ("代码覆盖", percent(with_code, total), "包含代码观察或代码仓库线索"),
        ("分类覆盖", quality["coverage"]["taxonomy"], "必要 taxonomy 字段完整"),
        ("高优先级", str(len(high_importance)), "importance >= 5"),
        ("待复习", str(len(due_review)), f"next_review <= {today}"),
        ("需建复习计划", str(len(review_plan["queues"]["needs_plan"])), "缺 next_review 的建议队列"),
        ("待补分类", str(len(missing_taxonomy)), "缺 taxonomy 或 line role"),
    ]
    metric_html = "".join(
        f'<section class="metric-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><span>{html.escape(note)}</span></section>'
        for label, value, note in metrics
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "Unassigned").strip() or "Unassigned"
        grouped[line].append(paper)

    line_rows = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
        items = grouped[line]
        roles = sorted({paper.get("line_role") or "unclassified" for paper in items}, key=role_rank)
        avg_importance = round(
            sum(int(paper.get("importance") or 0) for paper in items) / len(items),
            1,
        )
        code_count = sum(1 for paper in items if paper.get("has_code"))
        owner = research_line_owner(line)
        owner_label = owner.get("owner") or owner.get("team") or "Unassigned"
        owner_detail = " / ".join(part for part in [owner.get("team", ""), owner.get("cadence", "")] if part)
        line_link = (
            f'<a href="lines/{html.escape(slugify_label(line))}.html">{html.escape(line)}</a>'
            if line != "Unassigned"
            else html.escape(line)
        )
        line_rows.append(
            "<tr>"
            f"<td>{line_link}</td>"
            f"<td>{html.escape(owner_label)}<div class=\"meta\">{html.escape(owner_detail)}</div></td>"
            f"<td>{len(items)}</td>"
            f"<td>{html.escape(', '.join(roles))}</td>"
            f"<td>{avg_importance}</td>"
            f"<td>{percent(code_count, len(items))}</td>"
            "</tr>"
        )

    line_table = (
        '<table class="data-table"><thead><tr><th>研究线</th><th>Owner</th><th>论文</th><th>角色</th><th>平均重要性</th><th>代码覆盖</th></tr></thead>'
        f"<tbody>{''.join(line_rows)}</tbody></table>"
        if line_rows
        else '<div class="empty">还没有研究线。</div>'
    )
    balance_rows = []
    for row in sorted(taxonomy_balance_report(papers), key=lambda item: (item["balance_score"], -item["singleton_count"], item["label"])):
        max_value = str(row.get("max_value") or "")
        max_href = page_query_href("library.html", **{str(row["query_key"]): max_value}) if max_value else "library.html"
        balance_rows.append(
            "<tr>"
            f"<td>{html.escape(str(row['label']))}<div class=\"meta\">{html.escape(str(row['english']))}</div></td>"
            f"<td>{row['balance_score']}</td>"
            f"<td>{row['used_count']} / {row['configured_count']}</td>"
            f"<td>{row['singleton_count']}</td>"
            f"<td>{row['overloaded_count']}</td>"
            f'<td><a href="{html.escape(max_href)}">{html.escape(max_value or "-")}</a> <span class="meta">{round(float(row["max_share"]) * 100)}%</span></td>'
            "</tr>"
        )
    balance_table = (
        '<table class="data-table"><thead><tr><th>字段</th><th>均衡分</th><th>已用/配置</th><th>长尾</th><th>过载</th><th>最大值</th></tr></thead>'
        f"<tbody>{''.join(balance_rows)}</tbody></table>"
    )

    def queue(title: str, items: list[dict[str, Any]], empty: str) -> str:
        if items:
            rows = "".join(
                f'<li><a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
                f' <span class="meta">{html.escape(str(paper.get("research_line") or ""))}</span></li>'
                for paper in items[:12]
            )
            content = f'<ol class="queue-list">{rows}</ol>'
        else:
            content = f'<div class="empty">{html.escape(empty)}</div>'
        return f'<section class="role-section"><h2>{html.escape(title)} <span class="meta">{len(items)}</span></h2>{content}</section>'

    queues = [
        queue("高优先级", sorted(high_importance, key=lambda p: (-(p.get("importance") or 0), p["title"])), "暂无 5 星论文。"),
        queue("待补分类", missing_taxonomy, "taxonomy 覆盖完整。"),
        queue("待复习", due_review, "没有到期复习项。"),
        queue("未设置复习", no_review_plan, "所有论文都有 next_review。"),
        queue("无代码观察", no_code_observation, "所有论文都有代码观察或代码线索。"),
    ]
    quality_rows = "".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td>{len(slugs)}</td>"
        f"<td>{html.escape(', '.join(slugs[:8]))}{' ...' if len(slugs) > 8 else ''}</td>"
        "</tr>"
        for name, slugs in quality["queues"].items()
    )
    quality_table = (
        '<table class="data-table"><thead><tr><th>队列</th><th>数量</th><th>样例 slug</th></tr></thead>'
        f"<tbody>{quality_rows}</tbody></table>"
    )

    body = f"""
<header class="shell">
  <div class="eyebrow">Knowledge Base Operations</div>
  <h1>管理控制台</h1>
  <p class="lead">面向大量论文的运营视图：看分类覆盖、研究线健康度、复习队列和需要补元数据的报告。所有数据来自 markdown frontmatter 与 wiki 索引。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="inbox.html">待处理池</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="tags.html">分类总览</a>
    <a class="stat" href="quality.json">质量 JSON</a>
    <a class="stat" href="stats.json">统计 JSON</a>
    <span class="stat">生成时间 {html.escape(dt.datetime.now().isoformat(timespec="seconds"))}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">总览</h2>
    <div class="metric-grid">{metric_html}</div>
  </section>
  <section>
    <h2 class="section-title">研究线健康度</h2>
    {line_table}
  </section>
  <section>
    <h2 class="section-title">分类均衡度</h2>
    {balance_table}
  </section>
  <section>
    <h2 class="section-title">管理队列</h2>
    <div class="queue-grid">{''.join(queues)}</div>
  </section>
  <section>
    <h2 class="section-title">质量队列</h2>
    {quality_table}
  </section>
</main>
"""
    (report_dir / "dashboard.html").write_text(page_shell("管理控制台", body), encoding="utf-8")


def collection_paper_summary(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or paper["slug"],
        "title_zh": paper.get("title_zh") or paper.get("title") or paper["slug"],
        "href": paper_href(paper),
        "research_line": paper.get("research_line") or "Unassigned",
        "line_role": paper.get("line_role") or "",
        "year": paper.get("year") or "",
        "importance": paper.get("importance") or "",
        "status": paper.get("status") or "",
        "reading_stage": paper.get("reading_stage") or "",
        "review_stage": paper.get("review_stage") or "",
        "next_review": paper.get("next_review") or "",
    }


def build_views_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review_plan = build_review_plan(papers)
    today = dt.date.today().isoformat()
    paper_by_slug = {paper["slug"]: paper for paper in papers}

    def by_slugs(slugs: list[str]) -> list[dict[str, Any]]:
        return [paper_by_slug[slug] for slug in slugs if slug in paper_by_slug]

    def summarize(view: dict[str, Any], source: str, kind: str, note: str = "") -> dict[str, Any]:
        page = str(view.get("page") or "library")
        state = {
            str(key): str(value)
            for key, value in (view.get("state") or {}).items()
            if str(value).strip()
        }
        matched = [paper for paper in papers if matches_view_state(paper, state, today)]
        name = str(view.get("name") or "Untitled view")
        identity = json.dumps({"source": source, "kind": kind, "page": page, "name": name, "state": state}, ensure_ascii=False, sort_keys=True)
        view_id = f"{source}-{slugify_label(page)}-{slugify_label(name)}-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:8]}"
        return {
            "id": view_id,
            "name": name,
            "source": source,
            "kind": kind,
            "page": page,
            "target_page": view_target_page({"page": page}),
            "href": view_href({"page": page, "state": state}),
            "state": state,
            "count": len(matched),
            "slugs": [paper["slug"] for paper in matched],
            "sample_papers": [collection_paper_summary(paper) for paper in matched[:8]],
            "note": note,
            "shared_view": {"name": name, "page": page, "state": state},
            "empty": not matched,
        }

    configured_views = [
        summarize(view, "configured", "shared", "来自 docs/guides/taxonomy.json 的 shared_views。")
        for view in SHARED_VIEWS
    ]

    no_review = by_slugs(list(review_plan["queues"].get("needs_plan", [])))
    missing_taxonomy = by_slugs(list(quality["queues"].get("missing_required_metadata", [])))
    taxonomy_sparse = by_slugs(list(quality["queues"].get("taxonomy_sparse", [])))
    no_code_observation = by_slugs(list(quality["queues"].get("no_code_observation", [])))
    due_review = [
        paper
        for paper in papers
        if paper.get("next_review") and str(paper.get("next_review")) <= today
    ]

    smart_specs = [
        ("重点论文", "library", {"importance": "5", "sort": "importance"}, "高重要性论文，适合周会或路线图优先复盘。"),
        ("待复习", "library", {"review": "due", "sort": "importance"}, f"next_review <= {today} 的复习视图。"),
        ("未设置复习", "library", {"review": "none", "sort": "importance"}, "缺少 next_review 的论文，适合批量补复习计划。"),
        ("有代码", "library", {"code": "yes", "sort": "year"}, "带代码或实现观察的论文。"),
        ("缺代码观察", "library", {"code": "no", "sort": "importance"}, "尚未记录代码仓库或代码实现观察的论文。"),
    ]
    smart_views = [summarize({"name": name, "page": page, "state": state}, "system", "queue", note) for name, page, state, note in smart_specs]
    smart_views.extend(
        [
            {
                **summarize({"name": "待补分类", "page": "library", "state": {"sort": "importance"}}, "system", "queue", "缺必要分类字段的论文，入口指向质量治理。"),
                "href": "quality.html",
                "slugs": [paper["slug"] for paper in missing_taxonomy],
                "count": len(missing_taxonomy),
                "sample_papers": [collection_paper_summary(paper) for paper in missing_taxonomy[:8]],
                "empty": not missing_taxonomy,
            },
            {
                **summarize({"name": "分类偏薄", "page": "library", "state": {"sort": "importance"}}, "system", "queue", "标签粒度不足，影响后续检索和聚类。"),
                "href": "quality.html",
                "slugs": [paper["slug"] for paper in taxonomy_sparse],
                "count": len(taxonomy_sparse),
                "sample_papers": [collection_paper_summary(paper) for paper in taxonomy_sparse[:8]],
                "empty": not taxonomy_sparse,
            },
            {
                **summarize({"name": "复习计划缺口", "page": "library", "state": {"review": "none", "sort": "importance"}}, "system", "queue", "缺少 next_review 的论文，入口指向复习计划。"),
                "href": "review.html",
                "slugs": [paper["slug"] for paper in no_review],
                "count": len(no_review),
                "sample_papers": [collection_paper_summary(paper) for paper in no_review[:8]],
                "empty": not no_review,
            },
            {
                **summarize({"name": "已到复习日", "page": "library", "state": {"review": "due", "sort": "importance"}}, "system", "queue", "已到复习日的论文。"),
                "href": "review.html",
                "slugs": [paper["slug"] for paper in due_review],
                "count": len(due_review),
                "sample_papers": [collection_paper_summary(paper) for paper in due_review[:8]],
                "empty": not due_review,
            },
            {
                **summarize({"name": "代码观察缺口", "page": "library", "state": {"code": "no", "sort": "importance"}}, "system", "queue", "缺代码实现观察的论文，入口指向研究缺口。"),
                "href": "gaps.html",
                "slugs": [paper["slug"] for paper in no_code_observation],
                "count": len(no_code_observation),
                "sample_papers": [collection_paper_summary(paper) for paper in no_code_observation[:8]],
                "empty": not no_code_observation,
            },
        ]
    )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)
    line_views = [
        summarize(
            {"name": f"研究线：{line}", "page": "library", "state": {"line": line, "sort": "importance"}},
            "generated",
            "research_line",
            "按研究线固定入口生成的视图。",
        )
        for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower()))
    ]

    workflow_views = []
    for workflow_name, workflow in sorted((STATUS_WORKFLOWS or {}).items()):
        for status in workflow.get("status_values", []):
            workflow_views.append(
                summarize(
                    {
                        "name": f"{workflow_name} / {status}",
                        "page": "library",
                        "state": {"workflow": workflow_name, "status": status, "sort": "year"},
                    },
                    "generated",
                    "workflow_status",
                    "按状态 workflow 和 status 自动生成的视图。",
                )
            )

    views = configured_views + smart_views + line_views + workflow_views
    source_counts = Counter(str(view["source"]) for view in views)
    kind_counts = Counter(str(view["kind"]) for view in views)
    empty_views = [view for view in views if view["empty"]]
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "view_count": len(views),
        "configured_count": len(configured_views),
        "system_count": len(smart_views),
        "generated_count": len(line_views) + len(workflow_views),
        "source_counts": dict(sorted(source_counts.items())),
        "kind_counts": dict(sorted(kind_counts.items())),
        "empty_view_count": len(empty_views),
        "views": views,
        "recommendations": [
            "把常用筛选从浏览器本地 saved views 提升到 docs/guides/taxonomy.json 的 shared_views，便于多人和桌面端复用。",
            "优先保留命中数稳定、能代表研究线或状态流的视图；空视图可作为未来队列，也可从 shared_views 中移除。",
            "桌面软件或 DMG 外壳可直接读取 views.json，把 href/state/slugs 映射为侧边栏、收藏夹或项目队列。",
        ],
        "commands": [
            "python3 scripts/apply_shared_views.py docs --input <shared_views.json>",
            "python3 scripts/apply_shared_views.py docs --input <shared_views.json> --write",
            "python3 scripts/export_views.py docs --format patch --view <view_id_or_name> --field status --set-value reading --output docs/exports/views-status-patch.csv",
            "python3 scripts/apply_library_metadata.py docs --input docs/exports/views-status-patch.csv",
            "python3 scripts/apply_library_metadata.py docs --input docs/exports/views-status-patch.csv --write",
            "python3 scripts/build_wiki.py docs",
        ],
        "links": {
            "html": "views.html",
            "index": "index.html",
            "library": "library.html",
            "collections": "collections.html",
            "status": "status.html",
            "workflow": "workflow.html",
            "quality": "quality.html",
        },
    }


def write_views_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_views_payload(papers)
    (report_dir / "views.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_views(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_views_payload(papers)

    def sample_list(items: list[dict[str, Any]]) -> str:
        if not items:
            return '<span class="meta">暂无样例</span>'
        links = []
        for paper in items[:3]:
            title = str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or "")
            links.append(f'<a href="{html.escape(str(paper.get("href") or ""))}">{html.escape(title)}</a>')
        more = f' <span class="meta">+{len(items) - 3}</span>' if len(items) > 3 else ""
        return " · ".join(links) + more

    rows = []
    for view in payload["views"]:
        shared = html.escape(json.dumps(view["shared_view"], ensure_ascii=False, sort_keys=True), quote=True)
        slugs = html.escape(json.dumps(view.get("slugs", []), ensure_ascii=False), quote=True)
        state = html.escape(json.dumps(view["state"], ensure_ascii=False, sort_keys=True))
        rows.append(
            f"""<tr data-source="{html.escape(str(view['source']), quote=True)}" data-kind="{html.escape(str(view['kind']), quote=True)}" data-empty="{str(bool(view['empty'])).lower()}" data-view-id="{html.escape(str(view['id']), quote=True)}" data-view-name="{html.escape(str(view['name']), quote=True)}" data-slugs="{slugs}">
  <td><a href="{html.escape(str(view['href']))}">{html.escape(str(view['name']))}</a><div class="meta">{html.escape(str(view['note']))}</div></td>
  <td>{html.escape(str(view['source']))}</td>
  <td>{html.escape(str(view['kind']))}</td>
  <td>{html.escape(str(view['page']))}</td>
  <td>{int(view['count'])}</td>
  <td><code>{state}</code></td>
  <td>{sample_list(view.get('sample_papers', []))}</td>
  <td>
    <button class="button copy-view-json" type="button" data-view="{shared}">复制 JSON</button>
    <button class="button copy-view-patch" type="button">复制 patch</button>
    <button class="button download-view-patch" type="button">下载 patch</button>
    <button class="button copy-view-patch-command" type="button">复制命令</button>
  </td>
</tr>"""
        )

    command_buttons = "".join(
        f'<button class="button copy-view-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command)}</button>'
        for command in payload["commands"]
    )
    source_options = "".join(f'<option value="{html.escape(source)}">{html.escape(source)}</option>' for source in sorted(payload["source_counts"]))
    kind_options = "".join(f'<option value="{html.escape(kind)}">{html.escape(kind)}</option>' for kind in sorted(payload["kind_counts"]))
    data = {"views": payload["views"], "summary": {key: payload[key] for key in ("view_count", "configured_count", "system_count", "generated_count", "empty_view_count")}}
    views_css = """
    .view-toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) 180px 180px 160px;
      gap: 10px;
      align-items: center;
      margin: 18px 0;
    }
    .view-toolbar input,
    .view-toolbar select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fffdf8;
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
    }
    .view-table code {
      white-space: normal;
      word-break: break-word;
      font-size: 12px;
    }
    .view-table .button {
      min-width: 82px;
      justify-content: center;
      margin: 2px;
      padding-inline: 9px;
    }
    .view-patch-panel {
      display: grid;
      grid-template-columns: minmax(150px, 210px) minmax(180px, 1fr) minmax(130px, 180px);
      gap: 10px;
      align-items: end;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      margin: 10px 0 16px;
    }
    .view-patch-panel label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }
    .view-patch-panel input,
    .view-patch-panel select {
      width: 100%;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fffdf8;
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
    }
    .command-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }
    @media (max-width: 820px) {
      .view-toolbar { grid-template-columns: 1fr; }
      .view-patch-panel { grid-template-columns: 1fr; }
      .view-table { min-width: 980px; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">View Directory</div>
  <h1>视图目录</h1>
  <p class="lead">把共享筛选、系统队列、研究线入口和状态工作流入口集中成可版本化目录。论文多起来后，这里就是团队共用的侧边栏和桌面端启动数据。</p>
  <div class="stats">
    <a class="stat" href="views.json">Views JSON</a>
    <a class="stat" href="index.html">首页</a>
    <a class="stat" href="library.html">论文库</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="status.html">状态选择器</a>
    <span class="stat">视图 {payload["view_count"]}</span>
    <span class="stat">共享 {payload["configured_count"]}</span>
    <span class="stat">空视图 {payload["empty_view_count"]}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">筛选视图</h2>
    <div class="view-toolbar">
      <input id="viewSearch" type="search" placeholder="搜索视图、状态或筛选条件">
      <select id="viewSource"><option value="">全部来源</option>{source_options}</select>
      <select id="viewKind"><option value="">全部类型</option>{kind_options}</select>
      <select id="viewEmpty"><option value="">全部命中</option><option value="false">有命中</option><option value="true">空视图</option></select>
    </div>
    <div class="view-patch-panel">
      <label>
        <span>Patch 字段</span>
        <select id="viewPatchField">
          <option value="status">status</option>
          <option value="reading_stage">reading_stage</option>
          <option value="review_stage">review_stage</option>
          <option value="next_review">next_review</option>
          <option value="importance">importance</option>
          <option value="research_line">research_line</option>
          <option value="line_role">line_role</option>
          <option value="domains">domains</option>
          <option value="tracks">tracks</option>
          <option value="problems">problems</option>
          <option value="topics">topics</option>
          <option value="methods">methods</option>
        </select>
      </label>
      <label><span>Patch 值</span><input id="viewPatchValue" type="text" value="reading" placeholder="例如 reading / due / Attention Kernels"></label>
      <label>
        <span>列表模式</span>
        <select id="viewPatchListMode">
          <option value="replace">replace</option>
          <option value="append">append</option>
          <option value="remove">remove</option>
        </select>
      </label>
    </div>
    <div class="table-wrap">
      <table class="data-table view-table">
        <thead><tr><th>视图</th><th>来源</th><th>类型</th><th>页面</th><th>命中</th><th>状态</th><th>样例</th><th>操作</th></tr></thead>
        <tbody id="viewRows">{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
  <section>
    <h2 class="section-title">写回命令</h2>
    <p class="meta">复制某个视图 JSON 后，可保存成文件并用 dry-run 检查，再写回 docs/guides/taxonomy.json。</p>
    <div class="command-strip">{command_buttons}</div>
  </section>
</main>
<script>
(() => {{
  const rows = Array.from(document.querySelectorAll("#viewRows tr"));
  const search = document.querySelector("#viewSearch");
  const source = document.querySelector("#viewSource");
  const kind = document.querySelector("#viewKind");
  const empty = document.querySelector("#viewEmpty");
  const patchField = document.querySelector("#viewPatchField");
  const patchValue = document.querySelector("#viewPatchValue");
  const patchListMode = document.querySelector("#viewPatchListMode");
  const listPatchFields = new Set(["authors", "domains", "tracks", "problems", "topics", "methods"]);
  function csvCell(value) {{
    const text = String(value ?? "");
    return (text.includes(",") || text.includes('"') || text.includes("\\n"))
      ? `"${{text.replaceAll('"', '""')}}"`
      : text;
  }}
  function rowSlugs(row) {{
    try {{
      return JSON.parse(row.dataset.slugs || "[]").map(value => String(value || "").trim()).filter(Boolean);
    }} catch {{
      return [];
    }}
  }}
  function patchCsvFor(row) {{
    const field = patchField.value || "status";
    const value = patchValue.value || "";
    const listField = listPatchFields.has(field);
    const header = listField ? ["slug", field, "_list_mode"] : ["slug", field];
    const body = rowSlugs(row).map(slug => listField ? [slug, value, patchListMode.value || "replace"] : [slug, value]);
    return [header, ...body].map(items => items.map(csvCell).join(",")).join("\\n") + "\\n";
  }}
  function patchCommandFor(row) {{
    const viewId = row.dataset.viewId || row.dataset.viewName || "";
    const field = patchField.value || "status";
    const value = patchValue.value || "";
    const extra = listPatchFields.has(field) ? ` --list-mode ${{patchListMode.value || "replace"}}` : "";
    return `python3 scripts/export_views.py docs --format patch --view "${{viewId.replaceAll('"', '\\\\"')}}" --field ${{field}} --set-value "${{value.replaceAll('"', '\\\\"')}}"${{extra}} --output docs/exports/views-${{field}}-patch.csv`;
  }}
  function downloadText(filename, text, type = "text/csv;charset=utf-8") {{
    const blob = new Blob([text], {{ type }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }}
  async function copyText(value, title) {{
    try {{
      await navigator.clipboard.writeText(value);
    }} catch {{
      window.prompt(title, value);
    }}
  }}
  function applyFilters() {{
    const term = (search.value || "").toLowerCase();
    rows.forEach(row => {{
      const matchesText = !term || row.textContent.toLowerCase().includes(term);
      const matchesSource = !source.value || row.dataset.source === source.value;
      const matchesKind = !kind.value || row.dataset.kind === kind.value;
      const matchesEmpty = !empty.value || row.dataset.empty === empty.value;
      row.hidden = !(matchesText && matchesSource && matchesKind && matchesEmpty);
    }});
  }}
  [search, source, kind, empty].forEach(input => input.addEventListener("input", applyFilters));
  document.querySelectorAll(".copy-view-json").forEach(button => {{
    button.addEventListener("click", async () => {{
      const text = JSON.stringify({{ shared_views: [JSON.parse(button.dataset.view || "{{}}")] }}, null, 2);
      await copyText(text, "复制共享视图 JSON");
      button.textContent = "已复制";
      setTimeout(() => button.textContent = "复制 JSON", 1200);
    }});
  }});
  document.querySelectorAll(".copy-view-patch").forEach(button => {{
    button.addEventListener("click", async () => {{
      await copyText(patchCsvFor(button.closest("tr")), "复制 view patch CSV");
      button.textContent = "已复制";
      setTimeout(() => button.textContent = "复制 patch", 1200);
    }});
  }});
  document.querySelectorAll(".download-view-patch").forEach(button => {{
    button.addEventListener("click", () => {{
      const row = button.closest("tr");
      const field = patchField.value || "status";
      const viewId = row.dataset.viewId || "view";
      downloadText(`${{viewId}}-${{field}}-patch.csv`, patchCsvFor(row));
    }});
  }});
  document.querySelectorAll(".copy-view-patch-command").forEach(button => {{
    button.addEventListener("click", async () => {{
      await copyText(patchCommandFor(button.closest("tr")), "复制 view patch 命令");
      button.textContent = "已复制";
      setTimeout(() => button.textContent = "复制命令", 1200);
    }});
  }});
  document.querySelectorAll(".copy-view-command").forEach(button => {{
    button.addEventListener("click", async () => {{
      await copyText(button.dataset.command || "", "复制命令");
      button.textContent = "已复制";
      setTimeout(() => button.textContent = button.dataset.command || "复制", 1200);
    }});
  }});
}})();
</script>
"""
    (report_dir / "views.html").write_text(page_shell("视图目录", body, data, views_css), encoding="utf-8")


def build_collections_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review_plan = build_review_plan(papers)
    today = dt.date.today().isoformat()
    paper_by_slug = {paper["slug"]: paper for paper in papers}

    def items_from_slugs(slugs: list[str]) -> list[dict[str, Any]]:
        return [paper_by_slug[slug] for slug in slugs if slug in paper_by_slug]

    shared_views = []
    for view in SHARED_VIEWS:
        state = view.get("state") or {}
        matched = [paper for paper in papers if matches_view_state(paper, state, today)]
        shared_views.append(
            {
                "name": str(view.get("name") or ""),
                "page": str(view.get("page") or "all"),
                "href": view_href(view),
                "state": state,
                "count": len(matched),
                "slugs": [paper["slug"] for paper in matched],
                "sample_papers": [collection_paper_summary(paper) for paper in matched[:8]],
            }
        )

    due_review = [
        paper
        for paper in papers
        if paper.get("next_review") and str(paper.get("next_review")) <= today
    ]
    high_importance = sorted(
        [paper for paper in papers if int(paper.get("importance") or 0) >= 5],
        key=lambda paper: (-(paper.get("importance") or 0), -(paper.get("year") or 0), paper["title"]),
    )
    missing_taxonomy = items_from_slugs(quality["queues"].get("missing_required_metadata", []))
    taxonomy_drift = items_from_slugs(quality["queues"].get("taxonomy_drift", []))
    taxonomy_sparse = items_from_slugs(quality["queues"].get("taxonomy_sparse", []))
    taxonomy_dense = items_from_slugs(quality["queues"].get("taxonomy_dense", []))
    no_review_plan = items_from_slugs(review_plan["queues"].get("needs_plan", []))
    no_code_observation = items_from_slugs(quality["queues"].get("no_code_observation", []))

    smart_specs = [
        ("high_importance", "重点论文", page_query_href("library.html", importance="5", sort="importance"), "importance >= 5 的核心阅读对象。", high_importance),
        ("due_review", "待复习", page_query_href("review.html"), f"next_review <= {today} 的复习队列。", due_review),
        ("needs_review_plan", "需建复习计划", page_query_href("review.html"), "缺少 next_review 的论文。", no_review_plan),
        ("missing_taxonomy", "待补分类", page_query_href("quality.html"), "缺少必要 taxonomy 或研究线角色的论文。", missing_taxonomy),
        ("taxonomy_sparse", "分类偏薄", page_query_href("quality.html"), "结构分类或 topic/method 太少，检索入口不足。", taxonomy_sparse),
        ("taxonomy_dense", "分类过密", page_query_href("quality.html"), "topic/method 过多，可能需要收敛为核心标签。", taxonomy_dense),
        ("taxonomy_drift", "Taxonomy Drift", page_query_href("quality.html"), "状态、阶段或角色不在 taxonomy.json 允许值中的论文。", taxonomy_drift),
        ("no_code_observation", "缺代码观察", page_query_href("gaps.html"), "尚未记录代码仓库或代码实现观察的论文。", no_code_observation),
    ]
    smart_collections = [
        {
            "id": key,
            "title": title,
            "href": href,
            "note": note,
            "count": len(items),
            "slugs": [paper["slug"] for paper in items],
            "sample_papers": [collection_paper_summary(paper) for paper in items[:8]],
        }
        for key, title, href, note, items in smart_specs
    ]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)
    research_lines = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
        items = grouped[line]
        href = f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line)
        five_star = sum(1 for paper in items if int(paper.get("importance") or 0) >= 5)
        needs_plan = sum(1 for paper in items if not paper.get("next_review"))
        roles = Counter(str(paper.get("line_role") or "unclassified") for paper in items)
        topics = Counter(topic for paper in items for topic in paper.get("topics", []))
        methods = Counter(method for paper in items for method in paper.get("methods", []))
        research_lines.append(
            {
                "name": line,
                "href": href,
                "library_href": page_query_href("library.html", line=line, sort="importance"),
                "count": len(items),
                "high_importance": five_star,
                "needs_review_plan": needs_plan,
                "roles": dict(sorted(roles.items(), key=lambda item: (-item[1], item[0]))),
                "top_topics": [{"value": value, "count": count} for value, count in topics.most_common(8)],
                "top_methods": [{"value": value, "count": count} for value, count in methods.most_common(8)],
                "slugs": [paper["slug"] for paper in sorted(items, key=lambda paper: paper["slug"])],
                "sample_papers": [
                    collection_paper_summary(paper)
                    for paper in sorted(items, key=lambda paper: (-(int(paper.get("importance") or 0)), -(int(paper.get("year") or 0)), paper["title"]))[:8]
                ],
            }
        )

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "shared_view_count": len(shared_views),
        "smart_collection_count": len(smart_collections),
        "research_line_count": len(research_lines),
        "shared_views": shared_views,
        "smart_collections": smart_collections,
        "research_lines": research_lines,
        "links": {
            "html": "collections.html",
            "library": "library.html",
            "dashboard": "dashboard.html",
            "quality": "quality.html",
            "review": "review.html",
        },
    }


def write_collections_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_collections_payload(papers)
    (report_dir / "collections.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_collections(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_collections_payload(papers)

    def sample_list(items: list[dict[str, Any]]) -> str:
        if not items:
            return '<div class="empty">暂无论文。</div>'
        rows = "".join(
            f'<li><a href="{html.escape(str(paper.get("href") or ""))}">{html.escape(str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or ""))}</a>'
            f' <span class="meta">{html.escape(str(paper.get("research_line") or "Unassigned"))}</span></li>'
            for paper in items[:5]
        )
        more = f'<div class="meta">另有 {len(items) - 5} 篇未显示。</div>' if len(items) > 5 else ""
        return f'<ol class="queue-list">{rows}</ol>{more}'

    def smart_card(item: dict[str, Any]) -> str:
        return f"""<section class="collection-card">
  <header><h2><a href="{html.escape(str(item["href"]))}">{html.escape(str(item["title"]))}</a></h2><strong>{int(item["count"])}</strong></header>
  <p class="meta">{html.escape(str(item["note"]))}</p>
  {sample_list(item.get("sample_papers", []))}
</section>"""

    shared_rows = [
        "<tr>"
        f'<td><a href="{html.escape(str(view["href"]))}">{html.escape(str(view["name"]))}</a></td>'
        f"<td>{html.escape(str(view.get('page') or 'all'))}</td>"
        f"<td>{int(view['count'])}</td>"
        f"<td><code>{html.escape(json.dumps(view.get('state') or {}, ensure_ascii=False, sort_keys=True))}</code></td>"
        "</tr>"
        for view in payload["shared_views"]
    ]
    shared_table = (
        '<table class="data-table"><thead><tr><th>视图</th><th>页面</th><th>命中</th><th>筛选状态</th></tr></thead>'
        f"<tbody>{''.join(shared_rows)}</tbody></table>"
        if shared_rows
        else '<div class="empty">还没有共享视图。可以在 guides/taxonomy.json 的 shared_views 中添加。</div>'
    )

    smart_cards = [smart_card(item) for item in payload["smart_collections"]]

    line_rows = []
    for line in payload["research_lines"]:
        line_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(str(line["href"]))}">{html.escape(str(line["name"]))}</a></td>'
            f"<td>{int(line['count'])}</td>"
            f"<td>{int(line['high_importance'])}</td>"
            f"<td>{int(line['needs_review_plan'])}</td>"
            f'<td><a href="{html.escape(str(line["library_href"]))}">打开集合</a></td>'
            "</tr>"
        )
    line_table = (
        '<table class="data-table"><thead><tr><th>研究线集合</th><th>论文</th><th>重点</th><th>缺复习计划</th><th>入口</th></tr></thead>'
        f"<tbody>{''.join(line_rows)}</tbody></table>"
        if line_rows
        else '<div class="empty">还没有研究线集合。</div>'
    )

    collections_css = """
    .collection-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }
    .collection-card {
      display: grid;
      gap: 10px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .collection-card header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 0;
    }
    .collection-card h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.3;
    }
    .collection-card strong {
      min-width: 42px;
      text-align: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #edf3f1;
      color: var(--accent);
      padding: 4px 8px;
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Collections</div>
  <h1>集合视图</h1>
  <p class="lead">把共享筛选视图、研究线入口和系统自动队列集中到一个目录里。适合论文库变大后作为团队协作、周复盘和选题规划的入口。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="collections.json">Collections JSON</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <span class="stat">共享视图 {payload["shared_view_count"]}</span>
    <span class="stat">智能集合 {payload["smart_collection_count"]}</span>
    <span class="stat">研究线 {payload["research_line_count"]}</span>
    <span class="stat">论文 {payload["count"]}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">共享视图</h2>
    <div class="table-wrap">{shared_table}</div>
  </section>
  <section>
    <h2 class="section-title">智能集合</h2>
    <div class="collection-grid">{"".join(smart_cards)}</div>
  </section>
  <section>
    <h2 class="section-title">研究线集合</h2>
    <div class="table-wrap">{line_table}</div>
  </section>
</main>
"""
    (report_dir / "collections.html").write_text(page_shell("集合视图", body, extra_css=collections_css), encoding="utf-8")


FACET_SPECS = (
    ("domains", "Domain", "domain", "结构域", True),
    ("tracks", "Track", "track", "方向", True),
    ("problems", "Problem", "problem", "问题", True),
    ("topics", "Topic", "topic", "主题", True),
    ("methods", "Method", "method", "方法", True),
    ("research_line", "Research line", "line", "研究线", False),
    ("line_role", "Line role", "role", "研究线角色", False),
    ("status", "Status", "status", "阅读状态", False),
    ("reading_stage", "Reading stage", "stage", "阅读阶段", False),
    ("review_stage", "Review stage", "reviewStage", "复习阶段", False),
)


def registry_configured_values(field: str) -> set[str]:
    values = set(LABEL_DEFINITIONS.get(field, {}))
    if field == "research_line":
        values.update(RESEARCH_LINE_OWNERS)
        return values
    if field == "line_role":
        values.update(ROLE_ORDER)
        return values
    if field == "status":
        values.update(STATUS_VALUES)
        return values
    if field == "reading_stage":
        values.update(READING_STAGE_VALUES)
        return values
    if field == "review_stage":
        values.update(REVIEW_STAGE_VALUES)
        return values
    return values


def registry_label_id(label: str) -> str:
    slug = slugify_label(label)
    if slug != "untitled":
        return slug
    return "label-" + hashlib.sha1(label.encode("utf-8")).hexdigest()[:10]


def registry_field_papers(papers: list[dict[str, Any]], field: str, is_list: bool) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        for value in facet_values_for_paper(paper, field, is_list):
            grouped[value].append(paper)
    return grouped


def registry_paper_payload(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or "",
        "title_zh": paper.get("title_zh") or paper.get("title") or "",
        "href": paper.get("html_path") or paper.get("md_path") or f"{paper['slug']}.html",
        "year": paper.get("year") or "",
        "research_line": paper.get("research_line") or "Unassigned",
        "importance": paper.get("importance") or "",
    }


def registry_recommendation(signals: list[str]) -> str:
    if "deprecated_in_use" in signals:
        return "该标签已标记 deprecated 但仍在报告中使用；请导出 patch 迁移到替代标签。"
    if "unconfigured_value" in signals:
        return "确认这是新流程值还是拼写漂移：前者写入 taxonomy.json，后者批量修正报告 frontmatter。"
    if "unowned_research_line" in signals:
        return "给这条 research_line 在 taxonomy.json 的 research_line_owners 中补 owner/team/cadence。"
    if "overloaded" in signals:
        return "检查该标签是否过宽，必要时拆成更具体的 topic/method/problem。"
    if "cross_field" in signals:
        return "确认同名标签跨字段语义是否一致；若语义不同，改名让字段职责更清楚。"
    if "singleton" in signals:
        return "单例标签适合观察或合并，除非它代表明确的新研究方向。"
    if "unused_configured" in signals:
        return "配置中存在但当前未使用；可保留为预设，也可移除以降低选择噪音。"
    if "undefined_label" in signals:
        return "给该标签补 label_definitions 说明，或确认它应合并到已有规范标签。"
    if "has_aliases" in signals:
        return "保留 alias 映射，新增报告继续使用 canonical label。"
    return "当前标签状态稳定。"


def build_registry_report(papers: list[dict[str, Any]]) -> dict[str, Any]:
    taxonomy = taxonomy_counts(papers)
    policy = GOVERNANCE_POLICY["taxonomy_actions"]
    total = len(papers)
    records: dict[str, dict[str, Any]] = {}
    slugs_by_label: dict[str, set[str]] = defaultdict(set)
    papers_by_slug = {paper["slug"]: paper for paper in papers}

    aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
    for alias, canonical in LABEL_ALIASES.items():
        canonical_label = str(canonical or "").strip()
        alias_label = str(alias or "").strip()
        if canonical_label and alias_label and alias_label.lower() != canonical_label.lower():
            aliases_by_canonical[canonical_label].append(alias_label)
    for suggestion in label_alias_suggestions(papers):
        canonical_label = str(suggestion.get("canonical") or "").strip()
        aliases = suggestion.get("aliases") or {}
        if not canonical_label or not isinstance(aliases, dict):
            continue
        for alias in aliases:
            alias_label = str(alias or "").strip()
            if alias_label and alias_label.lower() != canonical_label.lower():
                aliases_by_canonical[canonical_label].append(alias_label)

    def ensure_record(label: str) -> dict[str, Any]:
        normalized = normalize_label(label)
        key = normalized_duplicate_key(normalized) or normalized.lower()
        if key not in records:
            records[key] = {
                "id": registry_label_id(normalized),
                "label": normalized,
                "key": key,
                "fields": {},
                "field_names": [],
                "total_count": 0,
                "paper_count": 0,
                "slugs": [],
                "papers": [],
                "aliases": sorted(set(aliases_by_canonical.get(normalized, [])), key=str.lower),
                "alias_count": len(set(aliases_by_canonical.get(normalized, []))),
                "configured": False,
                "configured_fields": [],
                "definitions": [],
                "definition_count": 0,
                "definition_status": "",
                "description": "",
                "owner": research_line_owner(normalized),
                "owner_name": (research_line_owner(normalized).get("owner") or ""),
                "signals": [],
                "severity": "ok",
                "recommended_action": "当前标签状态稳定。",
                "query_href": "library.html",
            }
        return records[key]

    for canonical in aliases_by_canonical:
        ensure_record(canonical)

    for field, english, query_key, label, is_list in FACET_SPECS:
        counts = dict(facet_count_for_field(papers, taxonomy, field, is_list))
        configured = registry_configured_values(field)
        for value in configured:
            counts.setdefault(value, 0)
        grouped_papers = registry_field_papers(papers, field, is_list)
        for value, count in counts.items():
            if not str(value).strip():
                continue
            record = ensure_record(str(value))
            value_papers = grouped_papers.get(str(value), [])
            field_configured = str(value) in configured
            definition = label_definition(field, str(value))
            if field_configured:
                record["configured"] = True
                record["configured_fields"].append(field)
            field_payload = {
                "field": field,
                "label": label,
                "english": english,
                "query_key": query_key,
                "count": int(count),
                "configured": field_configured,
                "href": f"library.html?{urlencode({query_key: str(value)})}",
            }
            if definition:
                field_payload["definition"] = definition
                record["definitions"].append({"field": field, **definition})
                if definition.get("owner") and not record["owner"]:
                    record["owner"] = {"owner": definition["owner"]}
                if definition.get("owner") and not record.get("owner_name"):
                    record["owner_name"] = definition["owner"]
            record["fields"][field] = field_payload
            for paper in value_papers:
                slugs_by_label[record["key"]].add(paper["slug"])

    for record in records.values():
        field_items = list(record["fields"].values())
        field_names = sorted(record["fields"])
        slugs = sorted(slugs_by_label.get(record["key"], set()))
        papers_payload = [registry_paper_payload(papers_by_slug[slug]) for slug in slugs[:8] if slug in papers_by_slug]
        total_count = sum(int(item["count"]) for item in field_items)
        configured_fields = sorted(set(record["configured_fields"]))
        definitions = record.get("definitions", [])
        definition_statuses = sorted({str(item.get("status") or "") for item in definitions if item.get("status")})
        descriptions = [str(item.get("description") or "") for item in definitions if item.get("description")]
        signals: list[str] = []
        if record["aliases"]:
            signals.append("has_aliases")
        if not field_items and record["aliases"]:
            signals.append("alias_only")
        if len(field_names) > 1:
            signals.append("cross_field")
        if configured_fields and total_count == 0:
            signals.append("unused_configured")
        if definitions and any(str(item.get("status") or "") == "deprecated" for item in definitions) and total_count > 0:
            signals.append("deprecated_in_use")
        if not definitions and total_count > 0 and any(field in {"domains", "tracks", "problems", "topics", "methods", "research_line"} for field in field_names):
            signals.append("undefined_label")
        if slugs and len(slugs) == 1 and not configured_fields:
            signals.append("singleton")
        overload_fields = {"domains", "tracks", "problems", "topics", "methods", "research_line"}
        for item in field_items:
            if item["field"] in overload_fields and total and int(item["count"]) >= int(policy["split_min_count"]) and int(item["count"]) / total >= float(policy["split_share"]):
                signals.append("overloaded")
            if item["field"] in {"status", "reading_stage", "review_stage", "line_role"} and int(item["count"]) > 0 and not item["configured"]:
                signals.append("unconfigured_value")
        if "research_line" in record["fields"] and int(record["fields"]["research_line"]["count"]) > 0 and not record["owner"]:
            signals.append("unowned_research_line")

        signals = sorted(set(signals))
        severity = "ok"
        if any(signal in signals for signal in ("deprecated_in_use", "overloaded", "unconfigured_value", "unowned_research_line")):
            severity = "high"
        elif any(signal in signals for signal in ("undefined_label", "cross_field", "singleton", "unused_configured", "alias_only")):
            severity = "medium"
        elif signals:
            severity = "low"

        primary = max(field_items, key=lambda item: (int(item["count"]), item["field"]), default=None)
        record.update(
            {
                "fields": sorted(field_items, key=lambda item: (item["field"], item["label"])),
                "field_names": field_names,
                "total_count": total_count,
                "paper_count": len(slugs),
                "slugs": slugs,
                "papers": papers_payload,
                "configured": bool(configured_fields),
                "configured_fields": configured_fields,
                "definitions": definitions,
                "definition_count": len(definitions),
                "definition_status": "mixed" if len(definition_statuses) > 1 else (definition_statuses[0] if definition_statuses else ""),
                "description": " / ".join(descriptions[:2]),
                "owner": record.get("owner") or {},
                "owner_name": record.get("owner_name") or "",
                "signals": signals,
                "severity": severity,
                "recommended_action": registry_recommendation(signals),
                "query_href": primary["href"] if primary else "taxonomy.html",
            }
        )

    labels = sorted(
        records.values(),
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2, "ok": 3}.get(str(item["severity"]), 4),
            -int(item["total_count"]),
            str(item["label"]).lower(),
        ),
    )
    severity_counts = Counter(str(item["severity"]) for item in labels)
    signal_counts = Counter(signal for item in labels for signal in item["signals"])
    field_counts = Counter(field for item in labels for field in item["field_names"])
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "label_count": len(labels),
        "configured_label_count": sum(1 for item in labels if item["configured"]),
        "alias_count": sum(len(item["aliases"]) for item in labels),
        "labels": labels,
        "summary": {
            "high": severity_counts.get("high", 0),
            "medium": severity_counts.get("medium", 0),
            "low": severity_counts.get("low", 0),
            "ok": severity_counts.get("ok", 0),
            "cross_field": signal_counts.get("cross_field", 0),
            "singleton": signal_counts.get("singleton", 0),
            "unused_configured": signal_counts.get("unused_configured", 0),
            "unowned_research_line": signal_counts.get("unowned_research_line", 0),
            "defined": sum(1 for item in labels if item.get("definition_count")),
            "deprecated_in_use": signal_counts.get("deprecated_in_use", 0),
            "undefined_label": signal_counts.get("undefined_label", 0),
        },
        "field_counts": dict(sorted(field_counts.items())),
        "signals": dict(sorted(signal_counts.items())),
        "csv_columns": ["label", "severity", "fields", "definition_status", "owner_name", "description", "total_count", "paper_count", "aliases", "signals", "recommended_action"],
        "commands": [
            "python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md",
            "python3 scripts/export_taxonomy_registry.py docs --format project --severity high --severity medium --output docs/exports/taxonomy-registry-project.csv",
            "python3 scripts/export_taxonomy_registry.py docs --format patch --signal singleton --target-value <target_value> --output docs/exports/taxonomy-registry-patch.csv",
            "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv",
            "python3 scripts/apply_library_metadata.py docs --input <taxonomy_registry_patch.csv>",
            "python3 scripts/apply_taxonomy_aliases.py docs --write",
        ],
        "links": {
            "taxonomy": "taxonomy.html",
            "facets": "facets.html",
            "quality": "quality.html",
            "library": "library.html",
        },
    }


def write_registry_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_registry_report(papers)
    (report_dir / "registry.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_registry_label_row(item: dict[str, Any]) -> str:
    field_names = ", ".join(str(field) for field in item.get("field_names", []))
    aliases = ", ".join(str(alias) for alias in item.get("aliases", []))
    signals = "".join(f'<span class="flag">{html.escape(str(signal))}</span>' for signal in item.get("signals", []))
    paper_links = []
    for paper in item.get("papers", []):
        title = paper.get("title_zh") or paper.get("title") or paper.get("slug")
        href = str(paper.get("href") or f"{paper.get('slug')}.html")
        paper_links.append(f'<a href="{html.escape(href)}">{html.escape(str(title))}</a>')
    owner = item.get("owner") or {}
    owner_text = " / ".join(str(owner.get(key) or "") for key in ("owner", "team", "cadence") if owner.get(key))
    description = str(item.get("description") or "")
    definition_status = str(item.get("definition_status") or "")
    search = " ".join(
        [
            str(item.get("label") or ""),
            field_names,
            aliases,
            description,
            definition_status,
            " ".join(str(signal) for signal in item.get("signals", [])),
            " ".join(str(slug) for slug in item.get("slugs", [])),
            owner_text,
        ]
    ).lower()
    checklist = f"- [ ] {item.get('label')} ({item.get('severity')}): {item.get('recommended_action')}"
    return (
        f'<tr data-severity="{html.escape(str(item.get("severity") or ""), quote=True)}"'
        f' data-fields="{html.escape(" ".join(str(field) for field in item.get("field_names", [])), quote=True)}"'
        f' data-configured="{"yes" if item.get("configured") else "no"}"'
        f' data-search="{html.escape(search, quote=True)}">'
        f'<td><a href="{html.escape(str(item.get("query_href") or "library.html"))}">{html.escape(str(item.get("label") or ""))}</a>'
        f'<div class="meta">{html.escape(owner_text or "no owner")}</div></td>'
        f"<td>{html.escape(field_names or 'alias')}</td>"
        f"<td><span class=\"flag\">{html.escape(str(item.get('severity') or 'ok'))}</span><div class=\"meta\">{html.escape(str(item.get('total_count') or 0))} uses / {html.escape(str(item.get('paper_count') or 0))} papers</div></td>"
        f"<td>{html.escape(definition_status or '-')}"
        f"<div class=\"meta\">{html.escape(description or 'No definition')}</div></td>"
        f"<td>{html.escape(aliases or '-')}</td>"
        f"<td>{signals or '<span class=\"meta\">stable</span>'}</td>"
        f"<td>{', '.join(paper_links) if paper_links else '<span class=\"meta\">No papers</span>'}</td>"
        f"<td>{html.escape(str(item.get('recommended_action') or ''))}</td>"
        f'<td><button class="button copy-registry-row" type="button" data-checklist="{html.escape(checklist, quote=True)}">复制</button></td>'
        "</tr>"
    )


def render_registry(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_registry_report(papers)
    rows = "".join(render_registry_label_row(item) for item in payload["labels"])
    table = (
        '<table class="data-table"><thead><tr><th>标签</th><th>字段</th><th>状态</th><th>定义</th><th>Alias</th><th>信号</th><th>代表论文</th><th>建议</th><th>复制</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        if rows
        else '<div class="empty">暂无分类标签。</div>'
    )
    field_options = "".join(
        f'<option value="{html.escape(field, quote=True)}">{html.escape(field)} ({count})</option>'
        for field, count in payload["field_counts"].items()
    )
    metrics = [
        ("标签总数", str(payload["label_count"]), "registry labels"),
        ("高风险", str(payload["summary"]["high"]), "need action"),
        ("跨字段", str(payload["summary"]["cross_field"]), "semantic check"),
        ("单例", str(payload["summary"]["singleton"]), "merge/watch"),
        ("已定义", str(payload["summary"]["defined"]), "definitions"),
        ("Alias", str(payload["alias_count"]), "canonicalization"),
    ]
    metric_html = "".join(
        f'<section class="metric-card"><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><span>{html.escape(note)}</span></section>'
        for label, value, note in metrics
    )
    command_buttons = "".join(
        f'<button class="button copy-registry-command" type="button" data-command="{html.escape(command, quote=True)}">{html.escape(command)}</button>'
        for command in payload["commands"]
    )
    body = f"""
<header class="shell">
  <div class="eyebrow">Taxonomy Registry</div>
  <h1>标签注册表</h1>
  <p class="lead">把 domain、track、problem、topic、method、研究线和状态值整理成可治理的标签字典，帮助多人维护时统一命名、发现跨字段复用和单例长尾。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="registry.json">Registry JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">标签 {payload["label_count"]}</span>
    <span class="stat">生成时间 {html.escape(payload["generated_at"])}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">注册表摘要</h2>
    <div class="metric-grid">{metric_html}</div>
  </section>
  <section>
    <h2 class="section-title">筛选</h2>
    <div class="filter-grid">
      <input id="registrySearch" type="search" placeholder="搜索标签、alias、slug、owner、治理信号">
      <select id="registryField"><option value="">全部字段</option>{field_options}</select>
      <select id="registrySeverity">
        <option value="">全部风险</option>
        <option value="high">high</option>
        <option value="medium">medium</option>
        <option value="low">low</option>
        <option value="ok">ok</option>
      </select>
      <select id="registryConfigured">
        <option value="">全部来源</option>
        <option value="yes">配置中出现</option>
        <option value="no">仅报告/alias</option>
      </select>
    </div>
    <div class="results-bar">
      <strong><span id="registryVisibleCount">{len(payload["labels"])}</span> 个标签可见</strong>
      <div class="results-actions">
        <button id="downloadRegistryCsv" class="button" type="button">下载 CSV</button>
        <button id="copyRegistryMarkdown" class="button" type="button">复制清单</button>
        <button id="copyRegistryCommands" class="button" type="button">复制命令</button>
      </div>
    </div>
  </section>
  <section>
    <h2 class="section-title">标签字典</h2>
    <div class="table-wrap">{table}</div>
  </section>
  <section>
    <h2 class="section-title">治理命令</h2>
    <div class="command-panel"><div class="bulk-actions">{command_buttons}</div></div>
  </section>
</main>
<script>
const registryPayload = window.PAPER_WIKI || {{}};
const registryLabels = registryPayload.labels || [];
const registryRows = Array.from(document.querySelectorAll("[data-severity]"));
const registrySearch = document.querySelector("#registrySearch");
const registryField = document.querySelector("#registryField");
const registrySeverity = document.querySelector("#registrySeverity");
const registryConfigured = document.querySelector("#registryConfigured");
const registryVisibleCount = document.querySelector("#registryVisibleCount");

function registryCsvCell(value) {{
  const text = Array.isArray(value) ? value.join("; ") : String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? '"' + text.replaceAll('"', '""') + '"'
    : text;
}}

function visibleRegistryLabels() {{
  const visible = new Set(registryRows.filter(row => !row.hidden).map(row => row.querySelector("a")?.textContent || ""));
  return registryLabels.filter(label => visible.has(label.label));
}}

function renderRegistry() {{
  const query = (registrySearch.value || "").trim().toLowerCase();
  const field = registryField.value;
  const severity = registrySeverity.value;
  const configured = registryConfigured.value;
  let count = 0;
  registryRows.forEach(row => {{
    const fields = (row.dataset.fields || "").split(/\\s+/).filter(Boolean);
    const match = (!query || (row.dataset.search || "").includes(query))
      && (!field || fields.includes(field))
      && (!severity || row.dataset.severity === severity)
      && (!configured || row.dataset.configured === configured);
    row.hidden = !match;
    if (match) count += 1;
  }});
  registryVisibleCount.textContent = String(count);
}}

function downloadRegistryCsv() {{
  const columns = registryPayload.csv_columns || [];
  const lines = [columns.join(",")];
  visibleRegistryLabels().forEach(label => {{
    const row = {{
      label: label.label,
      severity: label.severity,
      fields: label.field_names,
      definition_status: label.definition_status,
      owner_name: label.owner_name,
      description: label.description,
      total_count: label.total_count,
      paper_count: label.paper_count,
      aliases: label.aliases,
      signals: label.signals,
      recommended_action: label.recommended_action,
    }};
    lines.push(columns.map(column => registryCsvCell(row[column])).join(","));
  }});
  const blob = new Blob([lines.join("\\n")], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "taxonomy_registry.csv";
  link.click();
  URL.revokeObjectURL(url);
}}

function registryMarkdown(labels) {{
  if (!labels.length) return "- [x] 当前筛选没有标签";
  return labels.map(label => `- [ ] ${{label.label}} (${{label.severity}}): ${{label.recommended_action}}`).join("\\n");
}}

async function copyRegistryText(text, label, button) {{
  try {{
    await navigator.clipboard.writeText(text);
    const original = button.textContent;
    button.textContent = label;
    setTimeout(() => button.textContent = original, 1200);
  }} catch {{
    window.prompt("复制内容", text);
  }}
}}

[registrySearch, registryField, registrySeverity, registryConfigured].forEach(control => {{
  control.addEventListener("input", renderRegistry);
  control.addEventListener("change", renderRegistry);
}});
document.querySelector("#downloadRegistryCsv").addEventListener("click", downloadRegistryCsv);
document.querySelector("#copyRegistryMarkdown").addEventListener("click", event => copyRegistryText(registryMarkdown(visibleRegistryLabels()), "已复制", event.currentTarget));
document.querySelector("#copyRegistryCommands").addEventListener("click", event => copyRegistryText((registryPayload.commands || []).join("\\n"), "已复制", event.currentTarget));
document.querySelectorAll(".copy-registry-row").forEach(button => {{
  button.addEventListener("click", () => copyRegistryText(button.dataset.checklist || "", "已复制", button));
}});
document.querySelectorAll(".copy-registry-command").forEach(button => {{
  button.addEventListener("click", () => copyRegistryText(button.dataset.command || "", "已复制", button));
}});
renderRegistry();
</script>
"""
    (report_dir / "registry.html").write_text(page_shell("标签注册表", body, data=payload), encoding="utf-8")


def facet_values_for_paper(paper: dict[str, Any], field: str, is_list: bool) -> list[str]:
    if is_list:
        return [str(value).strip() for value in paper.get(field, []) if str(value).strip()]
    value = str(paper.get(field) or "").strip()
    return [value] if value and value != "Unassigned" else []


def facet_count_for_field(papers: list[dict[str, Any]], taxonomy: dict[str, dict[str, int]], field: str, is_list: bool) -> dict[str, int]:
    if field == "research_line":
        return taxonomy["research_lines"]
    if field == "line_role":
        return taxonomy["line_roles"]
    if field == "status":
        return taxonomy["statuses"]
    if field == "reading_stage":
        return taxonomy["reading_stages"]
    if field == "review_stage":
        return taxonomy["review_stages"]
    if is_list:
        return taxonomy[field]
    return scalar_counts(papers, field)


def taxonomy_balance_report(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    taxonomy = taxonomy_counts(papers)
    policy = GOVERNANCE_POLICY["taxonomy_actions"]
    total = len(papers)
    rows: list[dict[str, Any]] = []
    for field, english, query_key, label, is_list in FACET_SPECS:
        counts = facet_count_for_field(papers, taxonomy, field, is_list)
        used_items = [(value, count) for value, count in counts.items() if count > 0]
        unused_count = sum(1 for count in counts.values() if count == 0)
        singleton_count = sum(1 for _value, count in used_items if count == 1)
        overloaded_count = sum(
            1
            for _value, count in used_items
            if total and count / total >= float(policy["split_share"]) and count >= int(policy["split_min_count"])
        )
        max_value, max_count = max(used_items, key=lambda item: (item[1], item[0].lower()), default=("", 0))
        observed_total = sum(count for _value, count in used_items)
        probabilities = [count / observed_total for _value, count in used_items if observed_total]
        entropy = -sum(probability * math.log(probability) for probability in probabilities if probability > 0)
        effective_count = round(math.exp(entropy), 2) if probabilities else 0
        singleton_rate = (singleton_count / len(used_items)) if used_items else 0
        max_share = (max_count / total) if total else 0
        balance_score = round(100 * (1 - max_share) * (1 - singleton_rate * 0.5)) if used_items else 0
        rows.append(
            {
                "field": field,
                "label": label,
                "english": english,
                "query_key": query_key,
                "configured_count": len(counts),
                "used_count": len(used_items),
                "unused_count": unused_count,
                "singleton_count": singleton_count,
                "overloaded_count": overloaded_count,
                "max_value": max_value,
                "max_count": max_count,
                "max_share": round(max_share, 4),
                "effective_count": effective_count,
                "balance_score": balance_score,
            }
        )
    return rows


def render_balance(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    rows = taxonomy_balance_report(papers)
    actions = build_taxonomy_actions(papers)
    policy = GOVERNANCE_POLICY["taxonomy_balance"]
    avg_score = round(sum(int(row["balance_score"]) for row in rows) / len(rows), 1) if rows else 100
    weakest = min(rows, key=lambda row: int(row["balance_score"]), default=None)
    total_singletons = sum(int(row["singleton_count"]) for row in rows)
    total_overloaded = sum(int(row["overloaded_count"]) for row in rows)
    total_unused = sum(int(row["unused_count"]) for row in rows)

    def risk_level(row: dict[str, Any]) -> str:
        score = int(row["balance_score"])
        if score < int(policy["high_score_below"]) or int(row["overloaded_count"]) > 0:
            return "high"
        if score < int(policy["medium_score_below"]) or int(row["singleton_count"]) >= int(policy["singleton_medium_count"]) or int(row["unused_count"]) >= int(policy["unused_medium_count"]):
            return "medium"
        return "low"

    def action_hint(row: dict[str, Any]) -> str:
        hints = []
        if int(row["overloaded_count"]) > 0:
            hints.append("拆分过载标签")
        if int(row["singleton_count"]) > 0:
            hints.append("合并长尾标签")
        if int(row["unused_count"]) > 0:
            hints.append("清理空候选")
        return "；".join(hints) or "保持观察"

    def row_html(row: dict[str, Any]) -> str:
        risk = risk_level(row)
        max_href = page_query_href("library.html", **{str(row["query_key"]): str(row["max_value"])}) if row.get("max_value") else "library.html"
        field_href = page_query_href("facets.html")
        score = int(row["balance_score"])
        return (
            f'<tr data-label="{html.escape(str(row["label"]), quote=True)}" '
            f'data-english="{html.escape(str(row["english"]), quote=True)}" '
            f'data-risk="{risk}" data-score="{score}" '
            f'data-singletons="{row["singleton_count"]}" data-overloaded="{row["overloaded_count"]}" '
            f'data-unused="{row["unused_count"]}" data-search="{html.escape(" ".join([str(row["label"]), str(row["english"]), str(row["max_value"]), risk, action_hint(row)]).lower(), quote=True)}">'
            f'<td><a href="{html.escape(field_href)}">{html.escape(str(row["label"]))}</a><div class="meta">{html.escape(str(row["english"]))}</div></td>'
            f'<td><strong>{score}</strong><div class="balance-meter"><span style="width:{score}%"></span></div></td>'
            f'<td><span class="flag">{risk}</span></td>'
            f'<td>{row["used_count"]} / {row["configured_count"]}<div class="meta">effective {row["effective_count"]}</div></td>'
            f'<td>{row["singleton_count"]}</td>'
            f'<td>{row["overloaded_count"]}</td>'
            f'<td>{row["unused_count"]}</td>'
            f'<td><a href="{html.escape(max_href)}">{html.escape(str(row["max_value"]) or "-")}</a><div class="meta">{row["max_count"]} 篇 / {round(float(row["max_share"]) * 100)}%</div></td>'
            f"<td>{html.escape(action_hint(row))}</td>"
            "</tr>"
        )

    table_rows = "".join(row_html(row) for row in rows)
    action_summary = actions.get("summary", {})
    weakest_text = str(weakest["label"]) if weakest else "-"
    balance_css = """
    .balance-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(280px, .7fr);
      gap: 16px;
      align-items: start;
      margin-bottom: 24px;
    }
    .balance-panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .balance-panel h2 {
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.25;
    }
    .balance-panel p { margin: 0; color: var(--muted); }
    .balance-meter {
      width: 120px;
      height: 8px;
      border-radius: 999px;
      background: #eadfce;
      overflow: hidden;
      margin-top: 6px;
    }
    .balance-meter span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
    }
    .balance-controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(140px, 190px) minmax(160px, 210px) repeat(3, auto);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .balance-controls input,
    .balance-controls select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px 12px;
      color: var(--text);
      font: inherit;
    }
    @media (max-width: 900px) {
      .balance-hero { grid-template-columns: 1fr; }
      .balance-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Taxonomy Balance</div>
  <h1>分类均衡复盘</h1>
  <p class="lead">把每个分类维度的健康度、长尾、过载和空候选放到一张表里，适合论文库增长后定期判断哪些标签该合并、拆分或清理。</p>
  <div class="stats">
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="taxonomy_actions.json">治理任务 JSON</a>
    <a class="stat" href="stats.json">Stats JSON</a>
    <span class="stat">均衡分 {avg_score}</span>
    <span class="stat">最弱维度 {html.escape(weakest_text)}</span>
    <span class="stat">论文 {len(papers)}</span>
  </div>
</header>
<main class="shell">
  <section class="balance-hero">
    <div class="metric-grid">
      <section class="metric-card"><span>平均均衡分</span><strong>{avg_score}</strong><span>越高代表越少默认桶和极端长尾</span></section>
      <section class="metric-card"><span>长尾标签</span><strong>{total_singletons}</strong><span>只命中 1 篇论文</span></section>
      <section class="metric-card"><span>过载标签</span><strong>{total_overloaded}</strong><span>覆盖比例过高</span></section>
      <section class="metric-card"><span>空候选</span><strong>{total_unused}</strong><span>配置但未使用</span></section>
    </div>
    <aside class="balance-panel">
      <h2>治理任务摘要</h2>
      <p>长尾合并 {action_summary.get("merge_candidate", 0)} 项，过载拆分 {action_summary.get("split_candidate", 0)} 项，空候选 {action_summary.get("unused_config", 0)} 项，观察 {action_summary.get("watch", 0)} 项。</p>
    </aside>
  </section>
  <section>
    <h2 class="section-title">维度健康度</h2>
    <div class="balance-controls">
      <input id="balanceSearch" type="search" placeholder="搜索维度、最大标签或治理建议">
      <select id="balanceRisk"><option value="">全部风险</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select>
      <select id="balanceSort"><option value="risk">风险优先</option><option value="score">均衡分低到高</option><option value="singletons">长尾多到少</option><option value="overloaded">过载多到少</option><option value="unused">空候选多到少</option></select>
      <strong id="balanceCount">{len(rows)} 项</strong>
      <button id="downloadBalanceCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyBalanceMarkdown" class="button" type="button">复制复盘清单</button>
    </div>
    <div class="table-wrap">
      <table class="data-table"><thead><tr><th>维度</th><th>均衡分</th><th>风险</th><th>使用 / 配置</th><th>长尾</th><th>过载</th><th>空候选</th><th>最大标签</th><th>建议</th></tr></thead><tbody id="balanceRows">{table_rows}</tbody></table>
    </div>
  </section>
</main>
<script>
const balanceSearch = document.querySelector("#balanceSearch");
const balanceRisk = document.querySelector("#balanceRisk");
const balanceSort = document.querySelector("#balanceSort");
const balanceCount = document.querySelector("#balanceCount");
const balanceBody = document.querySelector("#balanceRows");
const downloadBalanceCsv = document.querySelector("#downloadBalanceCsv");
const copyBalanceMarkdown = document.querySelector("#copyBalanceMarkdown");
const balanceRows = Array.from(document.querySelectorAll("#balanceRows tr"));
const riskRank = {{ high: 0, medium: 1, low: 2 }};

function visibleBalanceRows() {{
  return balanceRows.filter(row => !row.hidden);
}}

function balanceCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function rowMetric(row, key) {{
  return Number(row.dataset[key] || 0);
}}

function sortBalanceRows(rows) {{
  const mode = balanceSort.value;
  return [...rows].sort((a, b) => {{
    if (mode === "score") return rowMetric(a, "score") - rowMetric(b, "score") || a.dataset.label.localeCompare(b.dataset.label);
    if (mode === "singletons") return rowMetric(b, "singletons") - rowMetric(a, "singletons") || a.dataset.label.localeCompare(b.dataset.label);
    if (mode === "overloaded") return rowMetric(b, "overloaded") - rowMetric(a, "overloaded") || a.dataset.label.localeCompare(b.dataset.label);
    if (mode === "unused") return rowMetric(b, "unused") - rowMetric(a, "unused") || a.dataset.label.localeCompare(b.dataset.label);
    return (riskRank[a.dataset.risk] ?? 9) - (riskRank[b.dataset.risk] ?? 9) || rowMetric(a, "score") - rowMetric(b, "score");
  }});
}}

function renderBalanceRows() {{
  const q = balanceSearch.value.trim().toLowerCase();
  const risk = balanceRisk.value;
  let visible = 0;
  balanceRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q)) && (!risk || row.dataset.risk === risk);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  sortBalanceRows(balanceRows).forEach(row => balanceBody.appendChild(row));
  balanceCount.textContent = `${{visible}} / ${{balanceRows.length}} 项`;
}}

function downloadCurrentBalanceCsv() {{
  const rows = visibleBalanceRows();
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const header = ["label", "english", "risk", "score", "singletons", "overloaded", "unused"];
  const body = rows.map(row => [row.dataset.label, row.dataset.english, row.dataset.risk, row.dataset.score, row.dataset.singletons, row.dataset.overloaded, row.dataset.unused]);
  const csv = [header, ...body].map(row => row.map(balanceCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "taxonomy_balance_filtered.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyBalanceMarkdownQueue() {{
  const rows = visibleBalanceRows();
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const lines = ["# Taxonomy Balance Review", ""];
  rows.forEach(row => {{
    lines.push(`- [ ] ${{row.dataset.risk}} / score ${{row.dataset.score}} / ${{row.dataset.label}}`);
    lines.push(`  - Long-tail: ${{row.dataset.singletons}}, overloaded: ${{row.dataset.overloaded}}, unused: ${{row.dataset.unused}}`);
  }});
  const text = lines.join("\\n") + "\\n";
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt("复制复盘清单", text);
  }}
}}

[balanceSearch, balanceRisk, balanceSort].forEach(control => control.addEventListener("input", renderBalanceRows));
downloadBalanceCsv.addEventListener("click", downloadCurrentBalanceCsv);
copyBalanceMarkdown.addEventListener("click", copyBalanceMarkdownQueue);
renderBalanceRows();
</script>
"""
    (report_dir / "balance.html").write_text(page_shell("分类均衡复盘", body, extra_css=balance_css), encoding="utf-8")


def build_coverage_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    policy = GOVERNANCE_POLICY["coverage"]
    coverage_specs = [
        ("domains", "Domain", "domain", True),
        ("tracks", "Track", "track", True),
        ("problems", "Problem", "problem", True),
        ("topics", "Topic", "topic", True),
        ("methods", "Method", "method", True),
        ("line_role", "Role", "role", False),
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)

    def values_for(paper: dict[str, Any], field: str, is_list: bool) -> list[str]:
        if is_list:
            return [str(value).strip() for value in paper.get(field, []) if str(value).strip()]
        value = str(paper.get(field) or "").strip()
        return [value] if value and value != "Unassigned" else []

    def top_values(items: list[dict[str, Any]], field: str, is_list: bool) -> list[tuple[str, int]]:
        counts: Counter[str] = Counter()
        for paper in items:
            counts.update(values_for(paper, field, is_list))
        return counts.most_common(4)

    coverage_rows: list[dict[str, Any]] = []
    for line, items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0].lower())):
        total = len(items)
        owner = research_line_owner(line)
        field_rows = []
        present_slots = 0
        missing_slots = 0
        for field, label, query_key, is_list in coverage_specs:
            missing_slugs = [str(paper.get("slug") or "") for paper in items if not values_for(paper, field, is_list)]
            missing = len(missing_slugs)
            present = total - missing
            present_slots += present
            missing_slots += missing
            values = sorted({value for paper in items for value in values_for(paper, field, is_list)}, key=str.lower)
            top = top_values(items, field, is_list)
            field_rows.append(
                {
                    "field": field,
                    "label": label,
                    "query_key": query_key,
                    "coverage": round((present / total) * 100) if total else 100,
                    "missing": missing,
                    "missing_slugs": missing_slugs,
                    "unique": len(values),
                    "top_values": [{"value": value, "count": count} for value, count in top],
                }
            )
        score = round((present_slots / (total * len(coverage_specs))) * 100) if total else 100
        missing_high = max(int(policy["missing_high_min"]), total)
        risk = (
            "high"
            if score < int(policy["high_score_below"]) or missing_slots >= missing_high
            else "medium"
            if score < int(policy["medium_score_below"]) or missing_slots
            else "low"
        )
        coverage_rows.append(
            {
                "line": line,
                "href": f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line),
                "count": total,
                "owner": owner.get("owner", ""),
                "team": owner.get("team", ""),
                "cadence": owner.get("cadence", ""),
                "score": score,
                "risk": risk,
                "missing_total": missing_slots,
                "fields": field_rows,
            }
        )

    total_missing = sum(int(row["missing_total"]) for row in coverage_rows)
    avg_score = round(sum(int(row["score"]) for row in coverage_rows) / len(coverage_rows), 1) if coverage_rows else 100
    risk_counts = dict(sorted(Counter(row["risk"] for row in coverage_rows).items()))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "line_count": len(coverage_rows),
        "field_count": len(coverage_specs),
        "avg_score": avg_score,
        "risk_counts": risk_counts,
        "weak_line_count": risk_counts.get("high", 0),
        "total_missing": total_missing,
        "fields": [
            {"field": field, "label": label, "query_key": query_key, "multi": is_list}
            for field, label, query_key, is_list in coverage_specs
        ],
        "coverage": coverage_rows,
        "links": {
            "html": "coverage.html",
            "library": "library.html",
            "balance": "balance.html",
            "facets": "facets.html",
            "quality": "quality.html",
            "lines": "lines/index.html",
        },
    }


def write_coverage_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_coverage_payload(papers)
    (report_dir / "coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_coverage(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_coverage_payload(papers)
    coverage_rows = payload["coverage"]
    coverage_specs = [
        (item["field"], item["label"], item["query_key"], item["multi"])
        for item in payload["fields"]
    ]

    def field_cell(line: str, field: dict[str, Any]) -> str:
        top = field["top_values"][:2]
        top_html = ", ".join(
            f'<a href="{html.escape(page_query_href("library.html", line=line, **{field["query_key"]: item["value"]}))}">{html.escape(item["value"])}</a> <span class="meta">{item["count"]}</span>'
            for item in top
        )
        if not top_html:
            top_html = '<span class="meta">暂无值</span>'
        return (
            f'<td data-missing="{field["missing"]}" data-coverage="{field["coverage"]}">'
            f'<strong>{field["coverage"]}%</strong>'
            f'<div class="meta">缺 {field["missing"]} / 唯一 {field["unique"]}</div>'
            f'<div class="coverage-top">{top_html}</div>'
            "</td>"
        )

    table_rows = "".join(
        "<tr "
        f'data-line="{html.escape(row["line"], quote=True)}" '
        f'data-risk="{row["risk"]}" '
        f'data-score="{row["score"]}" '
        f'data-missing="{row["missing_total"]}" '
        f'data-count="{row["count"]}" '
        f'data-search="{html.escape(" ".join([row["line"], row["risk"], str(row.get("owner") or ""), str(row.get("team") or ""), *[item["label"] for item in row["fields"]]]).lower(), quote=True)}">'
        f'<td><a href="{html.escape(row["href"])}">{html.escape(row["line"])}</a><div class="meta">{row["count"]} 篇</div></td>'
        f'<td>{html.escape(str(row.get("owner") or row.get("team") or "Unassigned"))}<div class="meta">{html.escape(str(row.get("team") or ""))}</div></td>'
        f'<td><strong>{row["score"]}</strong><div class="balance-meter"><span style="width:{row["score"]}%"></span></div></td>'
        f'<td><span class="flag">{row["risk"]}</span><div class="meta">缺口 {row["missing_total"]}</div></td>'
        + "".join(field_cell(str(row["line"]), field) for field in row["fields"])
        + "</tr>"
        for row in coverage_rows
    )
    field_headers = "".join(f"<th>{html.escape(label)}</th>" for _field, label, _query_key, _is_list in coverage_specs)
    coverage_json = json.dumps(coverage_rows, ensure_ascii=False).replace("</", "<\\/")
    weak_lines = payload["weak_line_count"]
    total_missing = payload["total_missing"]
    avg_score = payload["avg_score"]
    coverage_css = """
    .coverage-top {
      display: grid;
      gap: 3px;
      margin-top: 4px;
      font-size: 12px;
      line-height: 1.35;
    }
    .coverage-controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(140px, 190px) minmax(160px, 210px) repeat(3, auto);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .coverage-controls input,
    .coverage-controls select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px 12px;
      color: var(--text);
      font: inherit;
    }
    .coverage-table {
      min-width: 1180px;
    }
    .balance-meter {
      width: 120px;
      height: 8px;
      border-radius: 999px;
      background: #eadfce;
      overflow: hidden;
      margin-top: 6px;
    }
    .balance-meter span {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
    }
    @media (max-width: 900px) {
      .coverage-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Coverage Map</div>
  <h1>研究线分类覆盖地图</h1>
  <p class="lead">按研究线检查 domain、track、problem、topic、method 和角色是否覆盖完整，并显示每条线的维护 owner。适合在论文数量变多后，把补分类任务分派到具体研究线。</p>
  <div class="stats">
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="balance.html">分类均衡</a>
    <a class="stat" href="facets.html">分类工作台</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="coverage.json">Coverage JSON</a>
    <span class="stat">研究线 {len(coverage_rows)}</span>
    <span class="stat">平均覆盖 {avg_score}</span>
    <span class="stat">高风险 {weak_lines}</span>
    <span class="stat">缺口 {total_missing}</span>
  </div>
</header>
<main class="shell">
  <section class="metric-grid">
    <section class="metric-card"><span>平均覆盖分</span><strong>{avg_score}</strong><span>跨研究线和字段的完整度</span></section>
    <section class="metric-card"><span>高风险研究线</span><strong>{weak_lines}</strong><span>优先补 taxonomy</span></section>
    <section class="metric-card"><span>字段缺口</span><strong>{total_missing}</strong><span>paper-field 级缺失</span></section>
    <section class="metric-card"><span>研究线</span><strong>{len(coverage_rows)}</strong><span>含 Unassigned</span></section>
  </section>
  <section>
    <h2 class="section-title">覆盖明细</h2>
    <div class="coverage-controls">
      <input id="coverageSearch" type="search" placeholder="搜索研究线或字段">
      <select id="coverageRisk"><option value="">全部风险</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option></select>
      <select id="coverageSort"><option value="risk">风险优先</option><option value="score">覆盖分低到高</option><option value="missing">缺口多到少</option><option value="count">论文多到少</option><option value="line">研究线 A-Z</option></select>
      <strong id="coverageCount">{len(coverage_rows)} 条</strong>
      <button id="downloadCoverageCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyCoverageMarkdown" class="button" type="button">复制治理清单</button>
    </div>
    <div class="table-wrap">
      <table class="data-table coverage-table"><thead><tr><th>研究线</th><th>Owner</th><th>覆盖分</th><th>风险</th>{field_headers}</tr></thead><tbody id="coverageRows">{table_rows}</tbody></table>
    </div>
  </section>
</main>
<script>
const coverageData = {coverage_json};
const coverageSearch = document.querySelector("#coverageSearch");
const coverageRisk = document.querySelector("#coverageRisk");
const coverageSort = document.querySelector("#coverageSort");
const coverageCount = document.querySelector("#coverageCount");
const coverageBody = document.querySelector("#coverageRows");
const coverageRows = Array.from(document.querySelectorAll("#coverageRows tr"));
const downloadCoverageCsv = document.querySelector("#downloadCoverageCsv");
const copyCoverageMarkdown = document.querySelector("#copyCoverageMarkdown");
const coverageRiskRank = {{ high: 0, medium: 1, low: 2 }};

function visibleCoverageRows() {{
  return coverageRows.filter(row => !row.hidden);
}}

function coverageCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function coverageMetric(row, key) {{
  return Number(row.dataset[key] || 0);
}}

function sortCoverageRows(rows) {{
  const mode = coverageSort.value;
  return [...rows].sort((a, b) => {{
    if (mode === "score") return coverageMetric(a, "score") - coverageMetric(b, "score") || a.dataset.line.localeCompare(b.dataset.line);
    if (mode === "missing") return coverageMetric(b, "missing") - coverageMetric(a, "missing") || a.dataset.line.localeCompare(b.dataset.line);
    if (mode === "count") return coverageMetric(b, "count") - coverageMetric(a, "count") || a.dataset.line.localeCompare(b.dataset.line);
    if (mode === "line") return a.dataset.line.localeCompare(b.dataset.line);
    return (coverageRiskRank[a.dataset.risk] ?? 9) - (coverageRiskRank[b.dataset.risk] ?? 9) || coverageMetric(a, "score") - coverageMetric(b, "score");
  }});
}}

function renderCoverageRows() {{
  const q = coverageSearch.value.trim().toLowerCase();
  const risk = coverageRisk.value;
  let visible = 0;
  coverageRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q)) && (!risk || row.dataset.risk === risk);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  sortCoverageRows(coverageRows).forEach(row => coverageBody.appendChild(row));
  coverageCount.textContent = `${{visible}} / ${{coverageRows.length}} 条`;
}}

function filteredCoverageData() {{
  const visibleLines = new Set(visibleCoverageRows().map(row => row.dataset.line));
  return coverageData.filter(row => visibleLines.has(row.line));
}}

function downloadCoverageRows() {{
  const rows = filteredCoverageData();
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const header = ["research_line", "owner", "team", "cadence", "papers", "score", "risk", "missing_total", "field", "coverage", "missing", "unique", "top_values"];
  const flat = [];
  rows.forEach(row => {{
    row.fields.forEach(field => {{
      flat.push([
        row.line,
        row.owner || "",
        row.team || "",
        row.cadence || "",
        row.count,
        row.score,
        row.risk,
        row.missing_total,
        field.label,
        field.coverage,
        field.missing,
        field.unique,
        (field.top_values || []).map(item => `${{item.value}}:${{item.count}}`).join("; "),
      ]);
    }});
  }});
  const csv = [header, ...flat].map(row => row.map(coverageCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "research_line_coverage.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

async function copyCoverageQueue() {{
  const rows = filteredCoverageData();
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const lines = ["# Research Line Coverage Review", ""];
  rows.forEach(row => {{
    const weak = row.fields.filter(field => field.missing > 0 || field.coverage < 100);
    lines.push(`- [ ] ${{row.risk}} / score ${{row.score}} / ${{row.line}}`);
    if (row.owner || row.team) lines.push(`  - Owner: ${{row.owner || "Unassigned"}}${{row.team ? " / " + row.team : ""}}`);
    lines.push(`  - Papers: ${{row.count}}, missing slots: ${{row.missing_total}}`);
    weak.forEach(field => lines.push(`  - ${{field.label}}: ${{field.coverage}}%, missing ${{field.missing}}, unique ${{field.unique}}`));
  }});
  const text = lines.join("\\n") + "\\n";
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt("复制治理清单", text);
  }}
}}

[coverageSearch, coverageRisk, coverageSort].forEach(control => control.addEventListener("input", renderCoverageRows));
downloadCoverageCsv.addEventListener("click", downloadCoverageRows);
copyCoverageMarkdown.addEventListener("click", copyCoverageQueue);
renderCoverageRows();
</script>
"""
    (report_dir / "coverage.html").write_text(page_shell("研究线分类覆盖地图", body, extra_css=coverage_css), encoding="utf-8")


def taxonomy_action_status(count: int, share: float) -> tuple[str, str]:
    policy = GOVERNANCE_POLICY["taxonomy_actions"]
    if count == 0:
        return "unused_config", "medium"
    if count <= int(policy["singleton_max_count"]):
        return "merge_candidate", "medium"
    if share >= float(policy["split_share"]) and count >= int(policy["split_min_count"]):
        return "split_candidate", "high"
    if share >= float(policy["watch_share"]) and count >= int(policy["watch_min_count"]):
        return "watch", "low"
    return "stable", "none"


def taxonomy_action_recommendation(action: str, field_label: str) -> str:
    if action == "unused_config":
        return "保留为候选值，或从 taxonomy.json 中移除。"
    if action == "merge_candidate":
        return "检查是否应合并为更通用标签。"
    if action == "split_candidate":
        return f"{field_label} 过大，考虑拆成更细子类。"
    if action == "watch":
        return "关注是否正在变成默认桶。"
    return "结构稳定，继续积累样本。"


def build_taxonomy_actions(papers: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(papers)
    taxonomy = taxonomy_counts(papers)
    actions: list[dict[str, Any]] = []
    summary = {
        "merge_candidate": 0,
        "split_candidate": 0,
        "unused_config": 0,
        "watch": 0,
    }
    for field, english, query_key, label, is_list in FACET_SPECS:
        counts = facet_count_for_field(papers, taxonomy, field, is_list)
        for value, count in counts.items():
            share = (count / total) if total else 0
            action, severity = taxonomy_action_status(count, share)
            if action == "stable":
                continue
            summary[action] += 1
            matches = [
                paper
                for paper in papers
                if value in facet_values_for_paper(paper, field, is_list)
            ][:5]
            actions.append(
                {
                    "action": action,
                    "severity": severity,
                    "field": field,
                    "field_label": label,
                    "field_en": english,
                    "value": value,
                    "count": count,
                    "share": round(share, 4),
                    "href": page_query_href("library.html", **{query_key: value}),
                    "sample_slugs": [paper["slug"] for paper in matches],
                    "recommendation": taxonomy_action_recommendation(action, label),
                }
            )
    severity_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}
    actions.sort(key=lambda item: (severity_rank.get(item["severity"], 9), item["action"], item["field"], -item["count"], item["value"].lower()))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(actions),
        "paper_count": total,
        "summary": summary,
        "governance_policy": json.loads(json.dumps(GOVERNANCE_POLICY["taxonomy_actions"])),
        "actions": actions,
    }


def write_taxonomy_actions_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_taxonomy_actions(papers)
    (report_dir / "taxonomy_actions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_facets_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(papers)
    taxonomy = taxonomy_counts(papers)
    balance_by_field = {item["field"]: item for item in taxonomy_balance_report(papers)}
    fields: list[dict[str, Any]] = []
    values: list[dict[str, Any]] = []
    summary = Counter()

    for field, english, query_key, label, is_list in FACET_SPECS:
        counts = facet_count_for_field(papers, taxonomy, field, is_list)
        configured = registry_configured_values(field)
        grouped_papers = registry_field_papers(papers, field, is_list)
        balance = balance_by_field.get(field, {})
        fields.append(
            {
                "field": field,
                "label": label,
                "english": english,
                "query_key": query_key,
                "is_list": is_list,
                "configured_count": int(balance.get("configured_count") or len(counts)),
                "used_count": int(balance.get("used_count") or sum(1 for count in counts.values() if count > 0)),
                "unused_count": int(balance.get("unused_count") or sum(1 for count in counts.values() if count == 0)),
                "singleton_count": int(balance.get("singleton_count") or sum(1 for count in counts.values() if count == 1)),
                "overloaded_count": int(balance.get("overloaded_count") or 0),
                "max_value": str(balance.get("max_value") or ""),
                "max_count": int(balance.get("max_count") or 0),
                "max_share": float(balance.get("max_share") or 0),
                "effective_count": float(balance.get("effective_count") or 0),
                "balance_score": int(balance.get("balance_score") or 0),
                "href": page_query_href("library.html"),
            }
        )
        summary["fields"] += 1
        summary["configured_values"] += len(configured)

        for value, count in sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0]).lower())):
            value_text = str(value or "").strip()
            if not value_text:
                continue
            share = (int(count) / total) if total else 0
            action, severity = taxonomy_action_status(int(count), share)
            definition = label_definition(field, value_text)
            owner = definition.get("owner") if definition else ""
            if not owner and field == "research_line":
                owner = research_line_owner(value_text).get("owner") or ""
            sample_slugs = [paper["slug"] for paper in grouped_papers.get(value_text, [])[:5]]
            values.append(
                {
                    "field": field,
                    "field_label": label,
                    "english": english,
                    "query_key": query_key,
                    "value": value_text,
                    "count": int(count),
                    "share": round(share, 4),
                    "configured": value_text in configured,
                    "definition_status": str(definition.get("status") or "") if definition else "",
                    "owner_name": str(owner or ""),
                    "action": action,
                    "severity": severity,
                    "href": page_query_href("library.html", **{query_key: value_text}),
                    "sample_slugs": sample_slugs,
                    "recommendation": taxonomy_action_recommendation(action, label),
                }
            )
            summary[action] += 1
            summary[severity] += 1

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": total,
        "field_count": len(fields),
        "value_count": len(values),
        "summary": dict(sorted(summary.items())),
        "fields": fields,
        "values": values,
        "csv_columns": [
            "field",
            "field_label",
            "value",
            "count",
            "share",
            "configured",
            "definition_status",
            "owner_name",
            "action",
            "severity",
            "href",
            "sample_slugs",
            "recommendation",
        ],
        "commands": [
            "python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md",
            "python3 scripts/export_taxonomy_actions.py docs --format csv --output docs/exports/taxonomy-actions.csv",
            "python3 scripts/export_taxonomy_registry.py docs --output docs/exports/taxonomy-registry.md",
            "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv",
            "python3 scripts/apply_library_metadata.py docs --input <metadata-patch.csv>",
        ],
        "links": {
            "html": "facets.html",
            "library": "library.html",
            "taxonomy": "taxonomy.html",
            "registry": "registry.html",
            "quality": "quality.html",
            "actions": "taxonomy_actions.json",
        },
    }


def write_facets_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_facets_payload(papers)
    (report_dir / "facets.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_facets(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    total = len(papers)
    taxonomy = taxonomy_counts(papers)
    action_payload = build_taxonomy_actions(papers)

    def sample_links(field: str, value: str, is_list: bool) -> str:
        matches = [
            paper
            for paper in papers
            if value in facet_values_for_paper(paper, field, is_list)
        ][:3]
        if not matches:
            return '<span class="meta">暂无论文</span>'
        links = [
            f'<a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
            for paper in matches
        ]
        return "<br>".join(links)

    facet_cards = []
    table_rows = []
    field_options = []
    long_tail_total = 0
    overloaded_total = 0
    unused_total = 0
    for field, english, query_key, label, is_list in FACET_SPECS:
        field_options.append(f'<option value="{html.escape(field, quote=True)}">{html.escape(label)}</option>')
        counts = facet_count_for_field(papers, taxonomy, field, is_list)
        used_items = [(value, count) for value, count in counts.items() if count > 0]
        long_tail = sum(1 for _, count in used_items if count == 1)
        overloaded = sum(1 for _, count in used_items if total and count / total >= 0.6 and count >= 5)
        unused = sum(1 for _, count in counts.items() if count == 0)
        long_tail_total += long_tail
        overloaded_total += overloaded
        unused_total += unused
        facet_cards.append(
            f"""<section class="facet-card">
  <h2>{html.escape(label)} <span class="meta">{html.escape(english)}</span></h2>
  <div class="facet-metrics"><strong>{len(used_items)}</strong><span>已使用标签</span><strong>{long_tail}</strong><span>长尾</span><strong>{unused}</strong><span>候选空值</span></div>
</section>"""
        )
        for value, count in counts.items():
            share = (count / total) if total else 0
            action, severity = taxonomy_action_status(count, share)
            flags = [action]
            if action == "unused_config":
                flags.append("unused")
            if action == "merge_candidate":
                flags.append("long-tail")
            if action == "split_candidate":
                flags.append("overloaded")
            flag_html = "".join(f'<span class="flag">{html.escape(flag)}</span>' for flag in flags) or '<span class="flag">stable</span>'
            href = page_query_href("library.html", **{query_key: value})
            value_cell = f'<a href="{html.escape(href)}">{html.escape(value)}</a>'
            recommendation = taxonomy_action_recommendation(action, label)
            search_text = " ".join([label, english, value, action, severity, recommendation]).lower()
            table_rows.append(
                f'<tr data-field="{html.escape(label, quote=True)}" data-field-key="{html.escape(field, quote=True)}" data-action="{html.escape(action, quote=True)}" data-severity="{html.escape(severity, quote=True)}" data-value="{html.escape(value, quote=True)}" data-count="{count}" data-share="{round(share, 4)}" data-href="{html.escape(href, quote=True)}" data-recommendation="{html.escape(recommendation, quote=True)}" data-search="{html.escape(search_text, quote=True)}">'
                f"<td>{html.escape(label)}</td>"
                f"<td>{value_cell}</td>"
                f"<td>{count}</td>"
                f"<td>{round(share * 100)}%</td>"
                f"<td>{html.escape(severity)}</td>"
                f"<td>{flag_html}</td>"
                f"<td>{sample_links(field, value, is_list)}</td>"
                f"<td>{html.escape(recommendation)}</td>"
                "</tr>"
            )

    table_html = (
        '<table class="data-table"><thead><tr><th>字段</th><th>标签</th><th>论文</th><th>占比</th><th>优先级</th><th>状态</th><th>样例</th><th>建议动作</th></tr></thead>'
        f"<tbody>{''.join(table_rows)}</tbody></table>"
        if table_rows
        else '<div class="empty">还没有可审计的分类。</div>'
    )

    facets_css = """
    .facet-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 14px;
    }
    .facet-card {
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .facet-card h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.3;
    }
    .facet-metrics {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 6px 10px;
      align-items: baseline;
    }
    .facet-metrics strong { color: var(--accent); font-size: 22px; }
    .facet-actions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .facet-action {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--chip);
      padding: 14px;
    }
    .facet-action h3 { margin: 0 0 6px; font-size: 16px; }
    .facet-controls {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(140px, 190px)) repeat(3, auto);
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }
    .facet-controls input,
    .facet-controls select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 10px 12px;
      color: var(--text);
      font: inherit;
    }
    @media (max-width: 760px) {
      .facet-controls { grid-template-columns: 1fr; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Facet Workbench</div>
  <h1>分类工作台</h1>
  <p class="lead">集中审计 domain、track、problem、topic、method、研究线和阅读状态的规模。长尾标签提示可能需要合并，过载标签提示需要拆分，空候选值来自动态 taxonomy 配置；治理任务同步写入 taxonomy_actions.json。</p>
  <div class="stats">
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="facets.json">Facets JSON</a>
    <a class="stat" href="taxonomy_actions.json">治理任务 JSON</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <span class="stat">论文 {total}</span>
    <span class="stat">长尾 {long_tail_total}</span>
    <span class="stat">过载 {overloaded_total}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">字段概览</h2>
    <div class="facet-grid">{"".join(facet_cards)}</div>
  </section>
  <section>
    <h2 class="section-title">治理建议</h2>
    <div class="facet-actions">
      <section class="facet-action"><h3>长尾标签</h3><p class="meta">{long_tail_total} 个只命中 1 篇论文的标签。优先检查是否是大小写、复数、连字符或粒度不一致。</p></section>
      <section class="facet-action"><h3>过载标签</h3><p class="meta">{overloaded_total} 个标签覆盖过高。论文继续增加时，优先把它们拆成更可操作的子类。</p></section>
      <section class="facet-action"><h3>候选空值</h3><p class="meta">{unused_total} 个配置值当前没有论文使用。它们适合作为流程预留，也可能是过期状态。</p></section>
      <section class="facet-action"><h3>机器任务</h3><p class="meta">当前 taxonomy_actions.json 里有 {action_payload["count"]} 条可分派治理任务，可接入 issue、看板或桌面软件。</p></section>
    </div>
  </section>
  <section>
    <h2 class="section-title">分类明细</h2>
    <div class="facet-controls">
      <input id="facetSearch" type="search" placeholder="搜索字段、标签、建议动作">
      <select id="facetField"><option value="">全部字段</option>{"".join(field_options)}</select>
      <select id="facetSeverity"><option value="">全部优先级</option><option value="high">high</option><option value="medium">medium</option><option value="low">low</option><option value="none">none</option></select>
      <select id="facetAction"><option value="">全部状态</option><option value="merge_candidate">长尾待合并</option><option value="split_candidate">过载待拆分</option><option value="unused_config">候选空值</option><option value="watch">观察中</option><option value="stable">稳定</option></select>
      <strong id="facetResultCount">{len(table_rows)} 项</strong>
      <button id="downloadFacetCsv" class="button" type="button">下载当前 CSV</button>
      <button id="copyFacetMarkdown" class="button" type="button">复制清单</button>
      <button id="copyFacetCommand" class="button" type="button">复制治理命令</button>
    </div>
    <div class="table-wrap">{table_html}</div>
  </section>
</main>
<script>
const facetSearch = document.querySelector("#facetSearch");
const facetField = document.querySelector("#facetField");
const facetSeverity = document.querySelector("#facetSeverity");
const facetAction = document.querySelector("#facetAction");
const facetResultCount = document.querySelector("#facetResultCount");
const downloadFacetCsv = document.querySelector("#downloadFacetCsv");
const copyFacetMarkdown = document.querySelector("#copyFacetMarkdown");
const copyFacetCommand = document.querySelector("#copyFacetCommand");
const facetRows = Array.from(document.querySelectorAll("tr[data-field]"));

async function copyFacetText(text, fallbackLabel) {{
  try {{
    await navigator.clipboard.writeText(text);
    window.alert("已复制。");
  }} catch {{
    window.prompt(fallbackLabel, text);
  }}
}}

function facetCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function visibleFacetRows() {{
  return facetRows.filter(row => !row.hidden);
}}

function downloadFacetRows() {{
  const rows = visibleFacetRows();
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const header = ["field", "field_key", "value", "count", "share", "severity", "action", "recommendation", "href"];
  const body = rows.map(row => [
    row.dataset.field,
    row.dataset.fieldKey,
    row.dataset.value,
    row.dataset.count,
    row.dataset.share,
    row.dataset.severity,
    row.dataset.action,
    row.dataset.recommendation,
    row.dataset.href,
  ]);
  const csv = [header, ...body].map(row => row.map(facetCsvCell).join(",")).join("\\n") + "\\n";
  const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "facet_actions_filtered.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}}

function facetMarkdownQueue() {{
  const rows = visibleFacetRows();
  if (!rows.length) return "";
  const lines = ["# Taxonomy Governance Queue", ""];
  rows.forEach(row => {{
    const share = Math.round(Number(row.dataset.share || 0) * 100);
    lines.push(`- [ ] ${{row.dataset.severity}} / ${{row.dataset.action}} / ${{row.dataset.field}}: [${{row.dataset.value}}](${{row.dataset.href}})`);
    lines.push(`  - Count: ${{row.dataset.count}} papers, ${{share}}%`);
    lines.push(`  - Recommendation: ${{row.dataset.recommendation}}`);
  }});
  lines.push("");
  return lines.join("\\n");
}}

function taxonomyExportCommand(format = "markdown") {{
  const args = ["python3 scripts/export_taxonomy_actions.py docs"];
  if (format !== "markdown") args.push(`--format ${{format}}`);
  if (facetField.value) args.push(`--field ${{facetField.value}}`);
  if (facetSeverity.value && facetSeverity.value !== "none") args.push(`--severity ${{facetSeverity.value}}`);
  if (facetAction.value && facetAction.value !== "stable") args.push(`--action ${{facetAction.value}}`);
  return args.join(" ");
}}

function renderFacetRows() {{
  const q = facetSearch.value.trim().toLowerCase();
  const field = facetField.value;
  const severity = facetSeverity.value;
  const action = facetAction.value;
  let visible = 0;
  facetRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!field || row.dataset.fieldKey === field)
      && (!severity || row.dataset.severity === severity)
      && (!action || row.dataset.action === action);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  facetResultCount.textContent = `${{visible}} / ${{facetRows.length}} 项`;
}}

[facetSearch, facetField, facetSeverity, facetAction].forEach((control) => control.addEventListener("input", renderFacetRows));
downloadFacetCsv.addEventListener("click", downloadFacetRows);
copyFacetMarkdown.addEventListener("click", () => {{
  const text = facetMarkdownQueue();
  if (!text) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  copyFacetText(text, "复制分类治理清单");
}});
copyFacetCommand.addEventListener("click", () => copyFacetText(taxonomyExportCommand("project"), "复制分类治理命令"));
renderFacetRows();
</script>
"""
    (report_dir / "facets.html").write_text(page_shell("分类工作台", body, extra_css=facets_css), encoding="utf-8")


def paper_relation_features(paper: dict[str, Any]) -> set[str]:
    features: set[str] = set()
    for field in ("domains", "tracks", "problems", "topics", "methods"):
        features.update(f"{field}:{value}" for value in paper.get(field, []) if value)
    if paper.get("research_line") and paper.get("research_line") != "Unassigned":
        features.add(f"line:{paper['research_line']}")
    if paper.get("line_role"):
        features.add(f"role:{paper['line_role']}")
    return features


def relation_label(feature: str) -> str:
    prefixes = {
        "domains": "Domain",
        "tracks": "Track",
        "problems": "Problem",
        "topics": "Topic",
        "methods": "Method",
        "line": "Line",
        "role": "Role",
    }
    if ":" not in feature:
        return feature
    prefix, value = feature.split(":", 1)
    return f"{prefixes.get(prefix, prefix)} / {value}"


def render_related(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    feature_by_slug = {paper["slug"]: paper_relation_features(paper) for paper in papers}
    pair_counter: Counter[tuple[str, str]] = Counter()
    pair_examples: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        features = sorted(feature_by_slug[paper["slug"]])
        for left, right in itertools.combinations(features, 2):
            key = (left, right)
            pair_counter[key] += 1
            if len(pair_examples[key]) < 4:
                pair_examples[key].append(paper)

    cooccurrence_rows = []
    for (left, right), count in sorted(pair_counter.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:40]:
        examples = "、".join(
            f'<a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
            for paper in pair_examples[(left, right)]
        )
        cooccurrence_rows.append(
            "<tr>"
            f"<td>{html.escape(relation_label(left))}</td>"
            f"<td>{html.escape(relation_label(right))}</td>"
            f"<td>{count}</td>"
            f"<td>{examples}</td>"
            "</tr>"
        )
    cooccurrence_table = (
        '<table class="data-table"><thead><tr><th>标签 A</th><th>标签 B</th><th>共现</th><th>样例论文</th></tr></thead>'
        f"<tbody>{''.join(cooccurrence_rows)}</tbody></table>"
        if cooccurrence_rows
        else '<div class="empty">还没有足够标签形成共现。</div>'
    )

    similarity_rows = []
    max_score_by_slug = {paper["slug"]: 0 for paper in papers}
    for left, right in itertools.combinations(papers, 2):
        left_features = feature_by_slug[left["slug"]]
        right_features = feature_by_slug[right["slug"]]
        union = left_features | right_features
        if not union:
            continue
        shared = left_features & right_features
        score = round(100 * len(shared) / len(union))
        if score <= 0:
            continue
        max_score_by_slug[left["slug"]] = max(max_score_by_slug[left["slug"]], score)
        max_score_by_slug[right["slug"]] = max(max_score_by_slug[right["slug"]], score)
        similarity_rows.append((score, left, right, sorted(shared)))

    similar_table_rows = []
    for score, left, right, shared in sorted(
        similarity_rows,
        key=lambda item: (-item[0], item[1]["title"], item[2]["title"]),
    )[:60]:
        shared_labels = "".join(f'<span class="chip">{html.escape(relation_label(feature))}</span>' for feature in shared[:8])
        if len(shared) > 8:
            shared_labels += f'<span class="chip">+{len(shared) - 8}</span>'
        similar_table_rows.append(
            "<tr>"
            f"<td>{score}</td>"
            f'<td><a href="{html.escape(paper_href(left))}">{html.escape(left["title_zh"] or left["title"])}</a></td>'
            f'<td><a href="{html.escape(paper_href(right))}">{html.escape(right["title_zh"] or right["title"])}</a></td>'
            f'<td><div class="chips">{shared_labels}</div></td>'
            "</tr>"
        )
    similarity_table = (
        '<table class="data-table"><thead><tr><th>相似度</th><th>论文 A</th><th>论文 B</th><th>共享特征</th></tr></thead>'
        f"<tbody>{''.join(similar_table_rows)}</tbody></table>"
        if similar_table_rows
        else '<div class="empty">还没有可计算的相似论文。</div>'
    )

    isolated = [paper for paper in papers if max_score_by_slug.get(paper["slug"], 0) == 0]
    isolated_html = (
        '<ol class="queue-list">'
        + "".join(
            f'<li><a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
            f' <span class="meta">{html.escape(str(paper.get("research_line") or "Unassigned"))}</span></li>'
            for paper in isolated
        )
        + "</ol>"
        if isolated
        else '<div class="empty">没有孤岛论文。</div>'
    )

    related_css = """
    .relation-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    .relation-summary .metric-card strong { font-size: 28px; }
    .data-table td:nth-child(4) .chips { padding-top: 0; }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Relation Network</div>
  <h1>关联网络</h1>
  <p class="lead">按 frontmatter 中的研究线、结构分类、主题和方法计算标签共现与论文相似度，帮助发现研究簇、重复分类、孤岛论文和潜在的阅读路径。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">共现 {len(pair_counter)}</span>
    <span class="stat">相似对 {len(similarity_rows)}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">关系摘要</h2>
    <div class="relation-summary">
      <div class="metric-card"><strong>{len(pair_counter)}</strong><span>标签共现边</span></div>
      <div class="metric-card"><strong>{len(similarity_rows)}</strong><span>相似论文对</span></div>
      <div class="metric-card"><strong>{len(isolated)}</strong><span>孤岛论文</span></div>
    </div>
  </section>
  <section>
    <h2 class="section-title">标签共现</h2>
    <div class="table-wrap">{cooccurrence_table}</div>
  </section>
  <section>
    <h2 class="section-title">相似论文</h2>
    <div class="table-wrap">{similarity_table}</div>
  </section>
  <section>
    <h2 class="section-title">孤岛论文</h2>
    {isolated_html}
  </section>
</main>
"""
    (report_dir / "related.html").write_text(page_shell("关联网络", body, extra_css=related_css), encoding="utf-8")


def render_taxonomy(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
    controls = control_options()
    guide_link = (
        '<a class="stat" href="guides/taxonomy.md">分类指南</a>'
        if (report_dir / "guides" / "taxonomy.md").exists()
        else ""
    )

    def paper_link_list(items: list[dict[str, Any]], empty: str) -> str:
        if not items:
            return f'<div class="empty">{html.escape(empty)}</div>'
        rows = "".join(
            f'<li><a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a> '
            f'<span class="meta">{html.escape(str(paper.get("research_line") or "Unassigned"))}</span></li>'
            for paper in items[:10]
        )
        more = f'<div class="meta">另有 {len(items) - 10} 篇未显示。</div>' if len(items) > 10 else ""
        return f'<ol class="queue-list">{rows}</ol>{more}'

    def count_link(count: int, **params: str) -> str:
        href = page_query_href("library.html", **params)
        return f'<a class="matrix-link" href="{html.escape(href)}">{count}</a>' if count else '<span class="meta">0</span>'

    def top_chips(counter: Counter[str], limit: int = 4) -> str:
        if not counter:
            return '<span class="meta">暂无</span>'
        return "".join(
            f'<span class="chip">{html.escape(name)} {count}</span>'
            for name, count in counter.most_common(limit)
        )

    domain_rows = []
    for domain in taxonomy["domains"]:
        items = [paper for paper in papers if domain in paper.get("domains", [])]
        tracks = Counter(track for paper in items for track in paper.get("tracks", []))
        problems = Counter(problem for paper in items for problem in paper.get("problems", []))
        lines = Counter(str(paper.get("research_line") or "Unassigned") for paper in items)
        domain_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(page_query_href("library.html", domain=domain))}">{html.escape(domain)}</a></td>'
            f"<td>{len(items)}</td>"
            f"<td>{top_chips(tracks)}</td>"
            f"<td>{top_chips(problems)}</td>"
            f"<td>{top_chips(lines)}</td>"
            "</tr>"
        )
    domain_table = (
        '<table class="data-table"><thead><tr><th>Domain</th><th>论文</th><th>主要 Track</th><th>主要 Problem</th><th>研究线</th></tr></thead>'
        f"<tbody>{''.join(domain_rows)}</tbody></table>"
        if domain_rows
        else '<div class="empty">还没有 domain 分类。</div>'
    )

    track_rows = []
    for track in taxonomy["tracks"]:
        items = [paper for paper in papers if track in paper.get("tracks", [])]
        domains = Counter(domain for paper in items for domain in paper.get("domains", []))
        problems = Counter(problem for paper in items for problem in paper.get("problems", []))
        track_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(page_query_href("library.html", track=track))}">{html.escape(track)}</a></td>'
            f"<td>{len(items)}</td>"
            f"<td>{top_chips(domains, 3)}</td>"
            f"<td>{top_chips(problems, 5)}</td>"
            "</tr>"
        )
    track_table = (
        '<table class="data-table"><thead><tr><th>Track</th><th>论文</th><th>Domain</th><th>Problem</th></tr></thead>'
        f"<tbody>{''.join(track_rows)}</tbody></table>"
        if track_rows
        else '<div class="empty">还没有 track 分类。</div>'
    )

    role_values = list(ROLE_ORDER.keys())
    extra_roles = sorted(
        {
            str(paper.get("line_role") or "unclassified")
            for paper in papers
            if str(paper.get("line_role") or "unclassified") not in ROLE_ORDER
        }
    )
    role_values.extend(extra_roles)

    line_rows = []
    for line in taxonomy["research_lines"]:
        if line == "Unassigned":
            continue
        items = [paper for paper in papers if paper.get("research_line") == line]
        cells = []
        for role in role_values:
            count = sum(1 for paper in items if (paper.get("line_role") or "unclassified") == role)
            cells.append(f"<td>{count_link(count, line=line, role=role)}</td>")
        line_link = f"lines/{slugify_label(line)}.html"
        line_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(line_link)}">{html.escape(line)}</a></td>'
            f"<td>{len(items)}</td>"
            f"{''.join(cells)}"
            "</tr>"
        )
    role_header = "".join(f"<th>{html.escape(role)}</th>" for role in role_values)
    line_matrix = (
        '<table class="data-table"><thead><tr><th>研究线</th><th>论文</th>'
        f"{role_header}</tr></thead><tbody>{''.join(line_rows)}</tbody></table>"
        if line_rows
        else '<div class="empty">还没有研究线。</div>'
    )

    statuses = list(taxonomy["statuses"].keys())
    stages = list(taxonomy["reading_stages"].keys())
    stage_header = "".join(f"<th>{html.escape(stage)}</th>" for stage in stages)
    state_rows = []
    for status in statuses:
        status_items = [paper for paper in papers if paper.get("status") == status]
        cells = []
        for stage in stages:
            count = sum(1 for paper in status_items if paper.get("reading_stage") == stage)
            cells.append(f"<td>{count_link(count, status=status, stage=stage)}</td>")
        state_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(page_query_href("library.html", status=status))}">{html.escape(status)}</a></td>'
            f"<td>{len(status_items)}</td>"
            f"{''.join(cells)}"
            "</tr>"
        )
    state_matrix = (
        '<table class="data-table"><thead><tr><th>Status</th><th>论文</th>'
        f"{stage_header}</tr></thead><tbody>{''.join(state_rows)}</tbody></table>"
    )

    review_rows = []
    for stage, count in taxonomy["review_stages"].items():
        review_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(page_query_href("library.html", reviewStage=stage))}">{html.escape(stage)}</a></td>'
            f"<td>{count}</td>"
            "</tr>"
        )
    review_table = (
        '<table class="data-table"><thead><tr><th>Review stage</th><th>论文</th></tr></thead>'
        f"<tbody>{''.join(review_rows)}</tbody></table>"
    )

    def workflow_value_chips(values: list[str]) -> str:
        return "".join(f'<span class="chip">{html.escape(value)}</span>' for value in values)

    workflow_rows = [
        (
            "status",
            "论文生命周期",
            controls["status"],
            "控制首页、论文库筛选和状态看板列",
        ),
        (
            "reading_stage",
            "阅读深度",
            controls["reading_stage"],
            "控制批量更新和阅读深度筛选",
        ),
        (
            "review_stage",
            "复习阶段",
            controls["review_stage"],
            "控制复习队列和复习阶段筛选",
        ),
    ]
    workflow_table_rows = "".join(
        "<tr>"
        f"<td>{html.escape(field)}</td>"
        f"<td>{html.escape(purpose)}</td>"
        f'<td><div class="chips">{workflow_value_chips(values)}</div></td>'
        f"<td>{html.escape(effect)}</td>"
        "</tr>"
        for field, purpose, values, effect in workflow_rows
    )
    workflow_table = (
        '<table class="data-table"><thead><tr><th>字段</th><th>用途</th><th>当前可选值</th><th>影响页面</th></tr></thead>'
        f"<tbody>{workflow_table_rows}</tbody></table>"
    )
    workflow_name = ACTIVE_STATUS_WORKFLOW or "personal"
    status_workflows = controls.get("status_workflows") or {}
    if not status_workflows:
        status_workflows = {
            workflow_name: {
                "status_values": controls["status"],
                "reading_stage_values": controls["reading_stage"],
                "review_stage_values": controls["review_stage"],
            }
        }
    workflow_config = {
        "active_status_workflow": workflow_name,
        "status_workflows": status_workflows,
    }
    workflow_seed = {
        "name": workflow_name,
        "status_values": controls["status"],
        "reading_stage_values": controls["reading_stage"],
        "review_stage_values": controls["review_stage"],
    }
    workflow_config_json = html.escape(json.dumps(workflow_config, ensure_ascii=False, indent=2))
    workflow_seed_json = html.escape(json.dumps(workflow_seed, ensure_ascii=False), quote=True)
    workflow_all_json = html.escape(json.dumps(status_workflows, ensure_ascii=False), quote=True)
    governance_policy = controls.get("governance_policy") or {}
    policy_sections = [
        ("taxonomy_load", "单篇分类密度", "影响 quality.json 的 taxonomy_load 队列"),
        ("taxonomy_actions", "分类 action 阈值", "影响 taxonomy_actions.json 的 merge / watch / split 判断"),
        ("taxonomy_balance", "分类均衡风险", "影响 balance.html 的 high / medium / low 风险"),
        ("coverage", "研究线覆盖风险", "影响 coverage.html 的覆盖风险"),
    ]
    policy_labels = {
        "min_structure_labels": "最少结构标签",
        "min_tags": "最少 topic/method",
        "max_tags": "最多 topic/method",
        "max_methods": "最多 method",
        "singleton_max_count": "长尾最大计数",
        "watch_share": "关注占比",
        "watch_min_count": "关注最少论文",
        "split_share": "拆分占比",
        "split_min_count": "拆分最少论文",
        "high_score_below": "高风险低于",
        "medium_score_below": "中风险低于",
        "singleton_medium_count": "中风险长尾数",
        "unused_medium_count": "中风险空候选数",
        "missing_high_min": "高风险最少缺口",
    }
    policy_rows = []
    policy_inputs = []
    for section, title, effect in policy_sections:
        values = governance_policy.get(section) or {}
        for key, value in values.items():
            label = policy_labels.get(str(key), str(key))
            policy_rows.append(
                "<tr>"
                f"<td>{html.escape(section)}</td>"
                f"<td>{html.escape(label)}<div class=\"meta\">{html.escape(str(key))}</div></td>"
                f"<td><code>{html.escape(str(value))}</code></td>"
                f"<td>{html.escape(effect)}</td>"
                "</tr>"
            )
            step = "0.01" if isinstance(value, float) else "1"
            policy_inputs.append(
                "<label>"
                f"<span>{html.escape(title)} / {html.escape(label)}</span>"
                f'<input class="policy-input" type="number" min="0" step="{step}" '
                f'data-section="{html.escape(section, quote=True)}" data-key="{html.escape(str(key), quote=True)}" '
                f'value="{html.escape(str(value), quote=True)}">'
                "</label>"
            )
    policy_table = (
        '<table class="data-table"><thead><tr><th>策略组</th><th>阈值</th><th>当前值</th><th>影响</th></tr></thead>'
        f"<tbody>{''.join(policy_rows)}</tbody></table>"
        if policy_rows
        else '<div class="empty">暂无治理策略配置。</div>'
    )
    policy_config = {"governance_policy": governance_policy}
    policy_config_json = html.escape(json.dumps(policy_config, ensure_ascii=False, indent=2))
    policy_seed_json = html.escape(json.dumps(policy_config, ensure_ascii=False), quote=True)
    taxonomy_change_fields = []
    for field, english, _query_key, label, is_list in FACET_SPECS:
        values = sorted(facet_count_for_field(papers, taxonomy, field, is_list), key=lambda value: value.lower())
        taxonomy_change_fields.append(
            {
                "field": field,
                "label": label,
                "english": english,
                "is_list": is_list,
                "values": values,
            }
        )
    taxonomy_change_papers = [
        {
            "slug": paper["slug"],
            "title": paper.get("title_zh") or paper.get("title") or paper["slug"],
            "href": paper_href(paper),
            "fields": {
                field["field"]: (
                    paper.get(field["field"], [])
                    if field["is_list"]
                    else str(paper.get(field["field"]) or "")
                )
                for field in taxonomy_change_fields
            },
        }
        for paper in papers
    ]
    taxonomy_change_fields_json = json.dumps(taxonomy_change_fields, ensure_ascii=False).replace("</", "<\\/")
    taxonomy_change_papers_json = json.dumps(taxonomy_change_papers, ensure_ascii=False).replace("</", "<\\/")

    long_tail = Counter(
        tag
        for paper in papers
        for tag in [*paper.get("topics", []), *paper.get("methods", [])]
    )
    tail_items = [
        (tag, count)
        for tag, count in sorted(long_tail.items(), key=lambda item: (item[1], item[0].lower()))
        if count == 1
    ][:24]
    tail_html = (
        '<div class="tag-list">'
        + "".join(f'<span class="tag-pill"><span>{html.escape(tag)}</span><strong>{count}</strong></span>' for tag, count in tail_items)
        + "</div>"
        if tail_items
        else '<div class="empty">暂无长尾 topic/method。</div>'
    )
    alias_suggestions = label_alias_suggestions(papers)
    alias_rows = "".join(render_alias_suggestion_row(item) for item in alias_suggestions)
    alias_table = (
        '<table class="data-table"><thead><tr><th>建议规范值</th><th>建议别名</th><th>涉及论文</th><th>taxonomy.json 片段</th></tr></thead>'
        f"<tbody>{alias_rows}</tbody></table>"
        if alias_rows
        else '<div class="empty">暂无标签归一化建议。</div>'
    )

    queue_specs = [
        ("缺 Domain", [paper for paper in papers if not paper.get("domains")], "所有论文都有 domain。"),
        ("缺 Track", [paper for paper in papers if not paper.get("tracks")], "所有论文都有 track。"),
        ("缺 Problem", [paper for paper in papers if not paper.get("problems")], "所有论文都有 problem。"),
        ("缺 Topic", [paper for paper in papers if not paper.get("topics")], "所有论文都有 topic。"),
        ("缺 Method", [paper for paper in papers if not paper.get("methods")], "所有论文都有 method。"),
        (
            "缺研究线",
            [paper for paper in papers if paper.get("research_line") == "Unassigned"],
            "所有论文都有 research_line。",
        ),
        ("缺角色", [paper for paper in papers if not paper.get("line_role")], "所有论文都有 line_role。"),
    ]
    queue_cards = "".join(
        f'<section class="role-section"><h2>{html.escape(title)} <span class="meta">{len(items)}</span></h2>{paper_link_list(items, empty)}</section>'
        for title, items, empty in queue_specs
    )

    body = f"""
<header class="shell">
  <div class="eyebrow">Taxonomy Operations</div>
  <h1>分类治理</h1>
  <p class="lead">面向大量论文的分类治理视图：检查 domain / track / problem 层级、研究线角色矩阵、状态分布和需要补齐的元数据队列。所有计数都可以回跳到论文库表格继续筛选。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="tags.html">分类总览</a>
    {guide_link}
    <a class="stat" href="stats.json">统计 JSON</a>
    <a class="stat" href="papers.json">JSON 索引</a>
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">Domain {len(taxonomy["domains"])}</span>
    <span class="stat">Research line {len(taxonomy["research_lines"])}</span>
    <span class="stat">别名建议 {len(alias_suggestions)}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">结构分类层级</h2>
    <div class="taxonomy-board">
      <section class="taxonomy-panel"><h2>Domain -> Track / Problem</h2>{domain_table}</section>
      <section class="taxonomy-panel"><h2>Track -> Problem</h2>{track_table}</section>
    </div>
  </section>
  <section>
    <h2 class="section-title">研究线角色矩阵</h2>
    <div class="table-wrap">{line_matrix}</div>
  </section>
  <section>
    <h2 class="section-title">状态矩阵</h2>
    <div class="taxonomy-board">
      <section class="taxonomy-panel"><h2>Status x Reading stage</h2>{state_matrix}</section>
      <section class="taxonomy-panel"><h2>Review stage</h2>{review_table}</section>
    </div>
  </section>
  <section>
    <h2 class="section-title">状态工作流配置</h2>
    <div class="taxonomy-board">
      <section class="taxonomy-panel"><h2>当前动态选项</h2>{workflow_table}</section>
      <section class="taxonomy-panel">
        <h2>taxonomy.json 片段</h2>
        <pre class="config-snippet"><code>{workflow_config_json}</code></pre>
      </section>
    </div>
    <section class="taxonomy-panel workflow-designer" data-workflow="{workflow_seed_json}" data-workflows="{workflow_all_json}">
      <div>
        <h2>状态工作流设计器</h2>
        <p class="meta">载入已有 workflow 或命名一套新 workflow，每行一个值。下载或复制后合并到 guides/taxonomy.json，再运行 build_wiki，首页、论文库、看板和 JSON controls 会同步更新。</p>
      </div>
      <label><span>Load existing workflow</span><select id="workflowSource"></select></label>
      <label><span>Workflow name</span><input id="workflowName" type="text" value="{html.escape(workflow_name, quote=True)}"></label>
      <div class="designer-grid">
        <label><span>Status</span><textarea id="workflowStatus" rows="6"></textarea></label>
        <label><span>Reading stage</span><textarea id="workflowReadingStage" rows="6"></textarea></label>
        <label><span>Review stage</span><textarea id="workflowReviewStage" rows="6"></textarea></label>
      </div>
      <div class="designer-actions">
        <button class="button" type="button" id="resetWorkflow">恢复当前配置</button>
        <button class="button" type="button" id="copyWorkflow">复制 JSON</button>
        <button class="button primary" type="button" id="downloadWorkflow">下载状态配置</button>
        <span class="meta" id="workflowMessage"></span>
      </div>
      <pre class="config-snippet"><code id="workflowPreview"></code></pre>
    </section>
  </section>
  <section>
    <h2 class="section-title">治理策略配置</h2>
    <div class="taxonomy-board">
      <section class="taxonomy-panel"><h2>当前阈值</h2>{policy_table}</section>
      <section class="taxonomy-panel">
        <h2>governance_policy 片段</h2>
        <pre class="config-snippet"><code>{policy_config_json}</code></pre>
      </section>
    </div>
    <section class="taxonomy-panel policy-designer" data-policy="{policy_seed_json}">
      <div>
        <h2>治理策略设计器</h2>
        <p class="meta">调整阈值后复制或下载 JSON，用 apply_governance_policy.py 先 dry-run 再写入 guides/taxonomy.json。刷新 wiki 后 quality、facets、balance 和 coverage 会用同一套策略重算。</p>
      </div>
      <div class="policy-grid">{''.join(policy_inputs)}</div>
      <div class="designer-actions">
        <button class="button" type="button" id="resetPolicy">恢复当前策略</button>
        <button class="button" type="button" id="copyPolicy">复制 JSON</button>
        <button class="button primary" type="button" id="downloadPolicy">下载治理策略</button>
        <span class="meta" id="policyMessage"></span>
      </div>
      <p class="meta">应用命令：python3 scripts/apply_governance_policy.py docs --input ~/Downloads/taxonomy_governance_policy.json --write</p>
      <pre class="config-snippet"><code id="policyPreview"></code></pre>
    </section>
  </section>
  <section>
    <h2 class="section-title">分类变更预览</h2>
    <section class="taxonomy-panel taxonomy-change-planner">
      <div>
        <h2>标签 / 状态重命名影响</h2>
        <p class="meta">选择字段和旧值，填写新值后预览受影响论文；导出的 CSV 可用 apply_library_metadata.py 先 dry-run，再写回 frontmatter。</p>
      </div>
      <div class="taxonomy-change-grid">
        <label><span>字段</span><select id="taxonomyChangeField"></select></label>
        <label><span>旧值</span><select id="taxonomyChangeFrom"></select></label>
        <label><span>新值</span><input id="taxonomyChangeTo" type="text" placeholder="New value"></label>
        <button class="button primary" type="button" id="downloadTaxonomyChangePatch">下载 CSV patch</button>
      </div>
      <div class="designer-actions">
        <strong id="taxonomyChangeCount">0 篇论文</strong>
        <span class="meta">导出后运行：python3 scripts/apply_library_metadata.py docs --input ~/Downloads/taxonomy_change_patch.csv</span>
      </div>
      <div id="taxonomyChangePreview" class="taxonomy-change-preview"></div>
    </section>
  </section>
  <section>
    <h2 class="section-title">治理队列</h2>
    <div class="queue-grid">{queue_cards}</div>
  </section>
  <section>
    <h2 class="section-title">标签归一化建议</h2>
    <div class="table-wrap">{alias_table}</div>
  </section>
  <section>
    <h2 class="section-title">长尾 Topic / Method</h2>
    {tail_html}
  </section>
</main>
<script>
const taxonomyChangeFields = {taxonomy_change_fields_json};
const taxonomyChangePapers = {taxonomy_change_papers_json};

(() => {{
  const fieldSelect = document.querySelector("#taxonomyChangeField");
  const fromSelect = document.querySelector("#taxonomyChangeFrom");
  const toInput = document.querySelector("#taxonomyChangeTo");
  const count = document.querySelector("#taxonomyChangeCount");
  const preview = document.querySelector("#taxonomyChangePreview");
  const downloadButton = document.querySelector("#downloadTaxonomyChangePatch");
  if (!fieldSelect || !fromSelect || !toInput || !count || !preview || !downloadButton) return;
  const fieldByName = new Map(taxonomyChangeFields.map((field) => [field.field, field]));

  function uniqueValues(values) {{
    return Array.from(new Set(values.map((value) => String(value || "").trim()).filter(Boolean)));
  }}

  function csvCell(value) {{
    const text = String(value ?? "");
    return (text.includes(",") || text.includes('"') || text.includes("\\n"))
      ? `"${{text.replaceAll('"', '""')}}"`
      : text;
  }}

  function escapeHtml(value) {{
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }}

  function downloadCsv(filename, rows) {{
    const csv = rows.map((row) => row.map(csvCell).join(",")).join("\\n") + "\\n";
    const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }}

  function fieldValue(paper, field) {{
    const spec = fieldByName.get(field);
    const value = paper.fields[field];
    return spec && spec.is_list ? (Array.isArray(value) ? value : []) : String(value || "");
  }}

  function paperHasValue(paper, field, fromValue) {{
    const spec = fieldByName.get(field);
    const value = fieldValue(paper, field);
    return spec && spec.is_list ? value.includes(fromValue) : value === fromValue;
  }}

  function replacementValue(paper, field, fromValue, toValue) {{
    const spec = fieldByName.get(field);
    if (spec && spec.is_list) {{
      return uniqueValues(fieldValue(paper, field).map((value) => value === fromValue ? toValue : value)).join("; ");
    }}
    return toValue;
  }}

  function currentChanges() {{
    const field = fieldSelect.value;
    const fromValue = fromSelect.value;
    const toValue = toInput.value.trim();
    if (!field || !fromValue || !toValue) return [];
    return taxonomyChangePapers
      .filter((paper) => paperHasValue(paper, field, fromValue))
      .map((paper) => ({{
        ...paper,
        field,
        nextValue: replacementValue(paper, field, fromValue, toValue),
      }}));
  }}

  function renderPreview() {{
    const field = fieldSelect.value;
    const fromValue = fromSelect.value;
    const toValue = toInput.value.trim();
    const changes = currentChanges();
    downloadButton.disabled = changes.length === 0;
    count.textContent = `${{changes.length}} 篇论文`;
    if (!field || !fromValue) {{
      preview.innerHTML = '<div class="empty">请选择字段和旧值。</div>';
      return;
    }}
    if (!toValue) {{
      preview.innerHTML = '<div class="empty">填写新值后会显示可导出的 patch。</div>';
      return;
    }}
    if (!changes.length) {{
      preview.innerHTML = '<div class="empty">没有论文命中这次变更。</div>';
      return;
    }}
    const items = changes.slice(0, 30).map((paper) => (
      `<li><a href="${{escapeHtml(paper.href)}}">${{escapeHtml(paper.title)}}</a><span class="meta">${{escapeHtml(paper.slug)}} -> ${{escapeHtml(paper.nextValue)}}</span></li>`
    )).join("");
    const more = changes.length > 30 ? `<div class="meta">另有 ${{changes.length - 30}} 篇未显示。</div>` : "";
    preview.innerHTML = `<ol class="queue-list">${{items}}</ol>${{more}}`;
  }}

  function refreshFromOptions() {{
    const spec = fieldByName.get(fieldSelect.value) || taxonomyChangeFields[0];
    const values = spec ? spec.values : [];
    fromSelect.replaceChildren(...values.map((value) => new Option(value, value)));
    renderPreview();
  }}

  function downloadPatch() {{
    const field = fieldSelect.value;
    const changes = currentChanges();
    if (!changes.length) return;
    downloadCsv("taxonomy_change_patch.csv", [["slug", field], ...changes.map((paper) => [paper.slug, paper.nextValue])]);
  }}

  fieldSelect.replaceChildren(...taxonomyChangeFields.map((field) => new Option(`${{field.label}} / ${{field.english}}`, field.field)));
  fieldSelect.addEventListener("input", refreshFromOptions);
  fromSelect.addEventListener("input", renderPreview);
  toInput.addEventListener("input", renderPreview);
  downloadButton.addEventListener("click", downloadPatch);
  refreshFromOptions();
}})();

(() => {{
  const designer = document.querySelector(".workflow-designer");
  if (!designer) return;
  const seed = JSON.parse(designer.dataset.workflow || "{{}}");
  const knownWorkflows = JSON.parse(designer.dataset.workflows || "{{}}");
  const sourceSelect = document.querySelector("#workflowSource");
  const nameInput = document.querySelector("#workflowName");
  const fields = {{
    status_values: document.querySelector("#workflowStatus"),
    reading_stage_values: document.querySelector("#workflowReadingStage"),
    review_stage_values: document.querySelector("#workflowReviewStage"),
  }};
  const preview = document.querySelector("#workflowPreview");
  const message = document.querySelector("#workflowMessage");

  function uniqueLines(text) {{
    const seen = new Set();
    return String(text || "")
      .split(/\\r?\\n/)
      .map((line) => line.trim())
      .filter((line) => {{
        if (!line || seen.has(line)) return false;
        seen.add(line);
        return true;
      }});
  }}

  function payload() {{
    const workflowName = (nameInput.value || "personal").trim() || "personal";
    const workflow = Object.fromEntries(
      Object.entries(fields).map(([key, input]) => [key, uniqueLines(input.value)])
    );
    return {{
      active_status_workflow: workflowName,
      status_workflows: {{
        ...knownWorkflows,
        [workflowName]: workflow,
      }},
    }};
  }}

  function renderPreview() {{
    const data = payload();
    preview.textContent = JSON.stringify(data, null, 2);
    const workflow = data.status_workflows[data.active_status_workflow] || {{}};
    const emptyFields = Object.entries(workflow)
      .filter(([, values]) => values.length === 0)
      .map(([key]) => key);
    message.textContent = emptyFields.length ? `空字段：${{emptyFields.join(", ")}}` : "";
    return data;
  }}

  function reset() {{
    nameInput.value = seed.name || "personal";
    Object.entries(fields).forEach(([key, input]) => {{
      input.value = (seed[key] || []).join("\\n");
    }});
    if (sourceSelect) sourceSelect.value = seed.name || "";
    renderPreview();
  }}

  function loadWorkflow(name) {{
    const workflow = knownWorkflows[name];
    if (!workflow) return;
    nameInput.value = name;
    Object.entries(fields).forEach(([key, input]) => {{
      input.value = Array.isArray(workflow[key]) ? workflow[key].join("\\n") : "";
    }});
    renderPreview();
  }}

  function download() {{
    const blob = new Blob([JSON.stringify(renderPreview(), null, 2) + "\\n"], {{ type: "application/json" }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "taxonomy_status_workflow.json";
    link.click();
    URL.revokeObjectURL(url);
  }}

  async function copy() {{
    const text = JSON.stringify(renderPreview(), null, 2);
    try {{
      await navigator.clipboard.writeText(text);
      message.textContent = "已复制 JSON";
    }} catch (error) {{
      message.textContent = "当前浏览器不允许复制，可手动选中下方 JSON";
    }}
  }}

  nameInput.addEventListener("input", renderPreview);
  Object.values(fields).forEach((input) => input.addEventListener("input", renderPreview));
  sourceSelect.replaceChildren(
    ...Object.keys(knownWorkflows).map((name) => new Option(name === seed.name ? `${{name}} (active)` : name, name))
  );
  sourceSelect.addEventListener("change", () => loadWorkflow(sourceSelect.value));
  document.querySelector("#resetWorkflow").addEventListener("click", reset);
  document.querySelector("#downloadWorkflow").addEventListener("click", download);
  document.querySelector("#copyWorkflow").addEventListener("click", copy);
  reset();
}})();

(() => {{
  const designer = document.querySelector(".policy-designer");
  if (!designer) return;
  const seed = JSON.parse(designer.dataset.policy || "{{}}");
  const inputs = Array.from(designer.querySelectorAll(".policy-input"));
  const preview = document.querySelector("#policyPreview");
  const message = document.querySelector("#policyMessage");

  function numericValue(input) {{
    const raw = input.value.trim();
    if (raw === "") return 0;
    const value = Number(raw);
    return Number.isFinite(value) ? value : 0;
  }}

  function payload() {{
    const governancePolicy = {{}};
    inputs.forEach((input) => {{
      const section = input.dataset.section;
      const key = input.dataset.key;
      if (!section || !key) return;
      governancePolicy[section] = governancePolicy[section] || {{}};
      const step = String(input.step || "1");
      const value = numericValue(input);
      governancePolicy[section][key] = step.includes(".") ? value : Math.round(value);
    }});
    return {{ governance_policy: governancePolicy }};
  }}

  function renderPreview() {{
    const data = payload();
    preview.textContent = JSON.stringify(data, null, 2);
    const invalid = inputs.filter((input) => Number(input.value) < 0 || !Number.isFinite(Number(input.value)));
    message.textContent = invalid.length ? `有 ${{invalid.length}} 个无效阈值` : "";
    return data;
  }}

  function reset() {{
    const policy = seed.governance_policy || {{}};
    inputs.forEach((input) => {{
      const value = policy[input.dataset.section]?.[input.dataset.key];
      if (value !== undefined) input.value = value;
    }});
    renderPreview();
  }}

  function download() {{
    const blob = new Blob([JSON.stringify(renderPreview(), null, 2) + "\\n"], {{ type: "application/json" }});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "taxonomy_governance_policy.json";
    link.click();
    URL.revokeObjectURL(url);
  }}

  async function copy() {{
    const text = JSON.stringify(renderPreview(), null, 2);
    try {{
      await navigator.clipboard.writeText(text);
      message.textContent = "已复制 JSON";
    }} catch (error) {{
      message.textContent = "当前浏览器不允许复制，可手动选中下方 JSON";
    }}
  }}

  inputs.forEach((input) => input.addEventListener("input", renderPreview));
  document.querySelector("#resetPolicy").addEventListener("click", reset);
  document.querySelector("#downloadPolicy").addEventListener("click", download);
  document.querySelector("#copyPolicy").addEventListener("click", copy);
  reset();
}})();
</script>
"""
    taxonomy_css = "\n".join(
        [
            "    .config-snippet {",
            "      margin: 0;",
            "      padding: 12px;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      background: #f8fafc;",
            "      overflow-x: auto;",
            "      font-size: 13px;",
            "      line-height: 1.55;",
            "    }",
            "    .workflow-designer { margin-top: 16px; }",
            "    .policy-designer { margin-top: 16px; }",
            "    .designer-grid {",
            "      display: grid;",
            "      grid-template-columns: repeat(3, minmax(0, 1fr));",
            "      gap: 12px;",
            "      margin: 14px 0;",
            "    }",
            "    .policy-grid {",
            "      display: grid;",
            "      grid-template-columns: repeat(3, minmax(0, 1fr));",
            "      gap: 12px;",
            "      margin: 14px 0;",
            "    }",
            "    .designer-grid label { display: grid; gap: 6px; font-weight: 700; }",
            "    .policy-grid label { display: grid; gap: 6px; font-weight: 700; }",
            "    .designer-grid textarea {",
            "      width: 100%;",
            "      min-height: 132px;",
            "      resize: vertical;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      padding: 10px;",
            "      background: #fff;",
            "      color: var(--ink);",
            "      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;",
            "    }",
            "    .policy-grid input {",
            "      width: 100%;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      padding: 10px 12px;",
            "      background: #fff;",
            "      color: var(--ink);",
            "      font: inherit;",
            "    }",
            "    .designer-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }",
            "    .taxonomy-change-planner { margin-top: 8px; }",
            "    .taxonomy-change-grid {",
            "      display: grid;",
            "      grid-template-columns: repeat(3, minmax(0, 1fr)) auto;",
            "      gap: 12px;",
            "      align-items: end;",
            "      margin: 14px 0;",
            "    }",
            "    .taxonomy-change-grid label { display: grid; gap: 6px; font-weight: 700; }",
            "    .taxonomy-change-grid input, .taxonomy-change-grid select {",
            "      width: 100%;",
            "      border: 1px solid var(--line);",
            "      border-radius: 8px;",
            "      padding: 10px 12px;",
            "      background: #fff;",
            "      color: var(--ink);",
            "      font: inherit;",
            "    }",
            "    .taxonomy-change-preview { margin-top: 10px; }",
            "    .button.primary { background: var(--accent); color: #fff; border-color: var(--accent); }",
            "    @media (max-width: 820px) { .designer-grid, .policy-grid, .taxonomy-change-grid { grid-template-columns: 1fr; } }",
        ]
    )
    (report_dir / "taxonomy.html").write_text(page_shell("分类治理", body, extra_css=taxonomy_css), encoding="utf-8")


def render_timeline_item(paper: dict[str, Any]) -> str:
    link = paper["html_path"] or paper["md_path"]
    labels = [
        str(paper.get("line_role") or ""),
        str(paper.get("status") or ""),
        f'I {paper.get("importance")}' if paper.get("importance") else "",
        "code" if paper.get("has_code") else "",
    ]
    flags = "".join(f'<span class="flag">{html.escape(label)}</span>' for label in labels if label)
    taxonomy = [*paper.get("domains", []), *paper.get("tracks", []), *paper.get("problems", [])]
    tags = [*paper.get("topics", []), *paper.get("methods", [])]
    search_text = " ".join(
        str(part)
        for part in [
            paper.get("slug"),
            paper.get("title"),
            paper.get("title_zh"),
            paper.get("title_en"),
            paper.get("arxiv_id"),
            paper.get("research_line"),
            paper.get("line_role"),
            paper.get("status"),
            paper.get("reading_stage"),
            paper.get("review_stage"),
            paper.get("excerpt"),
            *paper.get("authors", []),
            *taxonomy,
            *tags,
        ]
        if part
    ).lower()
    line = str(paper.get("research_line") or "Unassigned")
    line_href = f'lines/{slugify_label(line)}.html' if line != "Unassigned" else ""
    line_html = (
        f'<a href="{html.escape(line_href)}">{html.escape(line)}</a>'
        if line_href
        else html.escape(line)
    )
    return f"""<article class="timeline-item"
  data-search="{html.escape(search_text, quote=True)}"
  data-line="{html.escape(line, quote=True)}"
  data-role="{html.escape(str(paper.get("line_role") or ""), quote=True)}"
  data-status="{html.escape(str(paper.get("status") or ""), quote=True)}"
  data-stage="{html.escape(str(paper.get("reading_stage") or ""), quote=True)}"
  data-review-stage="{html.escape(str(paper.get("review_stage") or ""), quote=True)}"
  data-tracks="{html.escape(attr_tokens(paper.get("tracks", [])), quote=True)}"
  data-code="{"yes" if paper.get("has_code") else "no"}"
  data-importance="{html.escape(str(paper.get("importance") or 0), quote=True)}"
  data-year="{html.escape(str(paper.get("year") or "unknown"), quote=True)}">
  <div class="timeline-dot" aria-hidden="true"></div>
  <div class="timeline-content">
    <h3><a href="{html.escape(link)}">{html.escape(paper["title_zh"] or paper["title"])}</a></h3>
    <div class="meta">{html.escape(str(paper.get("title_en") or ""))}</div>
    <div class="timeline-meta">{line_html}<span>{html.escape(str(paper.get("arxiv_id") or ""))}</span></div>
    <div class="card-flags">{flags}</div>
    <div class="chips">{render_inline_chips([*taxonomy, *tags], 6)}</div>
  </div>
</article>"""


def render_timeline(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
    controls = control_options()
    timeline_controls = {key: value for key, value in controls.items() if key != "shared_views"}
    years = sorted(
        {str(paper.get("year") or "unknown") for paper in papers},
        key=lambda value: int(value) if value.isdigit() else -1,
        reverse=True,
    )
    year_sections = []
    for year in years:
        items = [
            paper
            for paper in papers
            if str(paper.get("year") or "unknown") == year
        ]
        items.sort(
            key=lambda paper: (
                str(paper.get("research_line") or "Unassigned").lower(),
                role_rank(str(paper.get("line_role") or "")),
                -(paper.get("importance") or 0),
                paper["title"],
            )
        )
        year_sections.append(
            f"""<section class="timeline-year" data-year="{html.escape(year, quote=True)}">
  <header class="timeline-year-head"><h2>{html.escape(year)}</h2><span class="timeline-year-count">{len(items)}</span></header>
  <div class="timeline-list">{"".join(render_timeline_item(paper) for paper in items)}</div>
</section>"""
        )

    timeline_css = """
    .timeline-board {
      display: grid;
      gap: 18px;
    }
    .timeline-year {
      display: grid;
      grid-template-columns: 120px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }
    .timeline-year[hidden], .timeline-item[hidden] { display: none; }
    .timeline-year-head {
      position: sticky;
      top: 86px;
      display: grid;
      gap: 8px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .timeline-year-head h2 {
      margin: 0;
      font-size: 28px;
      line-height: 1.1;
    }
    .timeline-year-count {
      color: var(--muted);
      font-weight: 750;
    }
    .timeline-list {
      position: relative;
      display: grid;
      gap: 12px;
      padding-left: 18px;
    }
    .timeline-list::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 4px;
      width: 2px;
      background: var(--line);
    }
    .timeline-item {
      position: relative;
      display: grid;
      grid-template-columns: 18px minmax(0, 1fr);
      gap: 8px;
      min-width: 0;
    }
    .timeline-dot {
      width: 10px;
      height: 10px;
      margin-top: 17px;
      border: 2px solid var(--accent);
      border-radius: 999px;
      background: var(--bg);
      z-index: 1;
    }
    .timeline-content {
      display: grid;
      gap: 7px;
      min-width: 0;
      padding: 13px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .timeline-content h3 {
      margin: 0;
      font-size: 16px;
      line-height: 1.35;
    }
    .timeline-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .timeline-summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .timeline-summary .metric-card strong { font-size: 24px; }
    .active-filters {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      margin: -4px 0 16px;
      color: var(--muted);
      font-size: 13px;
    }
    .active-filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      max-width: 280px;
      min-height: 30px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
      cursor: pointer;
    }
    .active-filter-chip span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .active-filter-chip b {
      color: var(--muted);
      font-weight: 750;
    }
    .active-filter-chip::after {
      content: "x";
      color: var(--muted);
      font-weight: 850;
    }
    @media (max-width: 760px) {
      .timeline-year { grid-template-columns: 1fr; }
      .timeline-year-head { position: static; }
      .timeline-list { padding-left: 0; }
      .timeline-list::before { display: none; }
      .timeline-item { grid-template-columns: 1fr; }
      .timeline-dot { display: none; }
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Research Roadmap</div>
  <h1>研究路线时间轴</h1>
  <p class="lead">按年份浏览论文在不同研究线中的演进，适合在论文数量变多后快速判断一条方向的起点、系统化工作、变体和后续推进。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="board.html">状态看板</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="tags.html">分类总览</a>
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">年份 {len(years)}</span>
    <span class="stat">研究线 {len(taxonomy["research_lines"])}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="timelineSearch" type="search" placeholder="搜索标题、作者、研究线、分类、状态">
    <select id="timelineLine"><option value="">全部研究线</option>{render_topic_options(taxonomy["research_lines"])}</select>
    <select id="timelineTrack"><option value="">全部方向</option>{render_topic_options(taxonomy["tracks"])}</select>
    <select id="timelineRole"><option value="">全部角色</option>{render_topic_options(taxonomy["line_roles"])}</select>
    <select id="timelineWorkflow" aria-label="状态体系"></select>
    <select id="timelineStatus"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="timelineStage"><option value="">阅读阶段</option>{render_topic_options(taxonomy["reading_stages"])}</select>
    <select id="timelineCode"><option value="">代码状态</option><option value="yes">有代码</option><option value="no">无代码</option></select>
    <select id="timelineImportance"><option value="">重要性</option><option value="5">5 星</option><option value="4">4 星及以上</option><option value="3">3 星及以上</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="timelineCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <div class="results-actions">
      <button id="timelineCopyLink" class="button" type="button">复制当前链接</button>
      <button id="timelineReset" class="button" type="button">重置筛选</button>
    </div>
  </div>
  <div class="active-filters" id="timelineActiveFilters" aria-live="polite"></div>
  <div class="timeline-summary">
    <div class="metric-card"><strong>{len(years)}</strong><span>覆盖年份</span></div>
    <div class="metric-card"><strong>{len(taxonomy["research_lines"])}</strong><span>研究线</span></div>
    <div class="metric-card"><strong>{sum(1 for paper in papers if paper.get("has_code"))}</strong><span>有代码论文</span></div>
  </div>
  <div class="timeline-board">{"".join(year_sections) if year_sections else '<div class="empty">还没有论文。</div>'}</div>
</main>
<script>
const timelineItems = Array.from(document.querySelectorAll(".timeline-item"));
const timelineYears = Array.from(document.querySelectorAll(".timeline-year"));
const timelineSearch = document.querySelector("#timelineSearch");
const timelineLine = document.querySelector("#timelineLine");
const timelineTrack = document.querySelector("#timelineTrack");
const timelineRole = document.querySelector("#timelineRole");
const timelineWorkflow = document.querySelector("#timelineWorkflow");
const timelineStatus = document.querySelector("#timelineStatus");
const timelineStage = document.querySelector("#timelineStage");
const timelineCode = document.querySelector("#timelineCode");
const timelineImportance = document.querySelector("#timelineImportance");
const timelineCount = document.querySelector("#timelineCount");
const timelineReset = document.querySelector("#timelineReset");
const timelineCopyLink = document.querySelector("#timelineCopyLink");
const timelineActiveFilters = document.querySelector("#timelineActiveFilters");
const wikiControls = window.PAPER_WIKI.controls || {{}};
const statusWorkflows = wikiControls.status_workflows || {{}};
const activeStatusWorkflow = wikiControls.active_status_workflow || Object.keys(statusWorkflows)[0] || "default";
const fallbackStatusValues = Array.isArray(wikiControls.status) ? wikiControls.status : [];
const fallbackStageValues = Array.isArray(wikiControls.reading_stage) ? wikiControls.reading_stage : [];
const observedStatusValues = Array.from(new Set(timelineItems.map(item => item.dataset.status).filter(Boolean)));
const observedStageValues = Array.from(new Set(timelineItems.map(item => item.dataset.stage).filter(Boolean)));
const timelineControls = [timelineSearch, timelineLine, timelineTrack, timelineRole, timelineWorkflow, timelineStatus, timelineStage, timelineCode, timelineImportance];
const timelineStateControls = [
  ["q", timelineSearch],
  ["line", timelineLine],
  ["track", timelineTrack],
  ["role", timelineRole],
  ["workflow", timelineWorkflow],
  ["status", timelineStatus],
  ["stage", timelineStage],
  ["code", timelineCode],
  ["importance", timelineImportance],
];
const timelineControlsByKey = new Map(timelineStateControls);
const timelineFilterLabels = {{
  q: "搜索",
  line: "研究线",
  track: "方向",
  role: "角色",
  workflow: "状态体系",
  status: "状态",
  stage: "阅读阶段",
  code: "代码",
  importance: "重要性",
}};

function timelineTokens(value) {{
  return String(value || "").split("|").filter(Boolean);
}}

function orderedUnique(values) {{
  return Array.from(new Set(values.map(value => String(value || "").trim()).filter(Boolean)));
}}

function workflowValuesFor(name, key, fallbackValues, observedValues) {{
  const workflow = statusWorkflows[name] || {{}};
  const configured = Array.isArray(workflow[key]) ? workflow[key] : fallbackValues;
  return orderedUnique([...configured, ...observedValues]);
}}

function timelineValueCount(datasetKey, value) {{
  return timelineItems.filter(item => item.dataset[datasetKey] === value).length;
}}

function replaceWorkflowOptions(select, placeholder, values, datasetKey) {{
  const current = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  values.forEach(value => {{
    select.appendChild(new Option(`${{value}} (${{timelineValueCount(datasetKey, value)}})`, value));
  }});
  select.value = values.includes(current) ? current : "";
}}

function populateTimelineWorkflowOptions() {{
  const names = Object.keys(statusWorkflows);
  const workflowNames = names.length ? names : [activeStatusWorkflow];
  timelineWorkflow.replaceChildren(...workflowNames.map(name => {{
    const label = name === activeStatusWorkflow ? `${{name}} (默认)` : name;
    return new Option(label, name);
  }}));
  timelineWorkflow.value = workflowNames.includes(activeStatusWorkflow) ? activeStatusWorkflow : workflowNames[0] || "";
}}

function applyTimelineWorkflow() {{
  const workflowName = timelineWorkflow.value || activeStatusWorkflow;
  replaceWorkflowOptions(
    timelineStatus,
    "全部状态",
    workflowValuesFor(workflowName, "status_values", fallbackStatusValues, observedStatusValues),
    "status"
  );
  replaceWorkflowOptions(
    timelineStage,
    "阅读阶段",
    workflowValuesFor(workflowName, "reading_stage_values", fallbackStageValues, observedStageValues),
    "stage"
  );
}}

function timelineDefaultValue(key) {{
  return key === "workflow" ? activeStatusWorkflow : "";
}}

function timelineState() {{
  const state = {{}};
  timelineStateControls.forEach(([key, control]) => {{
    const defaultValue = timelineDefaultValue(key);
    if (control.value && control.value !== defaultValue) state[key] = control.value;
  }});
  return state;
}}

function timelineCleanOptionLabel(label) {{
  return String(label || "").replace(/\\s\\(\\d+\\)$/, "").replace(/\\s\\(默认\\)$/, "");
}}

function timelineDisplayValue(key, control) {{
  if (key === "q") return control.value.trim();
  const option = control.options && control.selectedIndex >= 0 ? control.options[control.selectedIndex] : null;
  return timelineCleanOptionLabel(option ? option.textContent : control.value);
}}

function renderTimelineActiveFilters() {{
  const state = timelineState();
  const entries = Object.entries(state).filter(([key]) => timelineControlsByKey.has(key));
  timelineActiveFilters.replaceChildren();
  if (!entries.length) {{
    timelineActiveFilters.textContent = "未设置筛选条件";
    return;
  }}
  const prefix = document.createElement("span");
  prefix.textContent = "当前筛选";
  timelineActiveFilters.appendChild(prefix);
  entries.forEach(([key]) => {{
    const control = timelineControlsByKey.get(key);
    const chip = document.createElement("button");
    chip.className = "active-filter-chip";
    chip.type = "button";
    chip.dataset.filterKey = key;
    chip.title = `移除${{timelineFilterLabels[key] || key}}筛选`;
    const name = document.createElement("b");
    name.textContent = timelineFilterLabels[key] || key;
    const value = document.createElement("span");
    value.textContent = timelineDisplayValue(key, control);
    chip.append(name, value);
    timelineActiveFilters.appendChild(chip);
  }});
}}

function clearTimelineFilter(key) {{
  const control = timelineControlsByKey.get(key);
  if (!control) return;
  control.value = timelineDefaultValue(key);
  if (key === "workflow") applyTimelineWorkflow();
  renderTimeline();
}}

function writeTimelineStateToUrl() {{
  const params = new URLSearchParams(timelineState());
  const query = params.toString();
  window.history.replaceState(null, "", query ? `${{location.pathname}}?${{query}}` : location.pathname);
}}

function readTimelineStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  timelineStateControls.forEach(([key, control]) => {{
    if (["status", "stage"].includes(key)) return;
    control.value = params.has(key) ? params.get(key) : timelineDefaultValue(key);
  }});
  applyTimelineWorkflow();
  timelineStatus.value = params.has("status") ? params.get("status") : "";
  timelineStage.value = params.has("stage") ? params.get("stage") : "";
}}

function timelineViewUrl() {{
  const url = new URL(window.location.href);
  url.search = new URLSearchParams(timelineState()).toString();
  url.hash = "";
  return url.toString();
}}

async function copyTimelineLink() {{
  const text = timelineViewUrl();
  try {{
    await navigator.clipboard.writeText(text);
    timelineCopyLink.textContent = "已复制";
    setTimeout(() => timelineCopyLink.textContent = "复制当前链接", 1400);
  }} catch {{
    window.prompt("复制当前链接", text);
  }}
}}

function renderTimeline() {{
  const q = timelineSearch.value.trim().toLowerCase();
  const minImportance = Number(timelineImportance.value || 0);
  let visible = 0;
  timelineItems.forEach(item => {{
    const hit = (!q || item.dataset.search.includes(q))
      && (!timelineLine.value || item.dataset.line === timelineLine.value)
      && (!timelineTrack.value || timelineTokens(item.dataset.tracks).includes(timelineTrack.value))
      && (!timelineRole.value || item.dataset.role === timelineRole.value)
      && (!timelineStatus.value || item.dataset.status === timelineStatus.value)
      && (!timelineStage.value || item.dataset.stage === timelineStage.value)
      && (!timelineCode.value || item.dataset.code === timelineCode.value)
      && (!minImportance || Number(item.dataset.importance || 0) >= minImportance);
    item.hidden = !hit;
    if (hit) visible += 1;
  }});
  timelineYears.forEach(section => {{
    const count = Array.from(section.querySelectorAll(".timeline-item")).filter(item => !item.hidden).length;
    section.hidden = count === 0;
    section.querySelector(".timeline-year-count").textContent = count;
  }});
  timelineCount.textContent = `显示 ${{visible}} / ${{timelineItems.length}} 篇`;
  renderTimelineActiveFilters();
  writeTimelineStateToUrl();
}}

timelineControls.forEach(control => control.addEventListener("input", () => {{
  if (control === timelineWorkflow) applyTimelineWorkflow();
  renderTimeline();
}}));
timelineReset.addEventListener("click", () => {{
  timelineControls.forEach(control => {{
    control.value = "";
  }});
  timelineWorkflow.value = activeStatusWorkflow;
  applyTimelineWorkflow();
  renderTimeline();
}});
timelineCopyLink.addEventListener("click", copyTimelineLink);
timelineActiveFilters.addEventListener("click", event => {{
  const target = event.target instanceof Element ? event.target.closest("[data-filter-key]") : null;
  if (!target) return;
  clearTimelineFilter(target.dataset.filterKey);
}});
populateTimelineWorkflowOptions();
readTimelineStateFromUrl();
renderTimeline();
</script>
"""
    (report_dir / "timeline.html").write_text(
        page_shell("研究路线时间轴", body, {"controls": timeline_controls}, timeline_css),
        encoding="utf-8",
    )


def render_matrix(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    controls = control_options()
    matrix_controls = {key: value for key, value in controls.items() if key != "shared_views"}
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for paper in papers:
        line = str(paper.get("research_line") or "Unassigned")
        year = str(paper.get("year") or "unknown")
        grouped[line][year].append(paper)

    years = sorted(
        {str(paper.get("year") or "unknown") for paper in papers},
        key=lambda value: int(value) if value.isdigit() else -1,
        reverse=True,
    )
    lines = sorted(
        grouped,
        key=lambda line: (-sum(len(items) for items in grouped[line].values()), line == "Unassigned", line.lower()),
    )
    max_count = max((len(items) for by_year in grouped.values() for items in by_year.values()), default=0)

    def cell_intensity(count: int) -> int:
        if not count or not max_count:
            return 0
        return max(1, min(5, round(count * 5 / max_count)))

    rows = []
    for line in lines:
        line_items = [paper for items in grouped[line].values() for paper in items]
        tracks = attr_tokens(sorted({track for paper in line_items for track in paper.get("tracks", [])}))
        statuses = attr_tokens(sorted({str(paper.get("status") or "") for paper in line_items if paper.get("status")}))
        max_importance = max((int(paper.get("importance") or 0) for paper in line_items), default=0)
        cells = []
        for year in years:
            items = grouped[line].get(year, [])
            count = len(items)
            titles = "; ".join(str(paper.get("title_zh") or paper.get("title") or paper["slug"]) for paper in items[:4])
            cells.append(
                f"""<td>
  <button class="matrix-cell heat-{cell_intensity(count)}" type="button"
    data-line="{html.escape(line, quote=True)}"
    data-year="{html.escape(year, quote=True)}"
    data-count="{count}"
    aria-label="{html.escape(f'{line} {year} {count} 篇', quote=True)}">
    <strong>{count if count else ""}</strong>
    <span>{html.escape(titles)}</span>
  </button>
</td>"""
            )
        rows.append(
            f"""<tr class="matrix-row"
  data-line="{html.escape(line, quote=True)}"
  data-search="{html.escape(line.lower(), quote=True)}"
  data-tracks="{html.escape(tracks, quote=True)}"
  data-statuses="{html.escape(statuses, quote=True)}"
  data-importance="{max_importance}">
  <th scope="row"><span>{html.escape(line)}</span><small>{len(line_items)} 篇</small></th>
  {"".join(cells)}
</tr>"""
        )

    matrix_items = []
    for paper in papers:
        matrix_items.append(
            {
                "slug": paper["slug"],
                "title": paper.get("title") or "",
                "title_zh": paper.get("title_zh") or "",
                "title_en": paper.get("title_en") or "",
                "line": paper.get("research_line") or "Unassigned",
                "year": str(paper.get("year") or "unknown"),
                "role": paper.get("line_role") or "",
                "status": paper.get("status") or "",
                "reading_stage": paper.get("reading_stage") or "",
                "importance": paper.get("importance") or "",
                "has_code": bool(paper.get("has_code")),
                "href": paper.get("html_path") or paper.get("md_path") or "",
                "topics": paper.get("topics", [])[:4],
                "methods": paper.get("methods", [])[:4],
            }
        )

    taxonomy = taxonomy_counts(papers)
    header_years = "".join(f"<th>{html.escape(year)}</th>" for year in years)
    matrix_css = """
    .matrix-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
      gap: 16px;
      align-items: start;
    }
    .matrix-table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
    }
    .research-matrix {
      width: 100%;
      min-width: 760px;
      border-collapse: collapse;
    }
    .research-matrix th,
    .research-matrix td {
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 8px;
      vertical-align: middle;
    }
    .research-matrix thead th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: #f0ebe1;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }
    .research-matrix tbody th {
      position: sticky;
      left: 0;
      z-index: 1;
      width: 220px;
      background: var(--panel);
      text-align: left;
    }
    .research-matrix tbody th span {
      display: block;
      line-height: 1.3;
    }
    .research-matrix tbody th small {
      color: var(--muted);
      font-weight: 650;
    }
    .research-matrix tr[hidden] { display: none; }
    .matrix-cell {
      display: grid;
      place-items: center;
      gap: 3px;
      width: 100%;
      min-width: 76px;
      min-height: 54px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #faf7f0;
      color: var(--ink);
      cursor: pointer;
      font: inherit;
    }
    .matrix-cell strong {
      font-size: 18px;
      line-height: 1;
    }
    .matrix-cell span {
      max-width: 120px;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.25;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .matrix-cell.heat-0 { opacity: .35; }
    .matrix-cell.heat-1 { background: #edf3f1; }
    .matrix-cell.heat-2 { background: #d9ebe8; }
    .matrix-cell.heat-3 { background: #b9d9d6; }
    .matrix-cell.heat-4 { background: #86bbb7; }
    .matrix-cell.heat-5 { background: #4f9691; color: #fff; }
    .matrix-cell.heat-5 span { color: #eef8f6; }
    .matrix-cell.active {
      outline: 3px solid color-mix(in srgb, var(--accent) 48%, transparent);
      outline-offset: 2px;
    }
    .matrix-detail {
      position: sticky;
      top: 86px;
      display: grid;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .matrix-detail h2 {
      margin: 0;
      font-size: 20px;
      line-height: 1.25;
    }
    .matrix-detail-list {
      display: grid;
      gap: 10px;
    }
    .matrix-paper {
      display: grid;
      gap: 6px;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fffaf2;
    }
    .matrix-paper h3 {
      margin: 0;
      font-size: 15px;
      line-height: 1.35;
    }
    .active-filters {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      min-height: 34px;
      margin: -4px 0 16px;
      color: var(--muted);
      font-size: 13px;
    }
    .active-filter-chip {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      max-width: 280px;
      min-height: 30px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--chip);
      color: var(--ink);
      padding: 0 10px;
      font: inherit;
      cursor: pointer;
    }
    .active-filter-chip span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .active-filter-chip b {
      color: var(--muted);
      font-weight: 750;
    }
    .active-filter-chip::after {
      content: "x";
      color: var(--muted);
      font-weight: 850;
    }
    @media (max-width: 980px) {
      .matrix-layout { grid-template-columns: 1fr; }
      .matrix-detail { position: static; }
    }
    """
    data = {"papers": matrix_items, "controls": matrix_controls}
    body = f"""
<header class="shell">
  <div class="eyebrow">Research Matrix</div>
  <h1>研究线年份矩阵</h1>
  <p class="lead">用矩阵方式查看每条研究线在不同年份的论文覆盖，快速发现高密度阶段、空档年份和需要补读的方向。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">年份 {len(years)}</span>
    <span class="stat">研究线 {len(lines)}</span>
  </div>
</header>
<div class="toolbar">
  <div class="shell controls">
    <input id="matrixSearch" type="search" placeholder="搜索研究线">
    <select id="matrixTrack"><option value="">全部方向</option>{render_topic_options(taxonomy["tracks"])}</select>
    <select id="matrixWorkflow" aria-label="状态体系"></select>
    <select id="matrixStatus"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="matrixImportance"><option value="">重要性</option><option value="5">含 5 星</option><option value="4">含 4 星及以上</option><option value="3">含 3 星及以上</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="matrixCount">显示 {len(lines)} / {len(lines)} 条研究线</strong>
    <div class="results-actions">
      <button id="matrixCopyLink" class="button" type="button">复制当前链接</button>
      <button id="matrixReset" class="button" type="button">重置筛选</button>
    </div>
  </div>
  <div class="active-filters" id="matrixActiveFilters" aria-live="polite"></div>
  <div class="matrix-layout">
    <div class="matrix-table-wrap">
      <table class="research-matrix">
        <thead><tr><th>研究线</th>{header_years}</tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </div>
    <aside class="matrix-detail" aria-live="polite">
      <h2 id="matrixDetailTitle">选择一个格子</h2>
      <p id="matrixDetailMeta" class="meta">点击矩阵中的数字，查看该研究线该年份的论文。</p>
      <div id="matrixDetailList" class="matrix-detail-list"></div>
    </aside>
  </div>
</main>
<script>
const matrixRows = Array.from(document.querySelectorAll(".matrix-row"));
const matrixCells = Array.from(document.querySelectorAll(".matrix-cell"));
const matrixSearch = document.querySelector("#matrixSearch");
const matrixTrack = document.querySelector("#matrixTrack");
const matrixWorkflow = document.querySelector("#matrixWorkflow");
const matrixStatus = document.querySelector("#matrixStatus");
const matrixImportance = document.querySelector("#matrixImportance");
const matrixReset = document.querySelector("#matrixReset");
const matrixCopyLink = document.querySelector("#matrixCopyLink");
const matrixActiveFilters = document.querySelector("#matrixActiveFilters");
const matrixCount = document.querySelector("#matrixCount");
const matrixDetailTitle = document.querySelector("#matrixDetailTitle");
const matrixDetailMeta = document.querySelector("#matrixDetailMeta");
const matrixDetailList = document.querySelector("#matrixDetailList");
const matrixPapers = window.PAPER_WIKI.papers || [];
const matrixControls = window.PAPER_WIKI.controls || {{}};
const matrixWorkflows = matrixControls.status_workflows || {{}};
const activeMatrixWorkflow = matrixControls.active_status_workflow || Object.keys(matrixWorkflows)[0] || "default";
const fallbackMatrixStatuses = Array.isArray(matrixControls.status) ? matrixControls.status : [];
const observedMatrixStatuses = Array.from(new Set(matrixPapers.map(paper => paper.status).filter(Boolean)));
const matrixStateControls = [
  ["q", matrixSearch],
  ["track", matrixTrack],
  ["workflow", matrixWorkflow],
  ["status", matrixStatus],
  ["importance", matrixImportance],
];
const matrixControlsByKey = new Map(matrixStateControls);
const matrixFilterLabels = {{
  q: "搜索",
  track: "方向",
  workflow: "状态体系",
  status: "状态",
  importance: "重要性",
}};

function matrixTokens(value) {{
  return String(value || "").split("|").filter(Boolean);
}}

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
}}

function orderedMatrixValues(values) {{
  return Array.from(new Set(values.map(value => String(value || "").trim()).filter(Boolean)));
}}

function matrixWorkflowValues(name) {{
  const workflow = matrixWorkflows[name] || {{}};
  const configured = Array.isArray(workflow.status_values) ? workflow.status_values : fallbackMatrixStatuses;
  return orderedMatrixValues([...configured, ...observedMatrixStatuses]);
}}

function populateMatrixWorkflowOptions() {{
  const names = Object.keys(matrixWorkflows);
  const workflowNames = names.length ? names : [activeMatrixWorkflow];
  matrixWorkflow.replaceChildren(...workflowNames.map(name => {{
    const label = name === activeMatrixWorkflow ? `${{name}} (默认)` : name;
    return new Option(label, name);
  }}));
  matrixWorkflow.value = workflowNames.includes(activeMatrixWorkflow) ? activeMatrixWorkflow : workflowNames[0] || "";
}}

function applyMatrixWorkflow() {{
  const current = matrixStatus.value;
  const values = matrixWorkflowValues(matrixWorkflow.value || activeMatrixWorkflow);
  matrixStatus.replaceChildren(new Option("全部状态", ""));
  values.forEach(value => {{
    const count = matrixPapers.filter(paper => paper.status === value).length;
    matrixStatus.appendChild(new Option(`${{value}} (${{count}})`, value));
  }});
  matrixStatus.value = values.includes(current) ? current : "";
}}

function matrixDefaultValue(key) {{
  return key === "workflow" ? activeMatrixWorkflow : "";
}}

function matrixState() {{
  const state = {{}};
  matrixStateControls.forEach(([key, control]) => {{
    const defaultValue = matrixDefaultValue(key);
    if (control.value && control.value !== defaultValue) state[key] = control.value;
  }});
  return state;
}}

function matrixCleanOptionLabel(label) {{
  return String(label || "").replace(/\\s\\(\\d+\\)$/, "").replace(/\\s\\(默认\\)$/, "");
}}

function matrixDisplayValue(key, control) {{
  if (key === "q") return control.value.trim();
  const option = control.options && control.selectedIndex >= 0 ? control.options[control.selectedIndex] : null;
  return matrixCleanOptionLabel(option ? option.textContent : control.value);
}}

function renderMatrixActiveFilters() {{
  const state = matrixState();
  const entries = Object.entries(state).filter(([key]) => matrixControlsByKey.has(key));
  matrixActiveFilters.replaceChildren();
  if (!entries.length) {{
    matrixActiveFilters.textContent = "未设置筛选条件";
    return;
  }}
  const prefix = document.createElement("span");
  prefix.textContent = "当前筛选";
  matrixActiveFilters.appendChild(prefix);
  entries.forEach(([key]) => {{
    const control = matrixControlsByKey.get(key);
    const chip = document.createElement("button");
    chip.className = "active-filter-chip";
    chip.type = "button";
    chip.dataset.filterKey = key;
    chip.title = `移除${{matrixFilterLabels[key] || key}}筛选`;
    const name = document.createElement("b");
    name.textContent = matrixFilterLabels[key] || key;
    const value = document.createElement("span");
    value.textContent = matrixDisplayValue(key, control);
    chip.append(name, value);
    matrixActiveFilters.appendChild(chip);
  }});
}}

function clearMatrixFilter(key) {{
  const control = matrixControlsByKey.get(key);
  if (!control) return;
  control.value = matrixDefaultValue(key);
  if (key === "workflow") applyMatrixWorkflow();
  renderMatrixFilters();
}}

function writeMatrixStateToUrl() {{
  const params = new URLSearchParams(matrixState());
  const query = params.toString();
  window.history.replaceState(null, "", query ? `${{location.pathname}}?${{query}}` : location.pathname);
}}

function readMatrixStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  matrixStateControls.forEach(([key, control]) => {{
    if (key === "status") return;
    control.value = params.has(key) ? params.get(key) : matrixDefaultValue(key);
  }});
  applyMatrixWorkflow();
  matrixStatus.value = params.has("status") ? params.get("status") : "";
}}

function matrixViewUrl() {{
  const url = new URL(window.location.href);
  url.search = new URLSearchParams(matrixState()).toString();
  url.hash = "";
  return url.toString();
}}

async function copyMatrixLink() {{
  const text = matrixViewUrl();
  try {{
    await navigator.clipboard.writeText(text);
    matrixCopyLink.textContent = "已复制";
    setTimeout(() => matrixCopyLink.textContent = "复制当前链接", 1400);
  }} catch {{
    window.prompt("复制当前链接", text);
  }}
}}

function renderMatrixFilters() {{
  const q = matrixSearch.value.trim().toLowerCase();
  const minImportance = Number(matrixImportance.value || 0);
  let visible = 0;
  matrixRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!matrixTrack.value || matrixTokens(row.dataset.tracks).includes(matrixTrack.value))
      && (!matrixStatus.value || matrixTokens(row.dataset.statuses).includes(matrixStatus.value))
      && (!minImportance || Number(row.dataset.importance || 0) >= minImportance);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  matrixCount.textContent = `显示 ${{visible}} / ${{matrixRows.length}} 条研究线`;
  renderMatrixActiveFilters();
  writeMatrixStateToUrl();
}}

function renderMatrixDetail(line, year) {{
  matrixCells.forEach(cell => cell.classList.toggle("active", cell.dataset.line === line && cell.dataset.year === year));
  const papers = matrixPapers.filter(paper => paper.line === line && paper.year === year);
  matrixDetailTitle.textContent = `${{line}} / ${{year}}`;
  matrixDetailMeta.textContent = `${{papers.length}} 篇论文`;
  if (!papers.length) {{
    matrixDetailList.innerHTML = '<div class="empty">这个格子还没有论文。</div>';
    return;
  }}
  matrixDetailList.innerHTML = papers.map(paper => {{
    const labels = [paper.role, paper.status, paper.reading_stage, paper.importance ? `I ${{paper.importance}}` : "", paper.has_code ? "code" : ""].filter(Boolean);
    const chips = [...(paper.topics || []), ...(paper.methods || [])].slice(0, 6);
    return `<article class="matrix-paper">
      <h3><a href="${{esc(paper.href)}}">${{esc(paper.title_zh || paper.title)}}</a></h3>
      <div class="meta">${{esc(paper.title_en || "")}}</div>
      <div class="card-flags">${{labels.map(label => `<span class="flag">${{esc(label)}}</span>`).join("")}}</div>
      <div class="chips">${{chips.map(chip => `<span class="chip">${{esc(chip)}}</span>`).join("")}}</div>
    </article>`;
  }}).join("");
}}

[matrixSearch, matrixTrack, matrixWorkflow, matrixStatus, matrixImportance].forEach(control => control.addEventListener("input", () => {{
  if (control === matrixWorkflow) applyMatrixWorkflow();
  renderMatrixFilters();
}}));
matrixReset.addEventListener("click", () => {{
  [matrixSearch, matrixTrack, matrixStatus, matrixImportance].forEach(control => {{
    control.value = "";
  }});
  matrixWorkflow.value = activeMatrixWorkflow;
  applyMatrixWorkflow();
  renderMatrixFilters();
}});
matrixCopyLink.addEventListener("click", copyMatrixLink);
matrixActiveFilters.addEventListener("click", event => {{
  const target = event.target instanceof Element ? event.target.closest("[data-filter-key]") : null;
  if (!target) return;
  clearMatrixFilter(target.dataset.filterKey);
}});
matrixCells.forEach(cell => cell.addEventListener("click", () => renderMatrixDetail(cell.dataset.line, cell.dataset.year)));
populateMatrixWorkflowOptions();
readMatrixStateFromUrl();
renderMatrixFilters();
const firstNonEmpty = matrixCells.find(cell => Number(cell.dataset.count || 0) > 0);
if (firstNonEmpty) renderMatrixDetail(firstNonEmpty.dataset.line, firstNonEmpty.dataset.year);
</script>
"""
    (report_dir / "matrix.html").write_text(page_shell("研究线年份矩阵", body, data, matrix_css), encoding="utf-8")


def gaps_paper_summary(paper: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": paper["slug"],
        "title": paper.get("title") or paper["slug"],
        "title_zh": paper.get("title_zh") or paper.get("title") or paper["slug"],
        "href": paper_href(paper),
        "research_line": paper.get("research_line") or "Unassigned",
        "status": paper.get("status") or "",
        "importance": paper.get("importance") or "",
    }


def build_gaps_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    current_year = dt.date.today().year
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    taxonomy_load_by_slug = {item["slug"]: item for item in quality.get("taxonomy_load", [])}
    paper_by_slug = {paper["slug"]: paper for paper in papers}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)

    lines = []
    all_actions: list[dict[str, Any]] = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name == "Unassigned", name.lower())):
        items = grouped[line]
        roles = {str(paper.get("line_role") or "") for paper in items if paper.get("line_role")}
        missing_roles = [role for role in ROADMAP_RECOMMENDED_ROLES if role not in roles]
        years = sorted({int(paper["year"]) for paper in items if isinstance(paper.get("year"), int)})
        latest_year = max(years) if years else None
        stale_years = current_year - latest_year if latest_year else None
        missing_taxonomy = [
            paper
            for paper in items
            if not paper.get("domains")
            or not paper.get("tracks")
            or not paper.get("problems")
            or not paper.get("topics")
            or not paper.get("methods")
            or not paper.get("line_role")
        ]
        no_review = [paper for paper in items if not paper.get("next_review")]
        no_code = [paper for paper in items if not paper.get("has_code")]
        taxonomy_load = [paper for paper in items if paper["slug"] in taxonomy_load_by_slug]
        high_priority = sorted(
            [paper for paper in items if int(paper.get("importance") or 0) >= 5],
            key=lambda paper: (not paper.get("next_review"), paper["title"]),
        )
        score = 100
        score -= len(missing_roles) * 10
        score -= min(25, len(missing_taxonomy) * 8)
        score -= min(15, len(taxonomy_load) * 5)
        score -= min(20, len(no_review) * 5)
        score -= min(15, len(no_code) * 4)
        if stale_years is None:
            score -= 12
        elif stale_years >= 2:
            score -= min(20, stale_years * 5)
        score = max(0, score)

        actions = []
        if missing_roles:
            actions.append(f"补角色：{', '.join(missing_roles)}")
        if stale_years is None:
            actions.append("补年份信息")
        elif stale_years >= 2:
            actions.append(f"检索 {latest_year + 1}-{current_year} 后续工作")
        if no_review:
            actions.append(f"补复习计划 {len(no_review)} 篇")
        if missing_taxonomy:
            actions.append(f"补 taxonomy {len(missing_taxonomy)} 篇")
        if taxonomy_load:
            actions.append(f"审分类粒度 {len(taxonomy_load)} 篇")
        if no_code:
            actions.append(f"补代码观察 {len(no_code)} 篇")
        if not actions:
            actions.append("保持观察")
        line_href = f"lines/{slugify_label(line)}.html" if line != "Unassigned" else "library.html?line=Unassigned"
        action_items = []
        for action in actions[:4]:
            priority = 100 - score
            action_item = {
                "line": line,
                "priority": priority,
                "type": "maintain" if action == "保持观察" else "gap",
                "label": action,
                "latest_year": latest_year,
                "href": page_query_href("library.html", line=line),
                "slugs": [paper["slug"] for paper in items],
            }
            action_items.append(action_item)
            all_actions.append(action_item)
        lines.append(
            {
                "id": slugify_label(line),
                "line": line,
                "href": line_href,
                "count": len(items),
                "score": score,
                "latest_year": latest_year,
                "stale_years": stale_years,
                "missing_roles": missing_roles,
                "missing_taxonomy_slugs": [paper["slug"] for paper in missing_taxonomy],
                "taxonomy_load_slugs": [paper["slug"] for paper in taxonomy_load],
                "no_review_slugs": [paper["slug"] for paper in no_review],
                "no_code_slugs": [paper["slug"] for paper in no_code],
                "high_priority_papers": [gaps_paper_summary(paper) for paper in high_priority[:6]],
                "actions": action_items,
            }
        )

    def queue_summaries(slugs: list[str]) -> list[dict[str, Any]]:
        return [gaps_paper_summary(paper_by_slug[slug]) for slug in slugs if slug in paper_by_slug]

    queues = {
        "needs_review_plan": queue_summaries(list(review["queues"].get("needs_plan", []))),
        "missing_taxonomy": queue_summaries(list(quality["queues"].get("missing_required_metadata", []))),
        "taxonomy_sparse": queue_summaries(list(quality["queues"].get("taxonomy_sparse", []))),
        "taxonomy_dense": queue_summaries(list(quality["queues"].get("taxonomy_dense", []))),
        "no_code_observation": queue_summaries(list(quality["queues"].get("no_code_observation", []))),
    }
    actions_sorted = sorted(all_actions, key=lambda item: (-int(item["priority"]), item["line"], item["label"]))
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "line_count": len(lines),
        "action_count": len(all_actions),
        "recommended_roles": ROADMAP_RECOMMENDED_ROLES,
        "summary": {
            "avg_score": round(sum(int(line["score"]) for line in lines) / len(lines), 1) if lines else 100,
            "low_score_lines": sum(1 for line in lines if int(line["score"]) < 70),
            "missing_role_lines": sum(1 for line in lines if line["missing_roles"]),
            "missing_taxonomy": sum(len(line["missing_taxonomy_slugs"]) for line in lines),
            "taxonomy_load": sum(len(line["taxonomy_load_slugs"]) for line in lines),
            "needs_review_plan": len(queues["needs_review_plan"]),
            "no_code_observation": len(queues["no_code_observation"]),
        },
        "lines": lines,
        "actions": actions_sorted,
        "queues": queues,
        "links": {
            "html": "gaps.html",
            "dashboard": "dashboard.html",
            "collections": "collections.html",
            "related": "related.html",
            "library": "library.html",
            "matrix": "matrix.html",
            "timeline": "timeline.html",
            "taxonomy": "taxonomy.html",
            "review": "review.html",
        },
    }


def write_gaps_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_gaps_payload(papers)
    (report_dir / "gaps.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_gaps(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_gaps_payload(papers)

    def queue_item(paper: dict[str, Any], reason: str) -> str:
        labels = [
            str(paper.get("research_line") or "Unassigned"),
            str(paper.get("status") or ""),
            f'I {paper.get("importance")}' if paper.get("importance") else "",
            reason,
        ]
        flags = "".join(f'<span class="flag">{html.escape(label)}</span>' for label in labels if label)
        return (
            f'<li><a href="{html.escape(str(paper.get("href") or ""))}">{html.escape(str(paper.get("title_zh") or paper.get("title") or paper.get("slug") or ""))}</a>'
            f'<div class="card-flags">{flags}</div></li>'
        )

    line_rows = []
    line_cards = []
    for line in payload["lines"]:
        actions = [str(action.get("label") or "") for action in line.get("actions", [])]
        line_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(str(line["href"]))}">{html.escape(str(line["line"]))}</a></td>'
            f"<td>{int(line['count'])}</td>"
            f"<td>{int(line['score'])}</td>"
            f"<td>{html.escape(str(line.get('latest_year') or 'unknown'))}</td>"
            f"<td>{html.escape(', '.join(line.get('missing_roles', [])) or '-')}</td>"
            f"<td>{len(line.get('missing_taxonomy_slugs', []))}</td>"
            f"<td>{len(line.get('taxonomy_load_slugs', []))}</td>"
            f"<td>{len(line.get('no_review_slugs', []))}</td>"
            f"<td>{len(line.get('no_code_slugs', []))}</td>"
            f"<td>{html.escape('; '.join(actions[:3]))}</td>"
            "</tr>"
        )
        chip_html = "".join(f'<span class="chip">{html.escape(action)}</span>' for action in actions[:4])
        paper_links = "".join(queue_item(paper, "重点") for paper in line.get("high_priority_papers", [])[:3])
        if not paper_links:
            paper_links = '<li class="meta">暂无 5 星论文。</li>'
        line_cards.append(
            f"""<section class="gap-card" data-score="{int(line['score'])}">
  <header><h2><a href="{html.escape(str(line['href']))}">{html.escape(str(line['line']))}</a></h2><strong>{int(line['score'])}</strong></header>
  <div class="meta">论文 {int(line['count'])} · 最新 {html.escape(str(line.get('latest_year') or 'unknown'))}</div>
  <div class="chips">{chip_html}</div>
  <ol class="queue-list">{paper_links}</ol>
</section>"""
        )

    action_rows = "".join(
        "<tr>"
        f"<td>{int(action.get('priority') or 0)}</td>"
        f'<td><a href="{html.escape(str(action.get("href") or ""))}">{html.escape(str(action.get("line") or ""))}</a></td>'
        f"<td>{html.escape(str(action.get('label') or ''))}</td>"
        f"<td>{html.escape(str(action.get('latest_year') or 'unknown'))}</td>"
        "</tr>"
        for action in payload["actions"][:24]
    )
    action_table = (
        '<table class="data-table"><thead><tr><th>优先级</th><th>研究线</th><th>建议动作</th><th>最新年份</th></tr></thead>'
        f"<tbody>{action_rows}</tbody></table>"
        if action_rows
        else '<div class="empty">暂无建议动作。</div>'
    )
    line_table = (
        '<table class="data-table"><thead><tr><th>研究线</th><th>论文</th><th>健康分</th><th>最新年份</th><th>缺角色</th><th>缺分类</th><th>粒度提示</th><th>缺复习</th><th>缺代码</th><th>下一步</th></tr></thead>'
        f"<tbody>{''.join(line_rows)}</tbody></table>"
        if line_rows
        else '<div class="empty">还没有研究线。</div>'
    )

    queue_blocks = [
        ("需建复习计划", payload["queues"]["needs_review_plan"], "review"),
        ("待补分类", payload["queues"]["missing_taxonomy"], "taxonomy"),
        ("分类偏薄", payload["queues"]["taxonomy_sparse"], "sparse"),
        ("分类过密", payload["queues"]["taxonomy_dense"], "dense"),
        ("缺代码观察", payload["queues"]["no_code_observation"], "code"),
    ]

    def render_queue(items: list[dict[str, Any]], reason: str) -> str:
        if not items:
            return '<li class="meta">暂无。</li>'
        return "".join(queue_item(paper, reason) for paper in items[:8])

    queue_html = "".join(
        f'<section class="role-section"><h2>{html.escape(title)} <span class="meta">{len(items)}</span></h2>'
        f'<ol class="queue-list">{render_queue(items, reason)}</ol></section>'
        for title, items, reason in queue_blocks
    )

    gaps_css = """
    .gap-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }
    .gap-card {
      display: grid;
      gap: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 16px;
    }
    .gap-card header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      padding: 0;
    }
    .gap-card h2 {
      margin: 0;
      font-size: 18px;
      line-height: 1.3;
    }
    .gap-card header strong {
      min-width: 44px;
      text-align: center;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #edf3f1;
      padding: 4px 8px;
      color: var(--accent);
    }
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Research Gap Analysis</div>
  <h1>研究缺口与下一步行动</h1>
  <p class="lead">从研究线角度自动诊断缺角色、缺分类、分类粒度、缺复习计划、缺代码观察和时间覆盖空档，把大量论文库变成可持续维护的行动队列。</p>
  <div class="stats">
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="gaps.json">Gaps JSON</a>
    <span class="stat">论文 {payload["count"]}</span>
    <span class="stat">研究线 {payload["line_count"]}</span>
    <span class="stat">建议 {payload["action_count"]}</span>
  </div>
</header>
<main class="shell">
  <section>
    <h2 class="section-title">下一步行动</h2>
    <div class="table-wrap">{action_table}</div>
  </section>
  <section>
    <h2 class="section-title">研究线健康卡片</h2>
    <div class="gap-grid">{"".join(line_cards) if line_cards else '<div class="empty">还没有研究线。</div>'}</div>
  </section>
  <section>
    <h2 class="section-title">研究线缺口明细</h2>
    <div class="table-wrap">{line_table}</div>
  </section>
  <section>
    <h2 class="section-title">运营队列</h2>
    <div class="queue-grid">{queue_html}</div>
  </section>
</main>
"""
    (report_dir / "gaps.html").write_text(page_shell("研究缺口", body, extra_css=gaps_css), encoding="utf-8")


def render_line_pages(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    lines_dir = report_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "").strip()
        if line and line != "Unassigned":
            grouped[line].append(paper)

    line_cards = []
    expected_line_pages = {"index.html"}
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
        items = sorted(
            grouped[line],
            key=lambda paper: (role_rank(paper.get("line_role", "")), -(paper.get("year") or 0), paper["title"]),
        )
        filename = f"{slugify_label(line)}.html"
        expected_line_pages.add(filename)
        roles = sorted({p.get("line_role") for p in items if p.get("line_role")}, key=role_rank)
        topics = Counter(topic for paper in items for topic in paper.get("topics", []))
        topic_html = "".join(
            f'<span class="chip">{html.escape(topic)} {count}</span>'
            for topic, count in topics.most_common(6)
        )
        line_cards.append(
            f'<section class="line-card"><h2><a href="{html.escape(filename)}">{html.escape(line)}</a> '
            f'<span class="meta">{len(items)}</span></h2>'
            f'<div class="card-flags">{"".join(f"<span class=\"flag\">{html.escape(role)}</span>" for role in roles)}</div>'
            f'<div class="chips">{topic_html}</div></section>'
        )

        role_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for paper in items:
            role_groups[paper.get("line_role") or "unclassified"].append(paper)

        sections = []
        for role in sorted(role_groups, key=role_rank):
            rows = []
            for paper in sorted(role_groups[role], key=lambda item: (-(item.get("importance") or 0), -(item.get("year") or 0), item["title"])):
                chips = "".join(
                    f'<span class="chip">{html.escape(value)}</span>'
                    for value in [*paper.get("topics", [])[:3], *paper.get("methods", [])[:3]]
                )
                flags = [
                    f'{paper.get("year")}' if paper.get("year") else "",
                    f'重要性 {paper.get("importance")}' if paper.get("importance") else "",
                    f'状态 {paper.get("status")}' if paper.get("status") else "",
                    "有代码" if paper.get("has_code") else "",
                ]
                flag_html = "".join(f'<span class="flag">{html.escape(flag)}</span>' for flag in flags if flag)
                rows.append(
                    f'<article class="paper-row"><div><h3><a href="{html.escape(paper_href(paper, "../"))}">'
                    f'{html.escape(paper["title_zh"] or paper["title"])}</a></h3>'
                    f'<div class="meta">{html.escape(paper.get("title_en") or "")}</div>'
                    f'<div class="chips">{chips}</div></div><div class="card-flags">{flag_html}</div></article>'
                )
            sections.append(
                f'<section class="role-section"><h2>{html.escape(role)} <span class="meta">{len(role_groups[role])}</span></h2>'
                f'{"".join(rows)}</section>'
            )

        body = f"""
<header class="shell">
  <div class="eyebrow">Research Line</div>
  <h1>{html.escape(line)}</h1>
  <p class="lead">按论文在该研究线中的角色组织：foundation、baseline、main、system、variant、followup 等角色来自 frontmatter，可按你的分类习惯自由扩展。</p>
  <div class="stats">
    <a class="stat" href="../index.html">返回首页</a>
    <a class="stat" href="../library.html">论文库表格</a>
    <a class="stat" href="../review.html">复习计划</a>
    <a class="stat" href="../dashboard.html">管理控制台</a>
    <a class="stat" href="../collections.html">集合视图</a>
    <a class="stat" href="../related.html">关联网络</a>
    <a class="stat" href="../gaps.html">研究缺口</a>
    <a class="stat" href="../taxonomy.html">分类治理</a>
    <a class="stat" href="../timeline.html">时间轴</a>
    <a class="stat" href="../matrix.html">研究矩阵</a>
    <a class="stat" href="index.html">全部研究线</a>
    <span class="stat">论文 {len(items)}</span>
    <span class="stat">角色 {len(role_groups)}</span>
  </div>
</header>
<main class="shell">
  <div class="line-detail">{''.join(sections)}</div>
</main>
"""
        (lines_dir / filename).write_text(page_shell(line, body, base_prefix="../"), encoding="utf-8")

    index_body = f"""
<header class="shell">
  <div class="eyebrow">AutoPaperReader Wiki</div>
  <h1>研究线</h1>
  <p class="lead">研究线把大量论文组织成脉络，而不是孤立标签。每条线都可以进入详情页，按论文角色和重要性浏览。</p>
  <div class="stats">
    <a class="stat" href="../index.html">返回首页</a>
    <a class="stat" href="../library.html">论文库表格</a>
    <a class="stat" href="../review.html">复习计划</a>
    <a class="stat" href="../dashboard.html">管理控制台</a>
    <a class="stat" href="../collections.html">集合视图</a>
    <a class="stat" href="../related.html">关联网络</a>
    <a class="stat" href="../gaps.html">研究缺口</a>
    <a class="stat" href="../taxonomy.html">分类治理</a>
    <a class="stat" href="../timeline.html">时间轴</a>
    <a class="stat" href="../matrix.html">研究矩阵</a>
    <a class="stat" href="../tags.html">分类总览</a>
    <span class="stat">研究线 {len(grouped)}</span>
    <span class="stat">论文 {sum(len(items) for items in grouped.values())}</span>
  </div>
</header>
<main class="shell">
  <div class="line-grid">{''.join(line_cards) if line_cards else '<div class="empty">还没有研究线。</div>'}</div>
</main>
"""
    (lines_dir / "index.html").write_text(page_shell("研究线", index_body, base_prefix="../"), encoding="utf-8")

    for stale_page in lines_dir.glob("*.html"):
        if stale_page.name not in expected_line_pages:
            stale_page.unlink()


def render_tags(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    def render_group(title: str, field: str, scalar: bool = False) -> str:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for paper in papers:
            if scalar:
                value = str(paper.get(field) or "").strip()
                if value and value != "Unassigned":
                    grouped[value].append(paper)
            else:
                for value in paper.get(field, []):
                    grouped[value].append(paper)

        if not grouped:
            return ""

        sections = []
        for tag in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
            items = "\n".join(
                f'<li><a href="{html.escape(p["html_path"] or p["md_path"])}">{html.escape(p["title_zh"] or p["title"])}</a>'
                f' <span class="meta">{html.escape(str(p.get("year") or ""))}</span></li>'
                for p in grouped[tag]
            )
            sections.append(
                f'<section><h2 class="section-title">{html.escape(tag)} '
                f'<span class="meta">{len(grouped[tag])}</span></h2><ul>{items}</ul></section>'
            )

        return f'<section><h2 class="section-title">{html.escape(title)}</h2>{"".join(sections)}</section>'

    groups = [
        render_group("研究线", "research_line", scalar=True),
        render_group("领域 Domain", "domains"),
        render_group("方向 Track", "tracks"),
        render_group("问题 Problem", "problems"),
        render_group("主题 Topic", "topics"),
        render_group("方法 Method", "methods"),
    ]
    content = "\n".join(group for group in groups if group)
    if not content:
        content = '<div class="empty">还没有可展示的分类。</div>'

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        for tag in [*paper.get("domains", []), *paper.get("tracks", []), *paper.get("problems", []), *paper.get("topics", []), *paper.get("methods", [])]:
            grouped[tag].append(paper)

    body = f"""
<header class="shell">
  <div class="eyebrow">AutoPaperReader Wiki</div>
  <h1>分类与研究线总览</h1>
  <p class="lead">按 research line、domain、track、problem、topic 与 method 汇总论文。分类来自报告 frontmatter，缺失时由构建脚本根据关键词做轻量推断。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="timeline.html">时间轴</a>
    <a class="stat" href="matrix.html">研究矩阵</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <span class="stat">分类 {len(grouped)}</span>
    <span class="stat">论文 {len(papers)}</span>
  </div>
</header>
<main class="shell">{content}</main>
"""
    (report_dir / "tags.html").write_text(page_shell("分类总览", body), encoding="utf-8")


def build_wiki(report_dir: Path) -> int:
    load_taxonomy_config(report_dir)
    papers = collect_papers(report_dir)
    set_quick_open_papers(papers)
    inbox_items = load_inbox_items(report_dir, papers)
    write_json(report_dir, papers)
    write_quality_json(report_dir, papers)
    write_review_json(report_dir, papers)
    write_freshness_json(report_dir, papers)
    write_taxonomy_actions_json(report_dir, papers)
    write_actions_json(report_dir, papers, inbox_items)
    write_command_json(report_dir, papers, inbox_items)
    write_stats_json(report_dir, papers)
    write_workflow_json(report_dir, papers)
    write_status_json(report_dir, papers)
    write_views_json(report_dir, papers)
    write_batch_json(report_dir, papers)
    write_collections_json(report_dir, papers)
    write_coverage_json(report_dir, papers)
    write_gaps_json(report_dir, papers)
    write_pivot_json(report_dir, papers)
    write_compare_json(report_dir, papers)
    write_taxonomy_map_json(report_dir, papers)
    write_clusters_json(report_dir, papers)
    write_roadmap_json(report_dir, papers)
    write_inbox_json(report_dir, inbox_items)
    write_dedupe_json(report_dir, papers, inbox_items)
    write_registry_json(report_dir, papers)
    write_facets_json(report_dir, papers)
    write_intake_json(report_dir, papers, inbox_items)
    write_search_index(report_dir, papers)
    write_scale_json(report_dir, papers, inbox_items)
    write_ownership_json(report_dir, papers)
    write_routing_json(report_dir, papers)
    write_onboarding_json(report_dir, papers, inbox_items)
    render_index(report_dir, papers, inbox_items)
    render_library(report_dir, papers)
    render_board(report_dir, papers)
    render_workflow(report_dir, papers)
    render_status(report_dir, papers)
    render_views(report_dir, papers)
    render_batch(report_dir, papers)
    render_pivot(report_dir, papers)
    render_compare(report_dir, papers)
    render_taxonomy_map(report_dir, papers)
    render_clusters(report_dir, papers)
    render_roadmap(report_dir, papers)
    render_scale(report_dir, papers, inbox_items)
    render_ownership(report_dir, papers)
    render_routing(report_dir, papers)
    render_onboarding(report_dir, papers, inbox_items)
    render_intake(report_dir, papers, inbox_items)
    render_inbox(report_dir, inbox_items)
    render_dedupe(report_dir, papers, inbox_items)
    render_registry(report_dir, papers)
    render_review(report_dir, papers)
    render_freshness(report_dir, papers)
    render_quality(report_dir, papers, inbox_items)
    render_actions(report_dir, papers, inbox_items)
    render_command(report_dir, papers, inbox_items)
    render_dashboard(report_dir, papers)
    render_collections(report_dir, papers)
    render_balance(report_dir, papers)
    render_coverage(report_dir, papers)
    render_facets(report_dir, papers)
    render_related(report_dir, papers)
    render_taxonomy(report_dir, papers)
    render_timeline(report_dir, papers)
    render_matrix(report_dir, papers)
    render_gaps(report_dir, papers)
    render_line_pages(report_dir, papers)
    render_tags(report_dir, papers)
    write_catalog_placeholders(report_dir)
    write_snapshot_json(report_dir, papers, inbox_items)
    render_snapshot(report_dir, papers, inbox_items)
    write_manifest_json(report_dir, papers, inbox_items)
    write_catalog_json(report_dir, papers, inbox_items)
    render_catalog(report_dir, papers, inbox_items)
    write_snapshot_json(report_dir, papers, inbox_items)
    render_snapshot(report_dir, papers, inbox_items)
    render_release(report_dir, papers, inbox_items)
    write_manifest_json(report_dir, papers, inbox_items)
    return len(papers)


def generated_output_paths(report_dir: Path) -> set[Path]:
    paths = {report_dir / path for path in GENERATED_FIXED_PATHS}
    lines_dir = report_dir / "lines"
    if lines_dir.exists():
        paths.update(lines_dir.glob("*.html"))
    return paths


def snapshot_outputs(paths: set[Path]) -> dict[Path, bytes | None]:
    return {path: path.read_bytes() if path.exists() else None for path in paths}


def restore_outputs(snapshot: dict[Path, bytes | None], extra_paths: set[Path]) -> None:
    for path in sorted(set(snapshot) | extra_paths):
        original = snapshot.get(path)
        if original is None:
            if path.exists():
                path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(original)


def normalize_generated_content(path: Path, data: bytes | None) -> str:
    if data is None:
        return "<missing>"
    text = data.decode("utf-8")
    text = re.sub(
        r'("(?:generated_at|created_at|updated_at)"\s*:\s*")[^"]+(")',
        r"\1<TIMESTAMP>\2",
        text,
    )
    text = re.sub(r"(最近更新|生成时间) \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", r"\1 <TIMESTAMP>", text)
    text = re.sub(r"next_review &lt;= \d{4}-\d{2}-\d{2}", "next_review &lt;= <DATE>", text)
    return text


def check_wiki(report_dir: Path) -> int:
    before_paths = generated_output_paths(report_dir)
    before = snapshot_outputs(before_paths)

    try:
        count = build_wiki(report_dir)
        after_paths = generated_output_paths(report_dir)
        after = snapshot_outputs(after_paths)
        all_paths = before_paths | after_paths
        changed = []
        for path in sorted(all_paths):
            old = normalize_generated_content(path, before.get(path))
            new = normalize_generated_content(path, after.get(path))
            if old != new:
                changed.append(path)
    finally:
        restore_outputs(before, generated_output_paths(report_dir))

    if changed:
        rel_paths = [
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
            for path in changed
        ]
        print("Wiki artifacts are out of date:", file=sys.stderr)
        for rel_path in rel_paths:
            print(f"  - {rel_path}", file=sys.stderr)
        print("Run: python3 scripts/build_wiki.py docs", file=sys.stderr)
        return 1

    rel = report_dir.relative_to(ROOT) if report_dir.is_relative_to(ROOT) else report_dir
    print(f"Wiki artifacts are up to date for {count} papers in {rel}")
    return 0


def main() -> None:
    args = parse_args()
    report_dir = Path(args.report_dir).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir

    if args.check and not report_dir.exists():
        print(f"Report directory does not exist: {report_dir}", file=sys.stderr)
        raise SystemExit(1)
    report_dir.mkdir(parents=True, exist_ok=True)

    if args.check:
        raise SystemExit(check_wiki(report_dir))

    count = build_wiki(report_dir)
    rel = report_dir.relative_to(ROOT) if report_dir.is_relative_to(ROOT) else report_dir
    print(f"Built wiki for {count} papers in {rel}")


if __name__ == "__main__":
    main()
