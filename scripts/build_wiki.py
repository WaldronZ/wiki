#!/usr/bin/env python3
"""Build a lightweight paper wiki from markdown reports.

The script intentionally uses only the Python standard library so the paper
reader workflow can refresh the wiki after every newly generated report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import itertools
import json
import math
import re
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
    "inbox.json",
    "quality.json",
    "review.json",
    "taxonomy_actions.json",
    "manifest.json",
    "index.html",
    "library.html",
    "board.html",
    "inbox.html",
    "quality.html",
    "review.html",
    "dashboard.html",
    "release.html",
    "collections.html",
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
VIEW_PAGES = {"all", "index", "library"}
VIEW_STATE_KEYS = {
    "q",
    "domain",
    "track",
    "problem",
    "line",
    "role",
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
    global LABEL_ALIASES, ROLE_ORDER, STATUS_VALUES, READING_STAGE_VALUES, REVIEW_STAGE_VALUES, STATUS_WORKFLOWS, SHARED_VIEWS, ACTIVE_STATUS_WORKFLOW

    LABEL_ALIASES = DEFAULT_LABEL_ALIASES.copy()
    ROLE_ORDER = {role: index for index, role in enumerate(DEFAULT_ROLE_ORDER)}
    STATUS_VALUES = DEFAULT_STATUS_VALUES.copy()
    READING_STAGE_VALUES = DEFAULT_READING_STAGE_VALUES.copy()
    REVIEW_STAGE_VALUES = DEFAULT_REVIEW_STAGE_VALUES.copy()
    STATUS_WORKFLOWS = {}
    SHARED_VIEWS = []
    ACTIVE_STATUS_WORKFLOW = ""

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
    structure_count = sum(len(paper.get(field, []) or []) for field in ("domains", "tracks", "problems"))
    topic_count = len(paper.get("topics", []) or [])
    method_count = len(paper.get("methods", []) or [])
    tag_count = topic_count + method_count
    signals: list[str] = []
    if structure_count < 3:
        signals.append("sparse_structure")
    if tag_count < 3:
        signals.append("sparse_tags")
    if tag_count > 10:
        signals.append("dense_tags")
    if method_count > 8:
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
        line_items.append(
            {
                "name": line,
                "count": len(items),
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


def wiki_pages_manifest() -> list[dict[str, str]]:
    return [
        {"title": "首页", "href": "index.html", "kind": "view", "description": "卡片检索、筛选、研究线概览"},
        {"title": "论文库表格", "href": "library.html", "kind": "view", "description": "密集筛选、列管理、批量更新"},
        {"title": "管理控制台", "href": "dashboard.html", "kind": "ops", "description": "覆盖率、队列和运营指标"},
        {"title": "发布摘要", "href": "release.html", "kind": "ops", "description": "页面入口、数据文件、质量状态"},
        {"title": "集合视图", "href": "collections.html", "kind": "view", "description": "共享视图、智能集合、研究线入口"},
        {"title": "分类工作台", "href": "facets.html", "kind": "ops", "description": "标签规模、长尾和过载分类"},
        {"title": "关联网络", "href": "related.html", "kind": "analysis", "description": "标签共现、相似论文、孤岛论文"},
        {"title": "研究缺口", "href": "gaps.html", "kind": "ops", "description": "下一步行动和研究线缺口"},
        {"title": "状态看板", "href": "board.html", "kind": "workflow", "description": "拖拽式状态流和 CSV patch"},
        {"title": "待处理池", "href": "inbox.html", "kind": "workflow", "description": "候选论文队列和去重提示"},
        {"title": "复习计划", "href": "review.html", "kind": "workflow", "description": "待复习、需建计划、建议日期"},
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
        {"href": "taxonomy_actions.json", "description": "分类长尾、过载和空候选治理任务"},
        {"href": "inbox.json", "description": "候选论文队列和重复项"},
        {"href": "manifest.json", "description": "发布摘要和页面入口清单"},
    ]


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
                "apply_metadata_dry_run",
                "quality_gate",
            ],
        },
        {
            "id": "taxonomy_balance_review",
            "label": "Taxonomy balance review",
            "description": "Turn overloaded or sparse taxonomy buckets into project tasks before changing labels.",
            "steps": [
                "taxonomy_balance_project",
                "taxonomy_actions_project",
                "quality_gate",
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


def build_manifest(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> dict[str, Any]:
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    stats = build_stats_report(papers)
    pages = wiki_pages_manifest()
    data_files = data_files_manifest()
    command_recipes = command_recipes_manifest()
    governance_playbooks = governance_playbooks_manifest()
    quality_queues = {name: len(slugs) for name, slugs in quality["queues"].items()}
    review_queues = {name: len(slugs) for name, slugs in review["queues"].items()}
    publish_checks = {
        "metadata_complete": quality_queues.get("missing_required_metadata", 0) == 0,
        "taxonomy_clean": quality_queues.get("taxonomy_drift", 0) == 0 and not quality["label_alias_suggestions"],
        "no_duplicate_reports": quality_queues.get("duplicate_reports", 0) == 0,
        "has_review_plan": review_queues.get("needs_plan", 0) == 0,
        "has_generated_pages": all((report_dir / page["href"]).exists() for page in pages if page["href"] != "release.html"),
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
        "command_recipes": command_recipes,
        "governance_playbooks": governance_playbooks,
        "commands": [recipe["command"] for recipe in command_recipes],
    }


def write_manifest_json(report_dir: Path, papers: list[dict[str, Any]], inbox_items: list[dict[str, Any]]) -> None:
    payload = build_manifest(report_dir, papers, inbox_items)
    (report_dir / "manifest.json").write_text(
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


def write_review_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_review_plan(papers)
    (report_dir / "review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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


def page_shell(
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    extra_css: str = "",
    base_prefix: str = "",
) -> str:
    embedded = ""
    css_extra = f"\n{extra_css}" if extra_css else ""
    quick_nav_prefix = json.dumps(base_prefix)
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

  const pages = [
    ["首页", "index.html", "总览、搜索和筛选"],
    ["论文库表格", "library.html", "密集筛选、列管理和批量更新"],
    ["管理控制台", "dashboard.html", "覆盖率、队列和运营指标"],
    ["发布摘要", "release.html", "页面入口、数据文件和发布状态"],
    ["集合视图", "collections.html", "共享视图和智能集合"],
    ["分类工作台", "facets.html", "标签规模、长尾和过载分类"],
    ["关联网络", "related.html", "标签共现和相似论文"],
    ["研究缺口", "gaps.html", "下一步行动和线索缺口"],
    ["状态看板", "board.html", "拖拽状态流"],
    ["待处理池", "inbox.html", "候选论文队列"],
    ["复习计划", "review.html", "待复习和建议日期"],
    ["质量治理", "quality.html", "元数据和 taxonomy drift"],
    ["分类治理", "taxonomy.html", "分类矩阵和状态工作流"],
    ["时间轴", "timeline.html", "按年份浏览研究路线"],
    ["研究矩阵", "matrix.html", "研究线和年份覆盖"],
    ["研究线", "lines/index.html", "按研究脉络组织论文"],
    ["分类总览", "tags.html", "标签聚合入口"],
  ].map(([title, href, meta]) => ({{
    title,
    href: prefix + href,
    meta,
    kind: "page",
  }}));

  const dataFiles = [
    ["Data: papers.json", "papers.json", "论文索引、taxonomy 聚合、前端 controls"],
    ["Data: search_index.json", "search_index.json", "正文全文检索索引"],
    ["Data: stats.json", "stats.json", "运营统计、分类均衡和队列规模"],
    ["Data: quality.json", "quality.json", "质量问题、taxonomy load 和 drift"],
    ["Data: review.json", "review.json", "复习计划和建议日期"],
    ["Data: taxonomy_actions.json", "taxonomy_actions.json", "可分派分类治理任务"],
    ["Data: inbox.json", "inbox.json", "候选论文队列和重复项"],
    ["Data: manifest.json", "manifest.json", "发布状态、入口清单和 command recipes"],
  ].map(([title, href, meta]) => ({{
    title,
    href: prefix + href,
    meta,
    kind: "data",
  }}));

  const commands = [
    ["Command: Build wiki", "release.html", "python3 scripts/build_wiki.py docs"],
    ["Command: Quality gate", "release.html", "python3 scripts/check_quality.py docs"],
    ["Command: Strict validation", "release.html", "python3 scripts/validate_wiki.py docs --strict-taxonomy"],
    ["Command: Preview metadata CSV", "release.html", "python3 scripts/apply_library_metadata.py docs --input <csv>"],
    ["Command: Apply metadata CSV", "release.html", "python3 scripts/apply_library_metadata.py docs --input <csv> --write"],
    ["Command: Apply taxonomy aliases", "release.html", "python3 scripts/apply_taxonomy_aliases.py docs --write"],
    ["Command: taxonomy_actions_markdown", "release.html", "python3 scripts/export_taxonomy_actions.py docs --output docs/exports/taxonomy-actions.md"],
    ["Command: taxonomy_actions_project", "release.html", "python3 scripts/export_taxonomy_actions.py docs --format project --output docs/exports/taxonomy-project.csv"],
    ["Command: taxonomy_actions_patch", "release.html", "python3 scripts/export_taxonomy_actions.py docs --format patch --action merge_candidate --output docs/exports/taxonomy-action-patch.csv"],
    ["Command: taxonomy_balance_project", "release.html", "python3 scripts/export_taxonomy_balance.py docs --format project --max-score 50 --output docs/exports/taxonomy-balance-project.csv"],
    ["Command: taxonomy_load_csv", "release.html", "python3 scripts/export_taxonomy_load.py docs --format csv --output docs/exports/taxonomy-load.csv"],
    ["Command: taxonomy_load_patch", "release.html", "python3 scripts/export_taxonomy_load.py docs --format patch --output docs/exports/taxonomy-load-patch.csv"],
  ].map(([title, href, meta]) => ({{
    title,
    href: prefix + href,
    meta,
    kind: "command",
  }}));

  const dataPapers = (window.PAPER_WIKI && Array.isArray(window.PAPER_WIKI.papers))
    ? window.PAPER_WIKI.papers.map((paper) => ({{
        title: paper.title_zh || paper.title || paper.slug,
        href: prefix + (paper.html_path || paper.md_path || ""),
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
  const paperMap = new Map([...dataPapers, ...rowPapers].map((item) => [item.href, item]));
  const papers = Array.from(paperMap.values());
  const entries = [...pages, ...dataFiles, ...commands, ...papers];
  let activeIndex = 0;

  function score(entry, query) {{
    if (!query) return entry.kind === "page" ? 2 : 1;
    const haystack = `${{entry.title}} ${{entry.meta}} ${{entry.href}}`.toLowerCase();
    if (haystack.includes(query)) return entry.title.toLowerCase().includes(query) ? 3 : 2;
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
      const title = document.createElement("strong");
      title.textContent = entry.title;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = entry.meta || entry.href;
      link.append(title, meta);
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


def render_index(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    taxonomy = taxonomy_counts(papers)
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
        "shared_views": shared_views_for("index"),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    cards = "\n".join(render_card(paper) for paper in papers)
    line_overview = render_line_overview(papers)
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
  <p class="lead">这里汇总每一篇独立阅读报告，并按主题、方法、年份和代码可复现性进行浏览。每次新增报告后运行构建脚本即可刷新。</p>
  <div class="stats">
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">研究线 {len(taxonomy["research_lines"])}</span>
    <span class="stat">分类 {len(data["tags"])}</span>
    <span class="stat">最近更新 {html.escape(data["generated_at"])}</span>
    <a class="stat" href="library.html">论文库表格</a>
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
  {line_overview}
  <div class="results-bar">
    <strong id="resultCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <div class="results-actions">
      <select id="savedView" class="saved-view" aria-label="选择保存视图"><option value="">选择视图</option></select>
      <button id="saveView" class="button" type="button">保存视图</button>
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
const copySharedView = document.querySelector("#copySharedView");
const deleteView = document.querySelector("#deleteView");
const exportSavedViews = document.querySelector("#exportSavedViews");
const importSavedViews = document.querySelector("#importSavedViews");
const searchTextBySlug = new Map((window.PAPER_WIKI.search_index || []).map(item => [item.slug, item.search_text || ""]));
const sharedViews = window.PAPER_WIKI.shared_views || [];
let currentPage = 1;
const savedViewsKey = "autopaperreader:index:savedViews";
const queryControls = [
  ["q", search],
  ["domain", domain],
  ["line", line],
  ["role", role],
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

function defaultValueFor(key) {{
  return key === "sort" ? "default" : key === "size" ? "12" : "";
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
    el.value = state[key] || defaultValueFor(key);
  }});
  currentPage = Number(state.page || 1) || 1;
  render();
}}

function readStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  queryControls.forEach(([key, el]) => {{
    el.value = params.has(key) ? params.get(key) : defaultValueFor(key);
  }});
  currentPage = Number(params.get("page") || 1) || 1;
}}

function writeStateToUrl() {{
  const params = new URLSearchParams(currentState());
  const query = params.toString();
  const nextUrl = query ? `${{location.pathname}}?${{query}}` : location.pathname;
  window.history.replaceState(null, "", nextUrl);
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

const filterControls = [search, domain, line, role, topic, method, status, stage, code, importance, reviewStage, review, sort, pageSize];
filterControls.forEach(el => el.addEventListener("input", () => {{
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
readStateFromUrl();
refreshSavedViews();
render();
</script>
"""
    (report_dir / "index.html").write_text(page_shell("我的论文知识库", body, data), encoding="utf-8")


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
    """
    body = f"""
