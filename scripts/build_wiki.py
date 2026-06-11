#!/usr/bin/env python3
"""Build a lightweight paper wiki from markdown reports.

The script intentionally uses only the Python standard library so the paper
reader workflow can refresh the wiki after every newly generated report.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "docs"

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

LABEL_ALIASES = {
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build docs/index.html and docs/papers.json")
    parser.add_argument(
        "report_dir",
        nargs="?",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory containing <slug>.md and <slug>.html reports.",
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


def role_rank(role: str) -> int:
    order = {
        "foundation": 0,
        "baseline": 1,
        "main": 2,
        "system": 3,
        "variant": 4,
        "followup": 5,
        "survey": 6,
    }
    return order.get(role, 20)


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
        "statuses": scalar_counts(papers, "status"),
        "reading_stages": scalar_counts(papers, "reading_stage"),
        "review_stages": scalar_counts(papers, "review_stage"),
    }


def write_json(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "tags": tag_counts(papers),
        "taxonomy": taxonomy_counts(papers),
        "papers": [public_paper(paper) for paper in papers],
    }
    (report_dir / "papers.json").write_text(
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


def page_shell(title: str, body: str, data: dict[str, Any] | None = None) -> str:
    embedded = ""
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
    .queue-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
    .queue-list {{ margin: 0; padding-left: 18px; }}
    .queue-list li {{ margin: 8px 0; }}
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
    }}
  </style>
</head>
<body>
{embedded}
{body}
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
    <a class="stat" href="dashboard.html">管理控制台</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="tags.html">分类总览</a>
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
const searchTextBySlug = new Map((window.PAPER_WIKI.search_index || []).map(item => [item.slug, item.search_text || ""]));
let currentPage = 1;
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

function readStateFromUrl() {{
  const params = new URLSearchParams(window.location.search);
  queryControls.forEach(([key, el]) => {{
    if (params.has(key)) el.value = params.get(key);
  }});
  currentPage = Number(params.get("page") || 1) || 1;
}}

function writeStateToUrl() {{
  const params = new URLSearchParams();
  queryControls.forEach(([key, el]) => {{
    const defaultValue = key === "sort" ? "default" : key === "size" ? "12" : "";
    if (el.value && el.value !== defaultValue) params.set(key, el.value);
  }});
  if (currentPage > 1) params.set("page", String(currentPage));
  const query = params.toString();
  const nextUrl = query ? `${{location.pathname}}?${{query}}` : location.pathname;
  window.history.replaceState(null, "", nextUrl);
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
  filterControls.forEach(el => el.value = "");
  sort.value = "default";
  pageSize.value = "12";
  currentPage = 1;
  render();
}});
readStateFromUrl();
render();
</script>
"""
    (report_dir / "index.html").write_text(page_shell("我的论文知识库", body, data), encoding="utf-8")


def render_topic_options(tags: dict[str, int]) -> str:
    return "".join(
        f'<option value="{html.escape(tag)}">{html.escape(tag)} ({count})</option>'
        for tag, count in tags.items()
    )


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


def render_dashboard(report_dir: Path, papers: list[dict[str, Any]]) -> None:
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
        ("研究线", str(len(scalar_counts(papers, "research_line"))), "有明确 research_line 的脉络"),
        ("代码覆盖", percent(with_code, total), "包含代码观察或代码仓库线索"),
        ("高优先级", str(len(high_importance)), "importance >= 5"),
        ("待复习", str(len(due_review)), f"next_review <= {today}"),
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

    body = f"""
<header class="shell">
  <div class="eyebrow">Knowledge Base Operations</div>
  <h1>管理控制台</h1>
  <p class="lead">面向大量论文的运营视图：看分类覆盖、研究线健康度、复习队列和需要补元数据的报告。所有数据来自 markdown frontmatter 与 wiki 索引。</p>
  <div class="stats">
    <a class="stat" href="index.html">返回首页</a>
    <a class="stat" href="lines/index.html">研究线</a>
    <a class="stat" href="tags.html">分类总览</a>
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
    <h2 class="section-title">管理队列</h2>
    <div class="queue-grid">{''.join(queues)}</div>
  </section>
</main>
"""
    (report_dir / "dashboard.html").write_text(page_shell("管理控制台", body), encoding="utf-8")


def render_line_pages(report_dir: Path, papers: list[dict[str, Any]]) -> None:
    lines_dir = report_dir / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        line = str(paper.get("research_line") or "").strip()
        if line and line != "Unassigned":
            grouped[line].append(paper)

    line_cards = []
    for line in sorted(grouped, key=lambda name: (-len(grouped[name]), name.lower())):
        items = sorted(
            grouped[line],
            key=lambda paper: (role_rank(paper.get("line_role", "")), -(paper.get("year") or 0), paper["title"]),
        )
        filename = f"{slugify_label(line)}.html"
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
    <a class="stat" href="../dashboard.html">管理控制台</a>
    <a class="stat" href="index.html">全部研究线</a>
    <span class="stat">论文 {len(items)}</span>
    <span class="stat">角色 {len(role_groups)}</span>
  </div>
</header>
<main class="shell">
  <div class="line-detail">{''.join(sections)}</div>
</main>
"""
        (lines_dir / filename).write_text(page_shell(line, body), encoding="utf-8")

    index_body = f"""
<header class="shell">
  <div class="eyebrow">AutoPaperReader Wiki</div>
  <h1>研究线</h1>
  <p class="lead">研究线把大量论文组织成脉络，而不是孤立标签。每条线都可以进入详情页，按论文角色和重要性浏览。</p>
  <div class="stats">
    <a class="stat" href="../index.html">返回首页</a>
    <a class="stat" href="../dashboard.html">管理控制台</a>
    <a class="stat" href="../tags.html">分类总览</a>
    <span class="stat">研究线 {len(grouped)}</span>
    <span class="stat">论文 {sum(len(items) for items in grouped.values())}</span>
  </div>
</header>
<main class="shell">
  <div class="line-grid">{''.join(line_cards) if line_cards else '<div class="empty">还没有研究线。</div>'}</div>
</main>
"""
    (lines_dir / "index.html").write_text(page_shell("研究线", index_body), encoding="utf-8")


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
    <a class="stat" href="dashboard.html">管理控制台</a>
    <span class="stat">分类 {len(grouped)}</span>
    <span class="stat">论文 {len(papers)}</span>
  </div>
</header>
<main class="shell">{content}</main>
"""
    (report_dir / "tags.html").write_text(page_shell("分类总览", body), encoding="utf-8")


def main() -> None:
    args = parse_args()
    report_dir = Path(args.report_dir).expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    papers = collect_papers(report_dir)
    write_json(report_dir, papers)
    write_search_index(report_dir, papers)
    render_index(report_dir, papers)
    render_dashboard(report_dir, papers)
    render_line_pages(report_dir, papers)
    render_tags(report_dir, papers)
    rel = report_dir.relative_to(ROOT) if report_dir.is_relative_to(ROOT) else report_dir
    print(f"Built wiki for {len(papers)} papers in {rel}")


if __name__ == "__main__":
    main()
