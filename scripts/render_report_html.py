#!/usr/bin/env python3
"""Render one markdown paper report into a standalone HTML reader page.

This is a fallback renderer for cases where the html-presenter agent is not
available. It preserves the markdown report as the source of truth and uses CDN
libraries in the generated page for markdown, math, code, and the mindmap.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a paper markdown report to HTML")
    parser.add_argument("report_md_path")
    parser.add_argument("report_html_path")
    parser.add_argument("--slug", default="")
    return parser.parse_args()


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
                existing.append(clean_scalar(item[2:].strip()))
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
            data[key] = [clean_scalar(part.strip()) for part in value[1:-1].split(",") if part.strip()]
        else:
            data[key] = clean_scalar(value)
    return data


def clean_scalar(value: str) -> Any:
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    return value


def strip_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    return parse_simple_yaml(text[4:end].strip()), text[end + len("\n---") :].lstrip("\n")


def as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def fix_markdown_paths(markdown: str, html_path: Path) -> str:
    # Reports conventionally write image paths as project-root-relative
    # `sources/<slug>/...`; HTML lives in docs/, so compute the real relative path.
    def repl(match: re.Match[str]) -> str:
        raw_path = match.group(1)
        source_path = ROOT / raw_path
        try:
            rel = source_path.relative_to(html_path.parent.resolve())
        except ValueError:
            rel = Path("..") / raw_path
        return f"]({rel.as_posix()}"

    return re.sub(r"\]\((sources/[^)\s]+)", repl, markdown)


def copy_local_assets(markdown: str, html_path: Path, slug: str) -> str:
    """Copy local report figures next to the HTML and rewrite image links.

    The markdown reports point at project-root `sources/...` paths. That works
    inside the repository but breaks when `docs/` is served as a standalone wiki.
    Copying referenced figures into `docs/assets/<slug>/` keeps HTML pages stable
    without changing the markdown source report.
    """
    asset_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}
    assets_dir = html_path.parent / "assets" / slug
    assets_dir.mkdir(parents=True, exist_ok=True)

    def repl(match: re.Match[str]) -> str:
        prefix, raw_path, suffix = match.group(1), match.group(2), match.group(3)
        if raw_path.startswith(("http://", "https://", "data:")):
            return match.group(0)
        if Path(raw_path).suffix.lower() not in asset_suffixes:
            return match.group(0)

        candidates = []
        path = Path(raw_path)
        if raw_path.startswith("../"):
            candidates.append((html_path.parent / path).resolve())
            candidates.append((ROOT / raw_path.removeprefix("../")).resolve())
        elif raw_path.startswith("sources/"):
            candidates.append((ROOT / path).resolve())
        else:
            candidates.append((html_path.parent / path).resolve())

        asset_path = next((candidate for candidate in candidates if candidate.exists()), None)
        if asset_path is None:
            return match.group(0)

        target = assets_dir / asset_path.name
        if not target.exists() or target.stat().st_size != asset_path.stat().st_size:
            shutil.copy2(asset_path, target)
        rel = target.relative_to(html_path.parent).as_posix()
        return f"{prefix}{rel}{suffix}"

    return re.sub(r"(!\[[^\]]*\]\()([^)\s]+)(\))", repl, markdown)


def protect_display_math(markdown: str) -> str:
    """Convert $$ blocks to explicit placeholders rendered by KaTeX later.

    marked + KaTeX auto-render is fragile for multiline display math when the
    markdown parser has already wrapped pieces into paragraphs. Explicit blocks
    make the output stable and keep bad formulas localized.
    """

    def repl(match: re.Match[str]) -> str:
        latex = match.group(1).strip()
        if not latex:
            return ""
        return f'\n<div class="math-display">{html.escape(latex)}</div>\n'

    return re.sub(r"(?s)\$\$\s*(.*?)\s*\$\$", repl, markdown)


def protect_inline_math(markdown: str) -> str:
    """Protect single-dollar inline math before Markdown emphasis parsing.

    The markdown parser runs before KaTeX in the browser. Without protection,
    expressions such as `$\\mathbf{K}_{\\text{AR}}$` can be split by `_..._`
    emphasis and become impossible for KaTeX to recover.
    """

    fence_re = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")
    code_re = re.compile(r"(`+)([\s\S]*?)(\1)")
    math_re = re.compile(r"(?<!\\)(?<!\$)\$([^\n$]+?)(?<!\\)\$(?!\$)")

    def protect_text(text: str) -> str:
        def math_repl(match: re.Match[str]) -> str:
            latex = match.group(1).strip()
            if not latex:
                return match.group(0)
            escaped = html.escape(latex, quote=True)
            return f'<span class="math-inline" data-tex="{escaped}"></span>'

        parts = code_re.split(text)
        out: list[str] = []
        i = 0
        while i < len(parts):
            if i + 2 < len(parts) and parts[i].startswith("`"):
                out.extend(parts[i : i + 3])
                i += 3
            else:
                out.append(math_re.sub(math_repl, parts[i]))
                i += 1
        return "".join(out)

    segments = fence_re.split(markdown)
    for idx in range(0, len(segments), 2):
        segments[idx] = protect_text(segments[idx])
    return "".join(segments)


def infer_title(body: str, meta: dict[str, Any]) -> str:
    title = str(meta.get("title_zh") or meta.get("title") or "").strip()
    if title:
        return title
    match = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else "论文阅读报告"


def build_mindmap(slug: str, meta: dict[str, Any]) -> str:
    title = str(meta.get("title_zh") or meta.get("title") or slug or "论文").strip()
    if "flashinfer" in slug.lower() or "FlashInfer" in str(meta.get("title", "")):
        return """# FlashInfer