<header class="shell">
  <div class="eyebrow">Paper Library</div>
  <h1>论文库表格</h1>
  <p class="lead">面向大量论文的密集管理视图：快速扫状态、研究线、分类覆盖、重要性和代码情况。适合批量整理与查漏补缺。</p>
  <div class="stats">
    <a class="stat" href="index.html">卡片首页</a>
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
  <div class="bulk-panel">
    <span id="bulkCount" class="bulk-count">已选 0 篇</span>
    <select id="bulkStatus"><option value="">状态</option>{render_value_options(controls["status"])}</select>
    <select id="bulkStage"><option value="">阅读阶段</option>{render_value_options(controls["reading_stage"])}</select>
    <select id="bulkReviewStage"><option value="">复习阶段</option>{render_value_options(controls["review_stage"])}</select>
    <input id="bulkNextReview" type="date" aria-label="下次复习日期">
    <div class="bulk-actions">
      <button id="selectVisible" class="button" type="button">选中当前页</button>
      <button id="selectFiltered" class="button" type="button">选中筛选结果</button>
      <button id="clearSelected" class="button" type="button">清除选择</button>
      <button id="downloadPatch" class="button" type="button">下载 CSV</button>
    </div>
    <details class="bulk-taxonomy">
      <summary>批量分类字段</summary>
      <div class="bulk-taxonomy-grid">
        <label><span>研究线</span><input id="bulkResearchLine" list="researchLineOptions" type="text" placeholder="Research line"></label>
        <label><span>研究线角色</span><select id="bulkLineRole"><option value="">角色</option>{render_value_options(controls["line_role"])}</select></label>
        <label><span>Domain</span><input id="bulkDomains" list="domainOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Track</span><input id="bulkTracks" list="trackOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Problem</span><input id="bulkProblems" list="problemOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Topics</span><input id="bulkTopics" list="topicOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <label><span>Methods</span><input id="bulkMethods" list="methodOptions" type="text" placeholder="多个值用 ; 分隔"></label>
        <div class="bulk-hint">这些字段会替换所选论文 frontmatter 中的对应值；下载后先 dry-run，再用 --write 写回。</div>
      </div>
    </details>
  </div>
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
const copySharedView = document.querySelector("#copySharedView");
const deleteView = document.querySelector("#deleteView");
const exportSavedViews = document.querySelector("#exportSavedViews");
const importSavedViews = document.querySelector("#importSavedViews");
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
const downloadPatch = document.querySelector("#downloadPatch");
const libraryTable = document.querySelector(".library-table");
const columnToggles = Array.from(document.querySelectorAll("[data-column-toggle]"));
const densityMode = document.querySelector("#densityMode");
const sharedViews = window.PAPER_WIKI.shared_views || [];
const wikiControls = window.PAPER_WIKI.controls || {{}};
const statusWorkflows = wikiControls.status_workflows || {{}};
const activeStatusWorkflow = wikiControls.active_status_workflow || Object.keys(statusWorkflows)[0] || "default";
const fallbackStatusValues = Array.isArray(wikiControls.status) ? wikiControls.status : [];
const observedStatusValues = Array.from(new Set(allRows.map(row => row.dataset.status).filter(Boolean)));
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
  ["code", code],
  ["importance", importance],
  ["sort", sort],
  ["size", pageSize],
];

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
  const workflow = statusWorkflows[name] || {{}};
  const configured = Array.isArray(workflow.status_values) ? workflow.status_values : fallbackStatusValues;
  return orderedUnique([...configured, ...observedStatusValues]);
}}

function statusCount(value) {{
  return allRows.filter(row => row.dataset.status === value).length;
}}

function replaceStatusOptions(select, placeholder, values, withCounts = false) {{
  const current = select.value;
  select.replaceChildren(new Option(placeholder, ""));
  values.forEach(value => {{
    const label = withCounts ? `${{value}} (${{statusCount(value)}})` : value;
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
  const values = statusValuesForWorkflow(statusWorkflow.value);
  replaceStatusOptions(status, "全部状态", values, true);
  replaceStatusOptions(bulkStatus, "状态", values, false);
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

function applyState(state) {{
  controls.forEach(([key, el]) => {{
    if (key === "status") return;
    el.value = state[key] || defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = state.status || defaultValueFor("status");
  currentPage = Number(state.page || 1) || 1;
  render();
}}

function readStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  controls.forEach(([key, el]) => {{
    if (key === "status") return;
    el.value = params.has(key) ? params.get(key) : defaultValueFor(key);
  }});
  applyStatusWorkflow();
  status.value = params.has("status") ? params.get("status") : defaultValueFor("status");
  currentPage = Number(params.get("page") || 1) || 1;
}}

function writeStateToUrl() {{
  const params = new URLSearchParams(currentState());
  const query = params.toString();
  window.history.replaceState(null, "", query ? `${{location.pathname}}?${{query}}` : location.pathname);
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

function updateBulkState() {{
  const selected = selectedRows().length;
  const visible = visibleRows();
  const visibleSelected = visible.filter(row => row.querySelector(".row-check").checked).length;
  bulkCount.textContent = `已选 ${{selected}} 篇`;
  toggleVisible.checked = visible.length > 0 && visibleSelected === visible.length;
  toggleVisible.indeterminate = visibleSelected > 0 && visibleSelected < visible.length;
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

function buildPatchRows() {{
  const fields = [];
  const values = {{}};
  [
    ["status", bulkStatus.value],
    ["reading_stage", bulkStage.value],
    ["review_stage", bulkReviewStage.value],
    ["next_review", bulkNextReview.value],
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
  const selected = selectedRows();
  if (!selected.length) {{
    window.alert("请先选择论文。");
    return [];
  }}
  if (!fields.length) {{
    window.alert("请先选择要写入的状态、日期或分类字段。");
    return [];
  }}
  return [["slug", ...fields], ...selected.map(row => [row.dataset.slug, ...fields.map(field => values[field])])];
}}

function render() {{
  const q = search.value.trim().toLowerCase();
  const minImportance = Number(importance.value || 0);
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
      && (!code.value || row.dataset.code === code.value)
      && (!minImportance || Number(row.dataset.importance || 0) >= minImportance);
  }});
  const ranked = sortRows(filtered);
  currentRankedRows = ranked;
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

function placeCard(card, status) {{
  const zone = dropzones.find(item => item.dataset.status === status);
  if (!zone) return;
  zone.appendChild(card);
  card.dataset.status = status;
  card.classList.toggle("changed", card.dataset.status !== card.dataset.originalStatus);
  renderBoard();
}}

function renderBoard() {{
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

function applyWorkflow(name) {{
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
  renderBoard();
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

[boardSearch, boardLine, boardTrack, boardImportance].forEach(el => el.addEventListener("input", renderBoard));
boardWorkflow.addEventListener("change", () => applyWorkflow(boardWorkflow.value));
downloadBoardPatch.addEventListener("click", () => {{
  const changed = changedCards();
  if (!changed.length) return;
  downloadBoardCsv("status_board_patch.csv", [["slug", "status"], ...changed.map(card => [card.dataset.slug, card.dataset.status])]);
}});
resetBoardChanges.addEventListener("click", () => {{
  changedCards().forEach(card => placeCard(card, card.dataset.originalStatus));
}});
renderBoard();
</script>
"""
    (report_dir / "board.html").write_text(page_shell("状态看板", body, extra_css=board_css), encoding="utf-8")


def render_inbox_row(item: dict[str, Any]) -> str:
    tags = "".join(f'<span class="chip">{html.escape(tag)}</span>' for tag in item.get("tags", []))
    link = str(item.get("link") or "")
    link_html = f'<a href="{html.escape(link)}">{html.escape(link)}</a>' if link else ""
    duplicate = '<span class="flag">已在库中</span>' if item.get("duplicate") else ""
    prompt_bits = [
        item.get("title") or "",
        item.get("link") or "",
        item.get("arxiv_id") or "",
    ]
    prompt = " ".join(str(bit) for bit in prompt_bits if bit).strip()
    return f"""<tr
  data-search="{html.escape(' '.join(str(value) for value in [item.get('title'), item.get('link'), item.get('arxiv_id'), item.get('note'), *item.get('tags', [])] if value).lower(), quote=True)}"
  data-status="{html.escape(str(item.get("status") or ""), quote=True)}"
  data-priority="{html.escape(str(item.get("priority") or ""), quote=True)}"
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
let visibleInboxRows = [...inboxRows];

function promptForRow(row) {{
  const button = row.querySelector(".copy-prompt");
  return button ? `请按 AutoPaperReader 工作流阅读这篇论文：${{button.dataset.prompt}}` : "";
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
        ("预览元数据写入", "python3 scripts/apply_library_metadata.py docs --input <csv>"),
        ("预览别名写入", "python3 scripts/apply_taxonomy_aliases.py docs"),
        ("写入别名建议", "python3 scripts/apply_taxonomy_aliases.py docs --write"),
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
        line_link = (
            f'<a href="lines/{html.escape(slugify_label(line))}.html">{html.escape(line)}</a>'
            if line != "Unassigned"
            else html.escape(line)
        )
        line_rows.append(
            "<tr>"
            f"<td>{line_link}</td>"
            f"<td>{len(items)}</td>"
            f"<td>{html.escape(', '.join(roles))}</td>"
            f"<td>{avg_importance}</td>"
            f"<td>{percent(code_count, len(items))}</td>"
            "</tr>"
        )

    line_table = (
        '<table class="data-table"><thead><tr><th>研究线</th><th>论文</th><th>角色</th><th>平均重要性</th><th>代码覆盖</th></tr></thead>'
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


def render_collections(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    quality = build_quality_report(papers)
    review_plan = build_review_plan(papers)
    today = dt.date.today().isoformat()
    paper_by_slug = {paper["slug"]: paper for paper in papers}

    def items_from_slugs(slugs: list[str]) -> list[dict[str, Any]]:
        return [paper_by_slug[slug] for slug in slugs if slug in paper_by_slug]

    def sample_list(items: list[dict[str, Any]]) -> str:
        if not items:
            return '<div class="empty">暂无论文。</div>'
        rows = "".join(
            f'<li><a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
            f' <span class="meta">{html.escape(str(paper.get("research_line") or "Unassigned"))}</span></li>'
            for paper in items[:5]
        )
        more = f'<div class="meta">另有 {len(items) - 5} 篇未显示。</div>' if len(items) > 5 else ""
        return f'<ol class="queue-list">{rows}</ol>{more}'

    def smart_card(title: str, href: str, note: str, items: list[dict[str, Any]]) -> str:
        return f"""<section class="collection-card">
  <header><h2><a href="{html.escape(href)}">{html.escape(title)}</a></h2><strong>{len(items)}</strong></header>
  <p class="meta">{html.escape(note)}</p>
  {sample_list(items)}
</section>"""

    shared_rows = []
    for view in SHARED_VIEWS:
        state = view.get("state") or {}
        count = sum(1 for paper in papers if matches_view_state(paper, state, today))
        shared_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(view_href(view))}">{html.escape(str(view["name"]))}</a></td>'
            f"<td>{html.escape(str(view.get('page') or 'all'))}</td>"
            f"<td>{count}</td>"
            f"<td><code>{html.escape(json.dumps(state, ensure_ascii=False, sort_keys=True))}</code></td>"
            "</tr>"
        )
    shared_table = (
        '<table class="data-table"><thead><tr><th>视图</th><th>页面</th><th>命中</th><th>筛选状态</th></tr></thead>'
        f"<tbody>{''.join(shared_rows)}</tbody></table>"
        if shared_rows
        else '<div class="empty">还没有共享视图。可以在 guides/taxonomy.json 的 shared_views 中添加。</div>'
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

    smart_cards = [
        smart_card("重点论文", page_query_href("library.html", importance="5", sort="importance"), "importance >= 5 的核心阅读对象。", high_importance),
        smart_card("待复习", page_query_href("review.html"), f"next_review <= {today} 的复习队列。", due_review),
        smart_card("需建复习计划", page_query_href("review.html"), "缺少 next_review 的论文。", no_review_plan),
        smart_card("待补分类", page_query_href("quality.html"), "缺少必要 taxonomy 或研究线角色的论文。", missing_taxonomy),
        smart_card("分类偏薄", page_query_href("quality.html"), "结构分类或 topic/method 太少，检索入口不足。", taxonomy_sparse),
        smart_card("分类过密", page_query_href("quality.html"), "topic/method 过多，可能需要收敛为核心标签。", taxonomy_dense),
        smart_card("Taxonomy Drift", page_query_href("quality.html"), "状态、阶段或角色不在 taxonomy.json 允许值中的论文。", taxonomy_drift),
        smart_card("缺代码观察", page_query_href("gaps.html"), "尚未记录代码仓库或代码实现观察的论文。", no_code_observation),
    ]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)
    line_rows = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
        items = grouped[line]
        href = f"lines/{slugify_label(line)}.html" if line != "Unassigned" else page_query_href("library.html", line=line)
        five_star = sum(1 for paper in items if int(paper.get("importance") or 0) >= 5)
        needs_plan = sum(1 for paper in items if not paper.get("next_review"))
        line_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(href)}">{html.escape(line)}</a></td>'
            f"<td>{len(items)}</td>"
            f"<td>{five_star}</td>"
            f"<td>{needs_plan}</td>"
            f'<td><a href="{html.escape(page_query_href("library.html", line=line, sort="importance"))}">打开集合</a></td>'
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
    <a class="stat" href="library.html">论文库表格</a>
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="collections.html">集合视图</a>
    <a class="stat" href="related.html">关联网络</a>
    <a class="stat" href="gaps.html">研究缺口</a>
    <a class="stat" href="review.html">复习计划</a>
    <a class="stat" href="quality.html">质量治理</a>
    <a class="stat" href="taxonomy.html">分类治理</a>
    <span class="stat">共享视图 {len(SHARED_VIEWS)}</span>
    <span class="stat">论文 {len(papers)}</span>
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
            if total and count / total >= 0.6 and count >= 5
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


def taxonomy_action_status(count: int, share: float) -> tuple[str, str]:
    if count == 0:
        return "unused_config", "medium"
    if count == 1:
        return "merge_candidate", "medium"
    if share >= 0.6 and count >= 5:
        return "split_candidate", "high"
    if share >= 0.4 and count >= 4:
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
        "actions": actions,
    }


def write_taxonomy_actions_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = build_taxonomy_actions(papers)
    (report_dir / "taxonomy_actions.json").write_text(
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
        field_options.append(f'<option value="{html.escape(label, quote=True)}">{html.escape(label)}</option>')
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
            action, _severity = taxonomy_action_status(count, share)
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
            search_text = " ".join([label, english, value, action, recommendation]).lower()
            table_rows.append(
                f'<tr data-field="{html.escape(label, quote=True)}" data-action="{html.escape(action, quote=True)}" data-value="{html.escape(value, quote=True)}" data-count="{count}" data-share="{round(share, 4)}" data-href="{html.escape(href, quote=True)}" data-recommendation="{html.escape(recommendation, quote=True)}" data-search="{html.escape(search_text, quote=True)}">'
                f"<td>{html.escape(label)}</td>"
                f"<td>{value_cell}</td>"
                f"<td>{count}</td>"
                f"<td>{round(share * 100)}%</td>"
                f"<td>{flag_html}</td>"
                f"<td>{sample_links(field, value, is_list)}</td>"
                f"<td>{html.escape(recommendation)}</td>"
                "</tr>"
            )

    table_html = (
        '<table class="data-table"><thead><tr><th>字段</th><th>标签</th><th>论文</th><th>占比</th><th>状态</th><th>样例</th><th>建议动作</th></tr></thead>'
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
      grid-template-columns: minmax(220px, 1fr) repeat(2, minmax(150px, 210px)) auto;
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
      <select id="facetAction"><option value="">全部状态</option><option value="merge_candidate">长尾待合并</option><option value="split_candidate">过载待拆分</option><option value="unused_config">候选空值</option><option value="watch">观察中</option><option value="stable">稳定</option></select>
      <strong id="facetResultCount">{len(table_rows)} 项</strong>
      <button id="downloadFacetCsv" class="button" type="button">下载当前 CSV</button>
    </div>
    <div class="table-wrap">{table_html}</div>
  </section>
</main>
<script>
const facetSearch = document.querySelector("#facetSearch");
const facetField = document.querySelector("#facetField");
const facetAction = document.querySelector("#facetAction");
const facetResultCount = document.querySelector("#facetResultCount");
const downloadFacetCsv = document.querySelector("#downloadFacetCsv");
const facetRows = Array.from(document.querySelectorAll("tr[data-field]"));

function facetCsvCell(value) {{
  const text = String(value ?? "");
  return (text.includes(",") || text.includes('"') || text.includes("\\n"))
    ? `"${{text.replaceAll('"', '""')}}"`
    : text;
}}

function downloadFacetRows() {{
  const rows = facetRows.filter(row => !row.hidden);
  if (!rows.length) {{
    window.alert("当前筛选结果为空。");
    return;
  }}
  const header = ["field", "value", "count", "share", "action", "recommendation", "href"];
  const body = rows.map(row => [
    row.dataset.field,
    row.dataset.value,
    row.dataset.count,
    row.dataset.share,
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

function renderFacetRows() {{
  const q = facetSearch.value.trim().toLowerCase();
  const field = facetField.value;
  const action = facetAction.value;
  let visible = 0;
  facetRows.forEach(row => {{
    const hit = (!q || row.dataset.search.includes(q))
      && (!field || row.dataset.field === field)
      && (!action || row.dataset.action === action);
    row.hidden = !hit;
    if (hit) visible += 1;
  }});
  facetResultCount.textContent = `${{visible}} / ${{facetRows.length}} 项`;
}}

[facetSearch, facetField, facetAction].forEach((control) => control.addEventListener("input", renderFacetRows));
downloadFacetCsv.addEventListener("click", downloadFacetRows);
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
            "    .designer-grid {",
            "      display: grid;",
            "      grid-template-columns: repeat(3, minmax(0, 1fr));",
            "      gap: 12px;",
            "      margin: 14px 0;",
            "    }",
            "    .designer-grid label { display: grid; gap: 6px; font-weight: 700; }",
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
            "    @media (max-width: 820px) { .designer-grid, .taxonomy-change-grid { grid-template-columns: 1fr; } }",
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
    <select id="timelineStatus"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="timelineStage"><option value="">阅读阶段</option>{render_topic_options(taxonomy["reading_stages"])}</select>
    <select id="timelineCode"><option value="">代码状态</option><option value="yes">有代码</option><option value="no">无代码</option></select>
    <select id="timelineImportance"><option value="">重要性</option><option value="5">5 星</option><option value="4">4 星及以上</option><option value="3">3 星及以上</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="timelineCount">显示 {len(papers)} / {len(papers)} 篇</strong>
    <button id="timelineReset" class="button" type="button">重置筛选</button>
  </div>
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
const timelineStatus = document.querySelector("#timelineStatus");
const timelineStage = document.querySelector("#timelineStage");
const timelineCode = document.querySelector("#timelineCode");
const timelineImportance = document.querySelector("#timelineImportance");
const timelineCount = document.querySelector("#timelineCount");
const timelineReset = document.querySelector("#timelineReset");
const timelineControls = [timelineSearch, timelineLine, timelineTrack, timelineRole, timelineStatus, timelineStage, timelineCode, timelineImportance];

function timelineTokens(value) {{
  return String(value || "").split("|").filter(Boolean);
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
}}

timelineControls.forEach(control => control.addEventListener("input", renderTimeline));
timelineReset.addEventListener("click", () => {{
  timelineControls.forEach(control => {{
    control.value = "";
  }});
  renderTimeline();
}});
renderTimeline();
</script>
"""
    (report_dir / "timeline.html").write_text(page_shell("研究路线时间轴", body, extra_css=timeline_css), encoding="utf-8")


def render_matrix(report_dir: Path, papers: list[dict[str, Any]]) -> None:
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
    @media (max-width: 980px) {
      .matrix-layout { grid-template-columns: 1fr; }
      .matrix-detail { position: static; }
    }
    """
    data = {"papers": matrix_items}
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
    <select id="matrixStatus"><option value="">全部状态</option>{render_topic_options(taxonomy["statuses"])}</select>
    <select id="matrixImportance"><option value="">重要性</option><option value="5">含 5 星</option><option value="4">含 4 星及以上</option><option value="3">含 3 星及以上</option></select>
  </div>
</div>
<main class="shell">
  <div class="results-bar">
    <strong id="matrixCount">显示 {len(lines)} / {len(lines)} 条研究线</strong>
    <button id="matrixReset" class="button" type="button">重置筛选</button>
  </div>
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
const matrixStatus = document.querySelector("#matrixStatus");
const matrixImportance = document.querySelector("#matrixImportance");
const matrixReset = document.querySelector("#matrixReset");
const matrixCount = document.querySelector("#matrixCount");
const matrixDetailTitle = document.querySelector("#matrixDetailTitle");
const matrixDetailMeta = document.querySelector("#matrixDetailMeta");
const matrixDetailList = document.querySelector("#matrixDetailList");
const matrixPapers = window.PAPER_WIKI.papers || [];

function matrixTokens(value) {{
  return String(value || "").split("|").filter(Boolean);
}}

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, char => ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[char]));
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

[matrixSearch, matrixTrack, matrixStatus, matrixImportance].forEach(control => control.addEventListener("input", renderMatrixFilters));
matrixReset.addEventListener("click", () => {{
  [matrixSearch, matrixTrack, matrixStatus, matrixImportance].forEach(control => {{
    control.value = "";
  }});
  renderMatrixFilters();
}});
matrixCells.forEach(cell => cell.addEventListener("click", () => renderMatrixDetail(cell.dataset.line, cell.dataset.year)));
renderMatrixFilters();
const firstNonEmpty = matrixCells.find(cell => Number(cell.dataset.count || 0) > 0);
if (firstNonEmpty) renderMatrixDetail(firstNonEmpty.dataset.line, firstNonEmpty.dataset.year);
</script>
"""
    (report_dir / "matrix.html").write_text(page_shell("研究线年份矩阵", body, data, matrix_css), encoding="utf-8")


def render_gaps(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    current_year = dt.date.today().year
    recommended_roles = ["foundation", "baseline", "main", "system"]
    quality = build_quality_report(papers)
    review = build_review_plan(papers)
    taxonomy_load_by_slug = {item["slug"]: item for item in quality.get("taxonomy_load", [])}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        grouped[str(paper.get("research_line") or "Unassigned")].append(paper)

    def queue_item(paper: dict[str, Any], reason: str) -> str:
        labels = [
            str(paper.get("research_line") or "Unassigned"),
            str(paper.get("status") or ""),
            f'I {paper.get("importance")}' if paper.get("importance") else "",
            reason,
        ]
        flags = "".join(f'<span class="flag">{html.escape(label)}</span>' for label in labels if label)
        return (
            f'<li><a href="{html.escape(paper_href(paper))}">{html.escape(paper["title_zh"] or paper["title"])}</a>'
            f'<div class="card-flags">{flags}</div></li>'
        )

    line_rows = []
    line_cards = []
    all_actions: list[tuple[int, str, str, str]] = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name == "Unassigned", name.lower())):
        items = grouped[line]
        roles = {str(paper.get("line_role") or "") for paper in items if paper.get("line_role")}
        missing_roles = [role for role in recommended_roles if role not in roles]
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
        for action in actions[:4]:
            priority = 100 - score
            all_actions.append((priority, line, action, str(latest_year or "unknown")))

        line_href = f"lines/{slugify_label(line)}.html" if line != "Unassigned" else "library.html?line=Unassigned"
        line_rows.append(
            "<tr>"
            f'<td><a href="{html.escape(line_href)}">{html.escape(line)}</a></td>'
            f"<td>{len(items)}</td>"
            f"<td>{score}</td>"
            f"<td>{html.escape(str(latest_year or 'unknown'))}</td>"
            f"<td>{html.escape(', '.join(missing_roles) or '-')}</td>"
            f"<td>{len(missing_taxonomy)}</td>"
            f"<td>{len(taxonomy_load)}</td>"
            f"<td>{len(no_review)}</td>"
            f"<td>{len(no_code)}</td>"
            f"<td>{html.escape('; '.join(actions[:3]))}</td>"
            "</tr>"
        )
        chip_html = "".join(f'<span class="chip">{html.escape(action)}</span>' for action in actions[:4])
        paper_links = "".join(queue_item(paper, "重点") for paper in high_priority[:3])
        if not paper_links:
            paper_links = '<li class="meta">暂无 5 星论文。</li>'
        line_cards.append(
            f"""<section class="gap-card" data-score="{score}">
  <header><h2><a href="{html.escape(line_href)}">{html.escape(line)}</a></h2><strong>{score}</strong></header>
  <div class="meta">论文 {len(items)} · 最新 {html.escape(str(latest_year or 'unknown'))}</div>
  <div class="chips">{chip_html}</div>
  <ol class="queue-list">{paper_links}</ol>
</section>"""
        )

    action_rows = "".join(
        "<tr>"
        f"<td>{priority}</td>"
        f'<td><a href="{html.escape(page_query_href("library.html", line=line))}">{html.escape(line)}</a></td>'
        f"<td>{html.escape(action)}</td>"
        f"<td>{html.escape(year)}</td>"
        "</tr>"
        for priority, line, action, year in sorted(all_actions, key=lambda item: (-item[0], item[1], item[2]))[:24]
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

    need_plan = [
        paper
        for paper in papers
        if paper["slug"] in set(review["queues"].get("needs_plan", []))
    ]
    taxonomy_queue = [
        paper
        for paper in papers
        if paper["slug"] in set(quality["queues"].get("missing_required_metadata", []))
    ]
    code_queue = [
        paper
        for paper in papers
        if paper["slug"] in set(quality["queues"].get("no_code_observation", []))
    ]
    taxonomy_sparse_queue = [
        paper
        for paper in papers
        if paper["slug"] in set(quality["queues"].get("taxonomy_sparse", []))
    ]
    taxonomy_dense_queue = [
        paper
        for paper in papers
        if paper["slug"] in set(quality["queues"].get("taxonomy_dense", []))
    ]
    queue_blocks = [
        ("需建复习计划", need_plan, "review"),
        ("待补分类", taxonomy_queue, "taxonomy"),
        ("分类偏薄", taxonomy_sparse_queue, "sparse"),
        ("分类过密", taxonomy_dense_queue, "dense"),
        ("缺代码观察", code_queue, "code"),
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
    <span class="stat">论文 {len(papers)}</span>
    <span class="stat">研究线 {len(grouped)}</span>
    <span class="stat">建议 {len(all_actions)}</span>
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
    inbox_items = load_inbox_items(report_dir, papers)
    write_json(report_dir, papers)
    write_quality_json(report_dir, papers)
    write_review_json(report_dir, papers)
    write_taxonomy_actions_json(report_dir, papers)
    write_stats_json(report_dir, papers)
    write_inbox_json(report_dir, inbox_items)
    write_search_index(report_dir, papers)
    render_index(report_dir, papers)
    render_library(report_dir, papers)
    render_board(report_dir, papers)
    render_inbox(report_dir, inbox_items)
    render_review(report_dir, papers)
    render_quality(report_dir, papers, inbox_items)
    render_dashboard(report_dir, papers)
    render_collections(report_dir, papers)
    render_facets(report_dir, papers)
    render_related(report_dir, papers)
    render_taxonomy(report_dir, papers)
    render_timeline(report_dir, papers)
    render_matrix(report_dir, papers)
    render_gaps(report_dir, papers)
    render_line_pages(report_dir, papers)
    render_tags(report_dir, papers)
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