## Serving 瓶颈
- 短 Q 长 KV
- 动态请求
- KV-cache 异构
## 统一表示
- BSR page table
- composable formats
- shared prefix
## Kernel 定制
- FA2/FA3 模板
- JIT functor
- RoPE 融合
## 动态调度
- plan/run 分离
- split-KV
- CUDA Graph
## 实验证据
- SGLang serving
- 变长 benchmark
- parallel generation
## 工程核对
- paged wrapper
- cascade merge
- 多 backend"""
    if "flashattention" in slug.lower() or "FlashAttention" in str(meta.get("title", "")):
        return f"""# FlashAttention-2
## 问题定位
- long context 瓶颈
- exact attention
- v1 未吃满算力
## 方法核心
- 少做 non-matmul
- sequence 并行
- warp 重分工
## GPU 视角
- A100 SM occupancy
- shared memory 通信
- GEMM 利用率
## 实验闭环
- attention benchmark
- H100 初测
- GPT-style 训练
## 工程观察
- CUDA/CUTLASS kernel
- ROCm/后续扩展
- 复现门槛"""
    return f"""# {title}
## 研究问题
- 动机
- 关键瓶颈
## 方法设计
- 核心算法
- 关键公式
## 实验验证
- 数据集
- baseline
- ablation
## 批判视角
- 前作关系
- 局限
## 代码实现
- 工程约束
- 可复现性"""


def parse_mindmap(markdown: str) -> tuple[str, list[tuple[str, list[str]]]]:
    root = "内容脑图"
    branches: list[tuple[str, list[str]]] = []
    current_title = ""
    current_items: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# ") and not line.startswith("## "):
            root = line[2:].strip() or root
            continue
        if line.startswith("## "):
            if current_title:
                branches.append((current_title, current_items))
            current_title = line[3:].strip()
            current_items = []
            continue
        if line.startswith("- ") and current_title:
            current_items.append(line[2:].strip())
    if current_title:
        branches.append((current_title, current_items))
    return root, branches


def render_mindmap_overview(markdown: str) -> str:
    root, branches = parse_mindmap(markdown)
    if not branches:
        return ""
    branch_html = []
    for title, items in branches:
        leaves = "".join(f"<li>{html.escape(item)}</li>" for item in items)
        branch_html.append(
            f"""<article class="mind-branch">
  <h3>{html.escape(title)}</h3>
  <ul>{leaves}</ul>
</article>"""
        )
    return f"""<div class="mind-overview">
  <div class="mind-root">{html.escape(root)}</div>
  <div class="mind-branches">{''.join(branch_html)}</div>
</div>"""


def render_html(meta: dict[str, Any], markdown: str, slug: str) -> str:
    title = infer_title(markdown, meta)
    title_en = str(meta.get("title_en") or meta.get("title") or "").strip()
    authors = ", ".join(as_list(meta.get("authors"))) or "Unknown"
    arxiv_id = str(meta.get("arxiv_id") or "").strip()
    arxiv_base = re.sub(r"v\d+$", "", arxiv_id)
    arxiv_url = f"https://arxiv.org/abs/{arxiv_base}" if arxiv_base else ""
    code_match = re.search(r"https://github\.com/[^\s)）]+", markdown)
    code_url = code_match.group(0) if code_match else ""
    if not code_url and slug == "2307.08691-flashattention-2":
        code_url = "https://github.com/Dao-AILab/flash-attention"
    project_match = re.search(r"https?://flashinfer\.ai[^\s)）]*", markdown)
    project_url = project_match.group(0) if project_match else ""
    topics = as_list(meta.get("topics"))
    methods = as_list(meta.get("methods"))
    year = str(meta.get("year") or "").strip()
    submitted_match = re.search(r"arXiv 编号与日期[：:][^\n；;]*[；;]\s*([^\n]+)", markdown)
    submitted = submitted_match.group(1).strip() if submitted_match else ""
    mindmap = build_mindmap(slug, meta)

    payload = {
        "markdown": markdown,
        "mindmap": mindmap,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    chips = "".join(f"<span>{html.escape(tag)}</span>" for tag in [*topics, *methods])
    mindmap_overview = render_mindmap_overview(mindmap)
    links = []
    if arxiv_url:
        links.append(f'<a class="hero-link" href="{html.escape(arxiv_url)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3h7v7h-2V6.41l-9.29 9.3-1.42-1.42 9.3-9.29H14V3Z"></path><path d="M5 5h6v2H7v10h10v-4h2v6H5V5Z"></path></svg>arxiv</a>')
    if code_url:
        links.append(f'<a class="hero-link" href="{html.escape(code_url)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8.7 16.6-5-4.6 5-4.6 1.35 1.48L6.66 12l3.39 3.12L8.7 16.6Zm6.6 0-1.35-1.48L17.34 12l-3.39-3.12L15.3 7.4l5 4.6-5 4.6Z"></path></svg>code</a>')
    if project_url:
        links.append(f'<a class="hero-link" href="{html.escape(project_url)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2Zm6.93 9h-3.02a15.8 15.8 0 0 0-1.13-5.06A8.02 8.02 0 0 1 18.93 11ZM12 4.04c.82 1.14 1.57 3.37 1.82 6.96h-3.64c.25-3.59 1-5.82 1.82-6.96ZM4.07 13h3.02c.18 1.94.58 3.72 1.13 5.06A8.02 8.02 0 0 1 4.07 13Zm3.02-2H4.07a8.02 8.02 0 0 1 4.15-5.06A15.8 15.8 0 0 0 7.09 11ZM12 19.96c-.82-1.14-1.57-3.37-1.82-6.96h3.64c-.25 3.59-1 5.82-1.82 6.96Zm3.78-1.9c.55-1.34.95-3.12 1.13-5.06h3.02a8.02 8.02 0 0 1-4.15 5.06Z"></path></svg>project</a>')
    link_html = "\n        ".join(links)

    template = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__TITLE__</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/highlight.js@11.11.1/styles/github.min.css">
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f7f8;
      --paper: #ffffff;
      --ink: #22262a;
      --muted: #667078;
      --line: #d8e0e5;
      --accent: #2c6e73;
      --accent-2: #6f5b8a;
      --soft: #e7f0ed;
      --soft-2: #eef0f5;
      --shadow: 0 18px 45px rgba(31, 44, 52, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "PingFang SC", "Noto Sans SC", system-ui, -apple-system, sans-serif;
      line-height: 1.72;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .shell { width: min(1120px, calc(100% - 32px)); margin: 0 auto; }
    .hero { padding: 16px 0 20px; }
    .crumb { display: none; }
    h1 { margin: 0 0 8px; font-size: clamp(30px, 5vw, 52px); line-height: 1.1; letter-spacing: 0; }
    .subtitle { max-width: 820px; color: var(--muted); font-size: 18px; margin: 0; }
    .meta-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0 0; }
    .pill, .hero-link {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--paper);
      padding: 0 12px;
      font-size: 14px;
      color: var(--muted);
    }
    .hero-link { color: var(--accent); font-weight: 700; }
    .hero-link svg {
      width: 15px;
      height: 15px;
      margin-right: 6px;
      fill: currentColor;
      flex: 0 0 auto;
    }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
    .chips span {
      border: 1px solid #cfdedc;
      background: var(--soft);
      color: #33595d;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 13px;
    }
    .panel {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .mindmap-panel { padding: 22px; margin: 14px auto 18px; }
    .panel-title { margin: 0 0 10px; font-size: 18px; }
    .mind-overview {
      display: grid;
      grid-template-columns: minmax(180px, .42fr) 1fr;
      gap: 16px;
      align-items: stretch;
    }
    .mind-root {
      min-height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      text-align: center;
      border-radius: 8px;
      border: 1px solid #cbdeda;
      background: linear-gradient(180deg, #edf7f5, #ffffff);
      color: #234e52;
      font-size: clamp(20px, 2.4vw, 28px);
      font-weight: 800;
      line-height: 1.15;
      padding: 20px;
    }
    .mind-branches {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }
    .mind-branch {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      padding: 12px;
      min-height: 132px;
    }
    .mind-branch h3 {
      margin: 0 0 6px;
      font-size: 16px;
      color: var(--accent);
    }
    .mind-branch ul {
      margin: 0;
      padding-left: 1.1em;
      color: #4a5358;
      font-size: 13.5px;
      line-height: 1.5;
    }
    .mindmap-toggle {
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
      overflow: hidden;
    }
    .mindmap-toggle summary {
      cursor: pointer;
      padding: 10px 14px;
      color: var(--accent);
      font-weight: 700;
      list-style: none;
    }
    .mindmap-toggle summary::-webkit-details-marker { display: none; }
    .markmap {
      height: 520px;
      border-top: 1px solid var(--line);
      background: #fffdf8;
      overflow: hidden;
      pointer-events: none;
      user-select: none;
    }
    .markmap svg {
      width: 100%;
      height: 520px;
      display: block;
      pointer-events: none;
    }
    .reader-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(210px, 248px);
      gap: 14px;
      align-items: start;
      padding-bottom: 56px;
      transition: grid-template-columns .18s ease;
    }
    .reader-layout.sidebar-collapsed {
      grid-template-columns: minmax(0, 1fr) 44px;
    }
    .side-toc {
      grid-column: 2;
      grid-row: 1;
      position: sticky;
      top: 64px;
      max-height: calc(100vh - 84px);
      overflow: hidden;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .side-toggle {
      width: 100%;
      min-height: 44px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
      color: var(--accent);
      padding: 0 12px;
      font: inherit;
      font-size: 14px;
      font-weight: 750;
      cursor: pointer;
    }
    .side-toggle-icon {
      width: 20px;
      height: 20px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: #fff;
      flex: 0 0 auto;
    }
    .side-toc nav {
      max-height: calc(100vh - 130px);
      overflow-y: auto;
      padding: 8px;
    }
    .side-toc a {
      display: block;
      border-radius: 7px;
      border: 1px solid transparent;
      padding: 8px 10px;
      color: #405059;
      font-size: 13px;
      line-height: 1.35;
    }
    .side-toc a:hover,
    .side-toc a.is-active {
      background: var(--soft);
      text-decoration: none;
      border-color: #cbdeda;
      color: #234e52;
    }
    .side-toc.is-collapsed .side-toggle {
      width: 44px;
      height: 44px;
      min-height: 44px;
      justify-content: center;
      border-bottom: 0;
      padding: 0;
    }
    .side-toc.is-collapsed {
      width: 44px;
      height: 44px;
      justify-self: end;
    }
    .side-toc.is-collapsed nav,
    .side-toc.is-collapsed .side-toggle-text {
      display: none;
    }
    .article { grid-column: 1; grid-row: 1; min-width: 0; }
    .report-section {
      margin: 16px 0;
      padding: 22px;
      border-left: 5px solid var(--accent);
      background: var(--paper);
      border-radius: 8px;
      border-top: 1px solid var(--line);
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      box-shadow: var(--shadow);
    }
    .report-section:nth-of-type(3) {
      border-left-color: #6f5b8a;
      background: linear-gradient(90deg, #f4f0fa 0, #fff 140px);
    }
    .report-section:nth-of-type(7) {
      border-left-color: #9a623d;
      background: linear-gradient(90deg, #f7f1ed 0, #fff 160px);
    }
    .report-section:nth-of-type(10) {
      border-left-color: #3f6c88;
      background: linear-gradient(90deg, #eef4f8 0, #fff 160px);
    }
    details.report-section { padding: 0; overflow: hidden; }
    details.report-section summary {
      cursor: pointer;
      list-style: none;
      padding: 18px 22px;
      font-size: 22px;
      font-weight: 760;
      line-height: 1.25;
    }
    details.report-section summary::-webkit-details-marker { display: none; }
    details.report-section summary::after {
      content: "收起";
      float: right;
      color: var(--muted);
      font-size: 13px;
      font-weight: 500;
      margin-top: 5px;
    }
    .report-section > h2,
    details.report-section > summary {
      scroll-margin-top: 96px;
    }
    details.report-section:not([open]) summary::after { content: "展开"; }
    .section-body { padding: 0 22px 22px; }
    .article > h1 {
      margin: 18px 0;
      padding: 18px 22px;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      font-size: clamp(24px, 3vw, 34px);
    }
    h2, h3 { letter-spacing: 0; line-height: 1.32; }
    h2 { margin: 0 0 12px; font-size: 24px; }
    h3 { margin: 22px 0 8px; font-size: 19px; color: #293d42; }
    p { margin: 10px 0; }
    ul, ol { padding-left: 1.4em; }
    li { margin: 5px 0; }
    blockquote {
      margin: 14px 0;
      padding: 10px 14px;
      border-left: 4px solid var(--accent-2);
      background: var(--soft-2);
      color: #51483f;
      border-radius: 6px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      overflow: hidden;
      border-radius: 8px;
      display: block;
      overflow-x: auto;
    }
    th, td { border: 1px solid var(--line); padding: 8px 10px; text-align: left; }
    th { background: #edf3f1; }
    pre {
      padding: 14px;
      overflow-x: auto;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: #f7f7f5;
    }
    code {
      font-family: "JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: .92em;
    }
    :not(pre) > code {
      background: #eef1ef;
      border-radius: 5px;
      padding: 1px 5px;
    }
    .math-inline {
      display: inline-block;
      max-width: 100%;
      vertical-align: baseline;
    }
    img, object.figure-pdf {
      max-width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      display: block;
      margin: 14px auto;
    }
    img.media-thumb { cursor: zoom-in; }
    object.figure-pdf { width: 100%; min-height: 420px; }
    .figure-fallback { display: block; margin: 8px 0 16px; font-size: 13px; color: var(--muted); }
    .figure-open {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--paper);
      color: var(--accent);
      padding: 0 12px;
      font: inherit;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }
    .figure-open:hover { background: var(--soft); }
    .media-viewer {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      background: rgba(28, 31, 32, .72);
      padding: 22px;
    }
    .media-viewer.is-open {
      display: grid;
      place-items: center;
    }
    .media-dialog {
      position: relative;
      width: min(1180px, 96vw);
      height: min(860px, 92vh);
      border-radius: 8px;
      background: var(--paper);
      border: 1px solid var(--line);
      box-shadow: 0 24px 70px rgba(0, 0, 0, .28);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      overflow: hidden;
    }
    .media-bar {
      min-height: 46px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding: 0 10px 0 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .media-title {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .media-close {
      width: 34px;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      font-size: 22px;
      line-height: 1;
      cursor: pointer;
    }
    .media-close:hover { background: var(--soft); }
    .media-content {
      min-height: 0;
      overflow: auto;
      padding: 14px;
      display: grid;
      place-items: center;
      background: #f3f6f8;
    }
    .media-content img {
      max-width: 100%;
      max-height: calc(92vh - 88px);
      object-fit: contain;
      margin: 0;
      cursor: default;
    }
    .media-content iframe {
      width: 100%;
      height: 100%;
      border: 0;
      background: #fff;
      border-radius: 6px;
    }
    body.media-viewer-open { overflow: hidden; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 2;
      background: color-mix(in srgb, var(--bg) 88%, transparent);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid color-mix(in srgb, var(--line) 75%, transparent);
    }
    .topbar-inner { min-height: 42px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
    .topbar a,
    .topbar button {
      border: 0;
      background: transparent;
      color: var(--accent);
      padding: 0;
      font: inherit;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .topbar button:hover { text-decoration: underline; }
    @media (max-width: 960px) {
      .reader-layout,
      .reader-layout.sidebar-collapsed {
        display: block;
      }
      .side-toc {
        position: sticky;
        top: 42px;
        z-index: 1;
        margin-bottom: 16px;
        max-height: none;
        width: auto;
        height: auto;
        justify-self: stretch;
      }
      .side-toc nav {
        display: flex;
        gap: 8px;
        overflow-x: auto;
        overflow-y: hidden;
        max-height: none;
        padding: 8px;
      }
      .side-toc a {
        white-space: nowrap;
        border: 1px solid var(--line);
        background: #fff;
      }
      .side-toc.is-collapsed .side-toggle {
        width: 100%;
        height: auto;
        min-height: 44px;
        justify-content: space-between;
        border-bottom: 0;
        padding: 0 12px;
      }
      .side-toc.is-collapsed {
        width: auto;
        height: auto;
      }
      .side-toc.is-collapsed .side-toggle-text {
        display: inline;
      }
    }
    @media (max-width: 760px) {
      .hero { padding-top: 12px; }
      .report-section { padding: 16px; }
      details.report-section summary { padding: 15px 16px; font-size: 19px; }
      .section-body { padding: 0 16px 16px; }
      .mind-overview { grid-template-columns: 1fr; }
      .mind-root { min-height: 120px; }
      .markmap, .markmap svg { height: 360px; }
    }
  </style>
</head>
<body>
  <script>
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    if (window.location.hash === "#side-toc") {
      history.replaceState(null, "", window.location.pathname + window.location.search);
      window.scrollTo(0, 0);
    }
  </script>
  <div class="topbar">
    <div class="shell topbar-inner">
      <a href="index.html">论文 wiki</a>
      <button id="topbar-toc-toggle" type="button">目录</button>
    </div>
  </div>
  <header class="shell hero">
    <div class="crumb">Paper Reading Report</div>
    <h1>__TITLE__</h1>
    <p class="subtitle">__TITLE_EN__</p>
    <div class="meta-row">
      <span class="pill">__AUTHORS__</span>
      <span class="pill">__YEAR__</span>
      <span class="pill">__ARXIV__</span>
      __SUBMITTED__
      __LINKS__
    </div>
    <div class="chips">__CHIPS__</div>
  </header>
  <section class="shell panel mindmap-panel">
    <h2 class="panel-title">内容脑图</h2>
    __MINDMAP_OVERVIEW__
    <details class="mindmap-toggle">
      <summary>交互脑图</summary>
      <div class="markmap"><script type="text/template">__MINDMAP__</script></div>
    </details>
  </section>
  <div class="shell reader-layout" id="reader-layout">
    <aside class="side-toc" id="paper-side-toc">
      <button class="side-toggle" id="side-toggle" type="button" aria-label="收起目录" title="收起目录">
        <span class="side-toggle-text">目录</span>
        <span class="side-toggle-icon" aria-hidden="true">›</span>
      </button>
      <nav id="side-links" aria-label="章节目录"></nav>
    </aside>
    <main class="article" id="article"></main>
  </div>
  <div class="media-viewer" id="media-viewer" aria-hidden="true">
    <div class="media-dialog" role="dialog" aria-modal="true" aria-labelledby="media-title">
      <div class="media-bar">
        <div class="media-title" id="media-title">图表预览</div>
        <button class="media-close" id="media-close" type="button" aria-label="关闭预览" title="关闭预览">×</button>
      </div>
      <div class="media-content" id="media-content"></div>
    </div>
  </div>
  <script>window.REPORT_PAYLOAD = __PAYLOAD__;</script>
  <script src="https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.2.6/dist/purify.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/contrib/auto-render.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.11.1/build/highlight.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18.12"></script>
  <script>
    marked.setOptions({ gfm: true, breaks: false });
    const article = document.querySelector("#article");
    article.innerHTML = DOMPurify.sanitize(marked.parse(window.REPORT_PAYLOAD.markdown));

    function slugify(text, index) {
      return "sec-" + index + "-" + text.trim().toLowerCase()
        .replace(/[^\w\u4e00-\u9fa5]+/g, "-")
        .replace(/^-+|-+$/g, "");
    }

    function sectionize() {
      const original = Array.from(article.childNodes);
      article.innerHTML = "";
      let current = null;
      let index = 0;
      for (const node of original) {
        if (node.nodeType === 1 && node.tagName === "H2") {
          index += 1;
          const title = node.textContent.trim();
          const id = slugify(title, index);
          node.id = id;
          if (index <= 4) {
            current = document.createElement("section");
            current.className = "report-section";
            current.appendChild(node);
          } else {
            current = document.createElement("details");
            current.className = "report-section";
            current.open = true;
            const summary = document.createElement("summary");
            summary.textContent = title;
            summary.id = id;
            const body = document.createElement("div");
            body.className = "section-body";
            current.appendChild(summary);
            current.appendChild(body);
          }
          article.appendChild(current);
          const sideLink = document.createElement("a");
          sideLink.href = "#" + id;
          sideLink.textContent = title;
          sideLink.dataset.target = id;
          document.querySelector("#side-links").appendChild(sideLink);
          continue;
        }
        if (current) {
          const body = current.querySelector(".section-body") || current;
          body.appendChild(node);
        } else {
          article.appendChild(node);
        }
      }
    }

    function setupSidebar() {
      const layout = document.querySelector("#reader-layout");
      const sidebar = document.querySelector("#paper-side-toc");
      const button = document.querySelector("#side-toggle");
      const icon = button.querySelector(".side-toggle-icon");
      const topbarToggle = document.querySelector("#topbar-toc-toggle");
      const sideNav = document.querySelector("#side-links");
      const links = Array.from(document.querySelectorAll("#side-links a"));

      if (window.location.hash === "#side-toc") {
        history.replaceState(null, "", window.location.pathname + window.location.search);
        window.scrollTo({ top: 0, behavior: "auto" });
      }

      function readSavedState() {
        try {
          return window.localStorage && window.localStorage.getItem("paper-sidebar-collapsed") === "true";
        } catch {
          return false;
        }
      }

      function writeSavedState(collapsed) {
        try {
          if (window.localStorage) {
            window.localStorage.setItem("paper-sidebar-collapsed", String(collapsed));
          }
        } catch {
          // Storage can be unavailable in restricted browser contexts.
        }
      }

      function setCollapsed(collapsed) {
        layout.classList.toggle("sidebar-collapsed", collapsed);
        sidebar.classList.toggle("is-collapsed", collapsed);
        button.setAttribute("aria-label", collapsed ? "展开目录" : "收起目录");
        button.setAttribute("title", collapsed ? "展开目录" : "收起目录");
        if (icon) icon.textContent = collapsed ? "‹" : "›";
        writeSavedState(collapsed);
      }

      setCollapsed(readSavedState());
      button.addEventListener("click", () => setCollapsed(!sidebar.classList.contains("is-collapsed")));
      if (topbarToggle) {
        topbarToggle.addEventListener("click", () => {
          if (window.location.hash === "#side-toc") {
            history.replaceState(null, "", window.location.pathname + window.location.search);
          }
          setCollapsed(!sidebar.classList.contains("is-collapsed"));
        });
      }

      const targets = links
        .map(link => document.getElementById(link.dataset.target))
        .filter(Boolean);

      function setActive(id) {
        links.forEach(link => link.classList.toggle("is-active", link.dataset.target === id));
        const activeLink = links.find(link => link.dataset.target === id);
        if (activeLink && sideNav && !sidebar.classList.contains("is-collapsed")) {
          const linkTop = activeLink.offsetTop;
          const linkBottom = linkTop + activeLink.offsetHeight;
          const navTop = sideNav.scrollTop;
          const navBottom = navTop + sideNav.clientHeight;
          if (linkTop < navTop) {
            sideNav.scrollTop = Math.max(linkTop - 8, 0);
          } else if (linkBottom > navBottom) {
            sideNav.scrollTop = linkBottom - sideNav.clientHeight + 8;
          }
        }
      }

      function updateActiveFromScroll() {
        if (!targets.length) return;
        const offset = 150;
        let active = targets[0];
        for (const target of targets) {
          if (target.getBoundingClientRect().top <= offset) {
            active = target;
          } else {
            break;
          }
        }
        setActive(active.id);
      }

      let ticking = false;
      function requestActiveUpdate() {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(() => {
          ticking = false;
          updateActiveFromScroll();
        });
      }

      links.forEach(link => {
        link.addEventListener("click", event => {
          event.preventDefault();
          const target = document.getElementById(link.dataset.target);
          if (!target) return;
          const parentDetails = target.closest("details.report-section");
          if (parentDetails) parentDetails.open = true;
          setActive(target.id);
          history.pushState(null, "", "#" + target.id);
          target.scrollIntoView({ block: "start", behavior: "auto" });
          if (window.matchMedia("(max-width: 960px)").matches) {
            setCollapsed(true);
          }
          window.setTimeout(updateActiveFromScroll, 80);
        });
      });

      window.addEventListener("scroll", requestActiveUpdate, { passive: true });
      window.addEventListener("resize", requestActiveUpdate);
      window.addEventListener("hashchange", () => {
        const id = decodeURIComponent(window.location.hash.slice(1));
        if (id && document.getElementById(id)) setActive(id);
        window.setTimeout(updateActiveFromScroll, 80);
      });
      if (window.location.hash) {
        const id = decodeURIComponent(window.location.hash.slice(1));
        if (id && document.getElementById(id)) setActive(id);
      } else if (links[0]) {
        setActive(links[0].dataset.target);
      }
      updateActiveFromScroll();
    }

    function setupMediaViewer() {
      const viewer = document.querySelector("#media-viewer");
      const content = document.querySelector("#media-content");
      const title = document.querySelector("#media-title");
      const closeButton = document.querySelector("#media-close");
      if (!viewer || !content || !title || !closeButton) return null;

      function close() {
        viewer.classList.remove("is-open");
        viewer.setAttribute("aria-hidden", "true");
        document.body.classList.remove("media-viewer-open");
        content.innerHTML = "";
      }

      function open(src, type, label) {
        content.innerHTML = "";
        title.textContent = label || (type === "pdf" ? "PDF 图表" : "图表预览");
        if (type === "pdf") {
          const frame = document.createElement("iframe");
          frame.src = src;
          frame.title = title.textContent;
          content.appendChild(frame);
        } else {
          const image = document.createElement("img");
          image.src = src;
          image.alt = label || "图表预览";
          content.appendChild(image);
        }
        viewer.classList.add("is-open");
        viewer.setAttribute("aria-hidden", "false");
        document.body.classList.add("media-viewer-open");
        closeButton.focus({ preventScroll: true });
      }

      closeButton.addEventListener("click", close);
      viewer.addEventListener("click", event => {
        if (event.target === viewer) close();
      });
      window.addEventListener("keydown", event => {
        if (event.key === "Escape" && viewer.classList.contains("is-open")) close();
      });

      return { open, close };
    }

    function enhanceLinks() {
      const mediaViewer = setupMediaViewer();
      article.querySelectorAll("a[href]").forEach(a => {
        const href = a.getAttribute("href") || "";
        if (/^https?:\/\//.test(href)) a.target = "_blank";
      });
      article.querySelectorAll("img").forEach(img => {
        const src = img.getAttribute("src") || "";
        img.decoding = "async";
        img.onerror = () => {
          if (src.startsWith("../sources/")) {
            img.src = src.replace("../sources/", "sources/");
          }
        };
        if (src.endsWith(".pdf")) {
          const object = document.createElement("object");
          object.className = "figure-pdf";
          object.type = "application/pdf";
          object.data = src;
          const fallback = document.createElement("button");
          fallback.className = "figure-open";
          fallback.type = "button";
          fallback.textContent = "放大查看 PDF";
          fallback.addEventListener("click", () => {
            if (mediaViewer) mediaViewer.open(src, "pdf", img.getAttribute("alt") || "PDF 图表");
          });
          img.replaceWith(object);
          object.insertAdjacentElement("afterend", fallback);
        } else {
          img.classList.add("media-thumb");
          img.setAttribute("tabindex", "0");
          img.setAttribute("role", "button");
          img.setAttribute("title", "点击放大查看");
          const openImage = () => {
            if (mediaViewer) mediaViewer.open(img.currentSrc || img.src, "image", img.getAttribute("alt") || "图表预览");
          };
          img.addEventListener("click", openImage);
          img.addEventListener("keydown", event => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              openImage();
            }
          });
        }
      });
    }

    function linkifyArxivIds(root) {
      const re = /(?<![\w/.-])(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?(?![\w/.-])/g;
      const skipTags = new Set(["A", "CODE", "PRE", "SCRIPT", "STYLE", "TEXTAREA"]);
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!parent || skipTags.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
          re.lastIndex = 0;
          return re.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
      });
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(node => {
        re.lastIndex = 0;
        const frag = document.createDocumentFragment();
        let last = 0;
        for (const match of node.nodeValue.matchAll(re)) {
          frag.appendChild(document.createTextNode(node.nodeValue.slice(last, match.index)));
          const link = document.createElement("a");
          link.href = "https://arxiv.org/abs/" + match[1];
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = match[0];
          frag.appendChild(link);
          last = match.index + match[0].length;
        }
        frag.appendChild(document.createTextNode(node.nodeValue.slice(last)));
        node.replaceWith(frag);
      });
    }

    function renderDisplayMath() {
      article.querySelectorAll(".math-display").forEach(el => {
        const source = el.textContent.trim();
        try {
          katex.render(source, el, { displayMode: true, throwOnError: false });
        } catch (error) {
          el.classList.add("math-error");
          el.textContent = source;
        }
      });
    }

    function renderInlineMath() {
      article.querySelectorAll(".math-inline").forEach(el => {
        const source = el.getAttribute("data-tex") || el.textContent.trim();
        try {
          katex.render(source, el, { displayMode: false, throwOnError: false });
        } catch (error) {
          el.classList.add("math-error");
          el.textContent = source;
        }
      });
    }

    sectionize();
    setupSidebar();
    enhanceLinks();
    linkifyArxivIds(article);
    renderDisplayMath();
    renderInlineMath();
    renderMathInElement(article, {
      delimiters: [
        { left: "$", right: "$", display: false }
      ],
      ignoredClasses: ["math-display", "math-inline"],
      throwOnError: false
    });
    if (window.hljs) {
      hljs.highlightAll();
    }
  </script>
</body>
</html>
"""
    replacements = {
        "__TITLE__": html.escape(title),
        "__TITLE_EN__": html.escape(title_en),
        "__AUTHORS__": html.escape(authors),
        "__YEAR__": html.escape(year),
        "__ARXIV__": html.escape(arxiv_id),
        "__SUBMITTED__": f'<span class="pill">{html.escape(submitted)}</span>' if submitted else "",
        "__LINKS__": link_html,
        "__CHIPS__": chips,
        "__MINDMAP_OVERVIEW__": mindmap_overview,
        "__MINDMAP__": html.escape(mindmap),
        "__PAYLOAD__": payload_json,
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def main() -> None:
    args = parse_args()
    md_path = Path(args.report_md_path).expanduser()
    if not md_path.is_absolute():
        md_path = ROOT / md_path
    html_path = Path(args.report_html_path).expanduser()
    if not html_path.is_absolute():
        html_path = ROOT / html_path

    text = md_path.read_text(encoding="utf-8")
    meta, body = strip_frontmatter(text)
    slug = args.slug or str(meta.get("slug") or md_path.stem)
    body = fix_markdown_paths(body, html_path)
    body = copy_local_assets(body, html_path, slug)
    body = protect_display_math(body)
    body = protect_inline_math(body)
    html_text = render_html(meta, body, slug)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html_text, encoding="utf-8")
    rel = html_path.relative_to(ROOT) if html_path.is_relative_to(ROOT) else html_path
    print(f"Rendered {rel}")


if __name__ == "__main__":
    main()
