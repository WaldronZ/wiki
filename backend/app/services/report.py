from __future__ import annotations

import re
import subprocess
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from ..config import AppConfig
from .arxiv import ArxivMetadata
from .llm import LLMProvider


REQUIRED_FRONTMATTER = {
    "slug",
    "title",
    "title_zh",
    "title_en",
    "arxiv_id",
    "year",
    "authors",
    "topics",
    "methods",
    "research_line",
    "line_role",
    "status",
    "importance",
    "has_code",
}

REQUIRED_SECTIONS = [
    "## 1. 基本情况",
    "## 2. 核心贡献概述",
    "## 3. 一句话精髓",
    "## 4. 学术贡献清单",
    "## 5. 写作故事线",
    "## 6. 核心参考文献",
    "## 7. 批判性分析",
    "## 8. 方法细节",
    "## 9. 实验",
]

REPORT_PROMPT_VERSION = "report:paper-analyst-deep-v1"


@dataclass(frozen=True)
class ReportContext:
    slug: str
    metadata: ArxivMetadata
    source_dir: Path
    main_tex_path: Path | None
    report_md_path: Path
    report_html_path: Path


@dataclass(frozen=True)
class ReportMaterials:
    analyst_contract: str
    memory_context: str
    source_context: str
    figure_context: str
    bibliography_context: str
    related_work_context: str
    pdf_fallback_path: str


@dataclass(frozen=True)
class ReportModelRun:
    stage: str
    prompt: str
    response: str = ""
    error: str = ""


@dataclass(frozen=True)
class ReportGenerationResult:
    markdown: str
    runs: list[ReportModelRun]


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def read_paper_analyst_contract() -> str:
    path = project_root() / ".Codex" / "agents" / "paper-analyst.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str(data.get("developer_instructions") or "").strip()


def read_agent_memory_context(*, max_chars: int = 24000) -> str:
    memory_dir = project_root() / "memory"
    if not memory_dir.exists():
        return ""
    chunks: list[str] = []
    remaining = max_chars
    for path in sorted(memory_dir.rglob("*.md")):
        if remaining <= 0:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text.strip():
            continue
        rel = path.relative_to(project_root()).as_posix()
        text = text[:remaining]
        chunks.append(f"<!-- MEMORY: {rel} -->\n{text}")
        remaining -= len(text)
    return "\n\n".join(chunks)


def _read_text(path: Path, *, max_chars: int | None = None) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars] if max_chars else text


def _included_tex_paths(tex_path: Path, source_dir: Path) -> list[Path]:
    text = _read_text(tex_path)
    paths: list[Path] = []
    for match in re.finditer(r"\\(?:input|include)\{([^}]+)\}", text):
        raw = match.group(1).strip()
        if not raw:
            continue
        candidate = Path(raw)
        candidates = [
            tex_path.parent / candidate,
            tex_path.parent / f"{raw}.tex",
            source_dir / candidate,
            source_dir / f"{raw}.tex",
        ]
        for item in candidates:
            resolved = item.resolve()
            if resolved.exists() and resolved.suffix.lower() == ".tex":
                paths.append(resolved)
                break
    return paths


def ordered_tex_files(source_dir: Path, main_tex_path: Path | None, *, max_files: int = 80) -> list[Path]:
    if not source_dir.exists():
        return []
    source_dir = source_dir.resolve()
    ordered: list[Path] = []
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen or len(ordered) >= max_files:
            return
        if not resolved.exists() or resolved.suffix.lower() != ".tex":
            return
        seen.add(resolved)
        ordered.append(resolved)
        for child in _included_tex_paths(resolved, source_dir):
            visit(child)

    if main_tex_path is not None:
        visit(main_tex_path)
    for tex_path in sorted(source_dir.rglob("*.tex")):
        visit(tex_path)
        if len(ordered) >= max_files:
            break
    return ordered


def read_source_context(
    source_dir: Path,
    main_tex_path: Path | None,
    *,
    max_chars: int = 120000,
    max_chars_per_file: int = 26000,
) -> str:
    if main_tex_path is None and not source_dir.exists():
        return ""
    chunks: list[str] = []
    remaining = max_chars
    for tex_path in ordered_tex_files(source_dir, main_tex_path):
        if remaining <= 0:
            break
        source_root = source_dir.resolve().parent.parent
        try:
            display_path = tex_path.resolve().relative_to(source_root).as_posix()
            display_path = f"{source_root.name}/{display_path}"
        except ValueError:
            display_path = tex_path.as_posix()
        text = _read_text(tex_path, max_chars=min(max_chars_per_file, remaining))
        chunks.append(f"% ===== FILE: {display_path} =====\n{text}")
        remaining -= len(text)
    return "\n\n".join(chunks)


def build_bibliography_context(source_dir: Path, *, max_chars: int = 26000) -> str:
    if not source_dir.exists():
        return ""
    chunks: list[str] = []
    remaining = max_chars
    for bib_path in sorted(source_dir.rglob("*.bib")):
        if remaining <= 0:
            break
        try:
            display_path = bib_path.relative_to(source_dir).as_posix()
        except ValueError:
            display_path = bib_path.as_posix()
        text = _read_text(bib_path, max_chars=min(remaining, 12000))
        chunks.append(f"% ===== BIB: {display_path} =====\n{text}")
        remaining -= len(text)
    return "\n\n".join(chunks)


def extract_external_arxiv_ids(*texts: str, current_arxiv_id: str = "", max_ids: int = 8) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    current = re.sub(r"v\d+$", "", current_arxiv_id.strip())
    for text in texts:
        for match in re.finditer(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", text or ""):
            arxiv_id = match.group(1)
            if arxiv_id == current or arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            ids.append(arxiv_id)
            if len(ids) >= max_ids:
                return ids
    return ids


def fetch_related_work_context(arxiv_ids: list[str], *, timeout: int = 5) -> str:
    if not arxiv_ids:
        return ""
    query = urllib.parse.urlencode({"id_list": ",".join(arxiv_ids)})
    url = f"https://export.arxiv.org/api/query?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "AutoPaperReader/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            xml_text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return f"外部 arXiv 相关工作元数据抓取失败：{exc}"

    try:
        root = ElementTree.fromstring(xml_text)
    except Exception as exc:
        return f"外部 arXiv 相关工作元数据解析失败：{exc}"

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    entries: list[str] = []
    for entry in root.findall("atom:entry", namespace):
        entry_id = entry.findtext("atom:id", "", namespace) or ""
        id_match = re.search(r"(\d{4}\.\d{4,5})(?:v\d+)?", entry_id)
        arxiv_id = id_match.group(1) if id_match else entry_id
        title = " ".join((entry.findtext("atom:title", "", namespace) or "").split())
        summary = " ".join((entry.findtext("atom:summary", "", namespace) or "").split())
        published = entry.findtext("atom:published", "", namespace) or ""
        authors = [
            " ".join((author.findtext("atom:name", "", namespace) or "").split())
            for author in entry.findall("atom:author", namespace)[:6]
        ]
        authors = [author for author in authors if author]
        entries.append(
            "\n".join(
                [
                    f"- arXiv: {arxiv_id}",
                    f"  title: {title}",
                    f"  authors: {', '.join(authors) or 'Unknown'}",
                    f"  published: {published}",
                    f"  abstract: {summary[:900]}",
                ]
            )
        )
    return "\n\n".join(entries)


def _strip_tex_commands(value: str) -> str:
    text = re.sub(r"%.*", "", value)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
    text = re.sub(r"[{}]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _resolve_graphic_path(source_dir: Path, tex_path: Path, raw_path: str) -> str:
    candidate = raw_path.strip().strip("{}")
    if not candidate:
        return raw_path
    path = Path(candidate)
    source_dir = source_dir.resolve()
    tex_path = tex_path.resolve()
    search_roots = [tex_path.parent, source_dir]
    suffixes = ["", ".pdf", ".png", ".jpg", ".jpeg", ".eps"]
    for root in search_roots:
        for suffix in suffixes:
            resolved = (root / f"{candidate}{suffix}").resolve()
            if resolved.exists():
                try:
                    source_root = source_dir.parent.parent.resolve()
                    relative = resolved.relative_to(source_root).as_posix()
                    return f"{source_root.name}/{relative}"
                except ValueError:
                    return resolved.as_posix()
    return candidate


def build_figure_context(source_dir: Path, *, max_items: int = 80) -> str:
    if not source_dir.exists():
        return ""
    items: list[str] = []
    tex_files = sorted(source_dir.rglob("*.tex"))
    for tex_path in tex_files:
        text = tex_path.read_text(encoding="utf-8", errors="ignore")
        environments = re.finditer(
            r"(?s)\\begin\{(figure\*?|table\*?)\}(.*?)\\end\{\1\}",
            text,
        )
        for match in environments:
            kind = "figure" if match.group(1).startswith("figure") else "table"
            body = match.group(2)
            captions = re.findall(r"(?s)\\caption(?:\[[^\]]*\])?\{(.*?)\}", body)
            graphics = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body)
            label_match = re.search(r"\\label\{([^}]+)\}", body)
            caption = _strip_tex_commands(captions[0]) if captions else ""
            graphic_paths = [
                _resolve_graphic_path(source_dir, tex_path, graphic)
                for graphic in graphics
            ]
            rel_tex = tex_path.relative_to(source_dir).as_posix()
            pieces = [f"- {kind} in {rel_tex}"]
            if label_match:
                pieces.append(f"label={label_match.group(1)}")
            if graphic_paths:
                pieces.append("files=" + ", ".join(graphic_paths))
            if caption:
                pieces.append(f"caption={caption[:700]}")
            items.append("; ".join(pieces))
            if len(items) >= max_items:
                break
        if len(items) >= max_items:
            break
    return "\n".join(items)


def build_report_materials(context: ReportContext) -> ReportMaterials:
    pdf_fallback = context.source_dir / "paper.pdf"
    pdf_fallback_path = ""
    if pdf_fallback.exists():
        try:
            source_root = context.source_dir.resolve().parent.parent
            pdf_fallback_path = f"{source_root.name}/{pdf_fallback.resolve().relative_to(source_root).as_posix()}"
        except ValueError:
            pdf_fallback_path = pdf_fallback.as_posix()
    source_context = read_source_context(context.source_dir, context.main_tex_path)
    bibliography_context = build_bibliography_context(context.source_dir)
    related_ids = extract_external_arxiv_ids(
        source_context,
        bibliography_context,
        context.metadata.abstract,
        current_arxiv_id=context.metadata.arxiv_id,
    )
    return ReportMaterials(
        analyst_contract=read_paper_analyst_contract(),
        memory_context=read_agent_memory_context(),
        source_context=source_context,
        figure_context=build_figure_context(context.source_dir),
        bibliography_context=bibliography_context,
        related_work_context=fetch_related_work_context(related_ids),
        pdf_fallback_path=pdf_fallback_path,
    )


def build_report_prompt(context: ReportContext, materials: ReportMaterials | None = None) -> str:
    materials = materials or build_report_materials(context)
    authors = ", ".join(context.metadata.authors)
    return f"""
你现在要严格扮演 AutoPaperReader 的 `paper-analyst` 子 agent，按既有深读流程产出正式中文论文阅读报告。
下面的「paper-analyst 契约」是最高优先级写作规范；如果契约与后续补充要求冲突，以更严格、更具体者为准。

【paper-analyst 契约】
```text
{materials.analyst_contract}
```

【长期记忆 / 用户偏好】
```markdown
{materials.memory_context or "无额外长期记忆。"}
```

【桌面应用额外硬性约束】
- 后端会尽力从 TeX/BibTeX 中出现的 arXiv id 拉取外部相关工作元数据，并作为"外部相关工作证据包"提供给你；如果证据包为空或抓取失败，「批判性分析」必须明确说明证据边界，不能伪造"联网查到"。
- 输出必须是完整 Markdown，开头必须包含 YAML frontmatter。
- frontmatter 里的 status 必须只写阅读状态，默认写 `read`；不要写 arXiv 版本号、日期或解释。
- frontmatter 里的 importance 必须只写 1-5 的整数，例如 `importance: 4`；不要写"中高"、原因或中文说明。
- frontmatter 必须包含 research_line 和 line_role，用于个人知识库领域管理。
- 图表必须放在对应论证位置，而不是集中堆到文末：架构图放在方法细节，主结果表/曲线放在实验，失败案例或限制相关图放在批判性分析。每张图下面直接写 2-4 句「图解：...」，解释它支撑的 claim、关键趋势和容易忽略的细节。
- 如果图表清单里出现 `files=...`，必须用 Markdown 图片语法插入对应本地路径，例如 `![Figure 1](sources/<slug>/arxiv/figure.png)`，不能只写文字描述。
- 如果图表清单里有 figure/table/caption 但没有 `files=...`，说明它很可能是 TikZ/LaTeX 直接绘制或表格源码；不要说"论文没有图"。如果本地 PDF 兜底路径存在，可以在对应位置插入 PDF 预览，例如 `![Figure 1 PDF 预览]({materials.pdf_fallback_path or "sources/<slug>/arxiv/paper.pdf"}#page=页码)`；页码不确定时可以不加 `#page`，但仍要写图解。
- 不要创建独立的 `## 10. 论文图表解读` 来堆放所有图片；如果有公开代码并需要代码观察，代码观察应作为 `## 10. 代码实现观察`。
- 报告要接近人工深读质量：不要写模板化空话；每个判断都尽量指向正文、公式、实验、图表或参考文献线索。

论文元数据：
- slug: {context.slug}
- arxiv_id: {context.metadata.arxiv_id}
- title: {context.metadata.title}
- authors: {authors}
- year: {context.metadata.year or ""}
- published: {context.metadata.published}
- arxiv_url: {context.metadata.abs_url}
- pdf_url: {context.metadata.pdf_url}
- abstract: {context.metadata.abstract}

TeX 主文件路径：
{context.main_tex_path or ""}

论文图表清单（从 TeX figure/table 环境提取；如果文件路径可解析，会给出本地相对路径）：
```text
{materials.figure_context or "未从 TeX 中解析到 figure/table 环境；请仍根据正文中的图表引用说明是否缺失。"}
```

本地 PDF 兜底路径（用于 TikZ/LaTeX 绘制图或表格预览；若为空则不可用）：
{materials.pdf_fallback_path or "无"}

BibTeX / 参考文献线索（可能截断；用于核心参考文献和批判性分析，不要简单罗列全集）：
```bibtex
{materials.bibliography_context or "未找到 .bib 文件；请从正文 related work 和 cite 语境推断核心参考文献。"}
```

外部相关工作证据包（后端从 TeX/BibTeX 中可识别的 arXiv id 抓取；可能为空或截断）：
```text
{materials.related_work_context or "未抓取到外部 arXiv 相关工作元数据；请基于本文 related work、BibTeX 和稳定学术常识谨慎分析。"}
```

TeX 源码内容（已按 main.tex / input / include 顺序聚合，仍可能截断）：
```tex
{materials.source_context}
```
""".strip()


def build_deep_notes_prompt(context: ReportContext, materials: ReportMaterials) -> str:
    authors = ", ".join(context.metadata.authors)
    return f"""
你是 AutoPaperReader 的论文深读助手。先不要写最终报告，而是产出一份"可展示的阅读札记 / evidence map"，用于后续正式报告生成。

要求：
- 用中文写，关键术语保留英文。
- 必须逐项覆盖：问题动机、核心方法、实验设计、主要结果、图表含义、相关工作关系、可能局限、算力与实现线索。
- 每个判断后面尽量标出证据来源，例如 section 名、figure/table label、caption、公式、abstract 或 related work 线索。
- 这不是隐藏思维链，而是给用户看的结构化阅读札记；不要输出最终 Markdown 报告，不要写 YAML frontmatter。
- 如果图表是 TikZ/LaTeX 画出来的，明确记录它的 label/caption 和应该放入报告的章节。

论文元数据：
- slug: {context.slug}
- arxiv_id: {context.metadata.arxiv_id}
- title: {context.metadata.title}
- authors: {authors}
- year: {context.metadata.year or ""}
- abstract: {context.metadata.abstract}

图表清单：
```text
{materials.figure_context or "未解析到图表环境"}
```

长期记忆 / 用户偏好：
```markdown
{materials.memory_context or "无额外长期记忆。"}
```

本地 PDF 兜底路径：
{materials.pdf_fallback_path or "无"}

参考文献线索：
```bibtex
{materials.bibliography_context or "未找到 .bib 文件"}
```

外部相关工作证据包：
```text
{materials.related_work_context or "未抓取到外部 arXiv 相关工作元数据"}
```

TeX 源码：
```tex
{materials.source_context}
```
""".strip()


def build_deep_critique_prompt(context: ReportContext, materials: ReportMaterials, notes: str = "") -> str:
    notes_context = (
        f"""阅读札记：
```text
{notes}
```"""
        if notes.strip()
        else f"""阅读札记：
```text
本阶段与阅读札记并发执行，未提供单独札记；请直接基于 TeX、Related Work、BibTeX、图表清单和摘要完成批判性分析。
```

TeX 源码：
```tex
{materials.source_context}
```"""
    )
    return f"""
你是 AutoPaperReader 的批判性审稿助手。基于下面的阅读札记、Related Work/BibTeX、图表和 TeX 证据，产出"批判性分析备忘录"。

要求：
- 不要写最终报告。
- 明确区分：论文自己声称的贡献、相对前作的真实增量、可能只是工程组合的部分、实验覆盖不足、复现风险。
- 优先使用外部相关工作证据包、BibTeX 和 Related Work 交叉判断；如果证据只来自论文相关工作，明确写"基于本文相关工作判断"。
- 输出 8-14 条高密度 bullet，每条都要有证据依据。

论文：{context.metadata.title} ({context.metadata.arxiv_id})

{notes_context}

图表清单：
```text
{materials.figure_context or "未解析到图表环境"}
```

BibTeX / 相关工作线索：
```bibtex
{materials.bibliography_context or "未找到 .bib 文件"}
```

外部相关工作证据包：
```text
{materials.related_work_context or "未抓取到外部 arXiv 相关工作元数据"}
```

长期记忆 / 用户偏好：
```markdown
{materials.memory_context or "无额外长期记忆。"}
```
""".strip()


def build_deep_final_prompt(
    context: ReportContext,
    materials: ReportMaterials,
    notes: str,
    critique: str,
) -> str:
    base_prompt = build_report_prompt(context, materials)
    return f"""
{base_prompt}

【深读札记】
```text
{notes}
```

【批判性分析备忘录】
```text
{critique}
```

现在基于上面的 TeX、图表清单、阅读札记和批判性分析备忘录，写最终中文阅读报告。
这必须是一份正式入库的深度报告，不是快速摘要。请严格遵守以下额外要求：
- 输出只能是完整 Markdown 报告，不要解释生成过程。
- 每个章节都要有实质内容，不能出现"待补充""后续分析""略"等占位。
- 方法细节和实验部分要尽量引用具体 figure/table/公式/section 证据。
- 图表必须就近放在对应章节，并在下方写"图解：..."。没有独立图片文件的 TikZ 图，使用本地 PDF 兜底路径做预览。
- 批判性分析必须尖锐但有依据，不能只写泛泛局限。
""".strip()


def build_deep_repair_prompt(
    context: ReportContext,
    materials: ReportMaterials,
    markdown: str,
    errors: list[str],
) -> str:
    return f"""
下面是一份 AutoPaperReader 深度论文报告，但没有通过质量校验。请直接返回修订后的完整 Markdown 报告，不要输出解释。

**重要：你的回复必须以 `---` 开头，以 `---` 结束，中间是完整的 YAML frontmatter 和报告正文。不要在报告前后添加任何解释、说明或代码块标记。**

校验错误：
{chr(10).join(f'- {error}' for error in errors)}

硬性要求：
- 保留并修正 YAML frontmatter。
- 必须包含 1-9 章。
- status 只能是 read/unread/reading 等阅读状态，默认 read。
- importance 只能是 1-5 的整数。
- 如果有本地图片/PDF 路径，必须用 Markdown 媒体语法插入，并写"图解：..."。
- 不要新增独立的"论文图表解读"章节。

图表清单：
```text
{materials.figure_context or '未解析到图表环境'}
```

本地 PDF 兜底路径：
{materials.pdf_fallback_path or '无'}

长期记忆 / 用户偏好：
```markdown
{materials.memory_context or "无额外长期记忆。"}
```

原报告：
```markdown
{markdown}
```
""".strip()


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def build_mock_report(context: ReportContext) -> str:
    year = context.metadata.year or 0
    authors = context.metadata.authors or ["Unknown"]
    author_lines = "\n".join(f"  - {author}" for author in authors)
    author_text = ", ".join(authors)
    return f"""---
slug: {context.slug}
title: {context.metadata.title}
title_zh: {context.metadata.title}
title_en: {context.metadata.title}
arxiv_id: "{context.metadata.arxiv_id}"
year: {year}
authors:
{author_lines}
domains:
  - Unclassified
tracks:
  - Unclassified
problems:
  - Unclassified
topics:
  - Paper Reading
methods:
  - LLM-assisted analysis
research_line: Unclassified
line_role: main
status: unread
reading_stage: skim
review_stage: fresh
importance: 3
confidence: 2
reproducibility: 2
has_code: false
arxiv_url: "{context.metadata.abs_url}"
code_url: ""
---

# {context.metadata.title}

## 1. 基本情况

- 题目（中 / 英）：{context.metadata.title} / {context.metadata.title}
- 作者：{author_text}
- 单位：待人工补充
- arXiv 编号与提交日期：{context.metadata.arxiv_id} / {context.metadata.published}
- arXiv 链接：{context.metadata.abs_url}
- PDF：{context.metadata.pdf_url}
- 代码仓库：未检查公开代码

## 2. 核心贡献概述

- 中文版：这是一份由 mock provider 生成的结构化占位报告，用于验证 AutoPaperReader 的端到端流水线。
- English version: {context.metadata.abstract[:300]}
- 原文出处：abstract

## 3. 一句话精髓（写给外行）

这篇论文像是在一张复杂地图上先点亮主路，让后续深读能沿着清楚的路标继续前进。

## 4. 学术贡献清单

### 4.1 动机的发现与阐明

- 前人没有解决或没有说清的问题：待 LLM 深读后补充。
- 作者如何验证这个问题存在：待 LLM 深读后补充。

### 4.2 方法的创新

- 创新点 1：待 LLM 深读后补充。
- 创新点 2：待 LLM 深读后补充。

### 4.3 实验上的核心结论

- 主结论：待 LLM 深读后补充。
- 相比 baseline 的差异：待 LLM 深读后补充。

## 5. 写作故事线

待 LLM 深读后补充。当前报告主要用于验证导入、报告写入、HTML 渲染和 wiki 刷新链路。

## 6. 核心参考文献

- [ ] 待 LLM 深读后补充：需要从 TeX/BibTeX 中抽取关键引用。

## 7. 批判性分析

### 7.1 与前作的关系

- 这篇论文真正新增了什么：待 LLM 深读后补充。
- 哪些部分是已有方法的组合或工程化：待 LLM 深读后补充。

### 7.2 可能的局限

- 理论假设：待 LLM 深读后补充。
- 实验覆盖：待 LLM 深读后补充。
- 复现门槛：待 LLM 深读后补充。

## 8. 方法细节

### 8.1 算法流程

1. 输入：论文 TeX 源码与 arXiv metadata。
2. 核心步骤：解析、生成报告、渲染 HTML、刷新 wiki。
3. 输出：Markdown 与 HTML 报告。

### 8.2 关键公式

$$
\\mathrm{{Report}} = f(\\mathrm{{metadata}}, \\mathrm{{tex}})
$$

### 8.3 模型与数据流

- Backbone：待 LLM 深读后补充。
- 训练数据：待 LLM 深读后补充。
- 推理流程：待 LLM 深读后补充。

### 8.4 算力资源需求

- GPU 数量与型号：论文未在 mock 阶段解析。
- 训练时长：论文未在 mock 阶段解析。
- token / step 数：论文未在 mock 阶段解析。
- 估算说明：需要后续 LLM 深读或人工复核。

## 9. 实验

### 9.1 评测数据集

- 数据集：待 LLM 深读后补充。
- 规模：待 LLM 深读后补充。
- 任务类型：待 LLM 深读后补充。

### 9.2 评测指标

- 指标 1：待 LLM 深读后补充。

### 9.3 主实验结果

- 与 baseline 的对比：待 LLM 深读后补充。
- 最重要的表格或图：待 LLM 深读后补充。

### 9.4 消融实验

- Ablation 1 验证的假设：待 LLM 深读后补充。

### 9.5 结果分析

- 作者认为：待 LLM 深读后补充。
- 我认为：当前 mock 报告只适合验证系统链路，不应作为最终论文理解。

"""


def displayable_figure_paths(figure_context: str) -> list[str]:
    paths: list[str] = []
    suffixes = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf")
    for match in re.finditer(r"files=([^;\n]+)", figure_context):
        for raw_path in match.group(1).split(","):
            path = raw_path.strip()
            if path.lower().endswith(suffixes):
                paths.append(path)
    return paths


def validate_report(markdown: str, *, figure_context: str = "") -> list[str]:
    errors: list[str] = []
    if not markdown.startswith("---\n"):
        errors.append("missing YAML frontmatter")
    frontmatter_match = re.match(r"(?s)^---\n(.*?)\n---", markdown)
    frontmatter = frontmatter_match.group(1) if frontmatter_match else ""
    for key in sorted(REQUIRED_FRONTMATTER):
        if not re.search(rf"(?m)^{re.escape(key)}\s*:", frontmatter):
            errors.append(f"missing frontmatter field: {key}")
    for section in REQUIRED_SECTIONS:
        if section not in markdown:
            errors.append(f"missing required section: {section}")
    figure_paths = displayable_figure_paths(figure_context)
    if figure_paths:
        has_local_media = any(path in markdown for path in figure_paths) or bool(
            re.search(r"!\[[^\]]*\]\((?:\.\./)?sources/[^)]+\)", markdown)
        )
        if not has_local_media:
            errors.append("missing inline figure markdown for extracted paper figures")
    if re.search(r"!\[[^\]]*\]\((?:\.\./)?sources/[^)]+\)", markdown) and "图解" not in markdown:
        errors.append("missing figure interpretation text: 图解")
    return errors


def extract_report_from_llm_output(raw_output: str) -> str:
    """Extract the actual report from Claude Code's output, stripping explanatory text."""
    text = raw_output.strip()

    # If it starts with ---, it's already a report
    if text.startswith("---\n"):
        return text

    # Try to extract from markdown code block
    code_block_match = re.search(r"```(?:markdown|md)?\s*\n(---\n.*?\n---)\s*\n```", text, re.DOTALL)
    if code_block_match:
        return code_block_match.group(1).strip()

    # Try to find --- delimiters anywhere in the text
    delimiter_match = re.search(r"(?s)(---\n.*?\n---)", text)
    if delimiter_match:
        return delimiter_match.group(1).strip()

    # If nothing works, return as-is
    return text


def strip_frontmatter(markdown: str) -> str:
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---", 4)
    if end == -1:
        return markdown
    return markdown[end + len("\n---") :].lstrip()


def parse_report_frontmatter(markdown: str) -> dict[str, Any]:
    match = re.match(r"(?s)^---\n(.*?)\n---", markdown)
    if not match:
        return {}

    data: dict[str, Any] = {}
    current_key = ""
    for raw_line in match.group(1).splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")) and raw_line.strip().startswith("- ") and current_key:
            data.setdefault(current_key, []).append(_parse_frontmatter_scalar(raw_line.strip()[2:]))
            continue
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", raw_line)
        if not key_match:
            current_key = ""
            continue
        current_key = key_match.group(1)
        raw_value = key_match.group(2).strip()
        if raw_value == "":
            data[current_key] = []
        else:
            data[current_key] = _parse_frontmatter_scalar(raw_value)
    return data


def _parse_frontmatter_scalar(raw_value: str) -> Any:
    value = raw_value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def _frontmatter_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def extract_report_tags(markdown: str) -> dict[str, list[str]]:
    frontmatter = parse_report_frontmatter(markdown)
    return {
        "domain": _frontmatter_list(frontmatter, "domains"),
        "track": _frontmatter_list(frontmatter, "tracks"),
        "problem": _frontmatter_list(frontmatter, "problems"),
        "topic": _frontmatter_list(frontmatter, "topics"),
        "method": _frontmatter_list(frontmatter, "methods"),
    }


def chunk_report(markdown: str, *, max_chars: int = 2400) -> list[dict[str, Any]]:
    body = strip_frontmatter(markdown)
    sections: list[tuple[str, str]] = []
    current_section = "Front Matter"
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_section, "\n".join(current_lines).strip()))
            current_section = line.lstrip("#").strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_section, "\n".join(current_lines).strip()))

    chunks: list[dict[str, Any]] = []
    for section, text in sections:
        if not text:
            continue
        start = 0
        while start < len(text):
            part = text[start : start + max_chars].strip()
            if part:
                chunks.append(
                    {
                        "source_type": "report",
                        "section": section,
                        "text": part,
                        "token_count": max(1, len(part.split())),
                    }
                )
            start += max_chars
    return chunks


def write_report(context: ReportContext, provider: LLMProvider, *, prompt: str | None = None) -> str:
    prompt = prompt if prompt is not None else build_report_prompt(context)
    figure_context = build_figure_context(context.source_dir)
    markdown = provider.generate(prompt).strip()
    errors = validate_report(markdown, figure_context=figure_context)
    if errors:
        raise ValueError("Generated report failed validation: " + "; ".join(errors))
    context.report_md_path.parent.mkdir(parents=True, exist_ok=True)
    context.report_md_path.write_text(markdown + "\n", encoding="utf-8")
    return markdown


def generate_deep_report(
    context: ReportContext,
    provider: LLMProvider,
    *,
    on_stage: Any | None = None,
) -> ReportGenerationResult:
    materials = build_report_materials(context)
    runs: list[ReportModelRun] = []

    def run_stage(stage: str, prompt: str) -> str:
        if on_stage:
            on_stage(stage)
        try:
            response = provider.generate(prompt).strip()
        except Exception as exc:
            runs.append(ReportModelRun(stage=stage, prompt=prompt, error=str(exc)))
            raise
        runs.append(ReportModelRun(stage=stage, prompt=prompt, response=response))
        return response

    notes_prompt = build_deep_notes_prompt(context, materials)
    notes = run_stage("reading_notes", notes_prompt)

    critique_prompt = build_deep_critique_prompt(context, materials, notes)
    critique = run_stage("critical_memo", critique_prompt)

    final_prompt = build_deep_final_prompt(context, materials, notes, critique)
    markdown = run_stage("final_report", final_prompt)

    errors = validate_report(markdown, figure_context=materials.figure_context)
    if errors:
        repair_prompt = build_deep_repair_prompt(context, materials, markdown, errors)
        markdown = run_stage("quality_repair", repair_prompt)
        errors = validate_report(markdown, figure_context=materials.figure_context)
    if errors:
        raise ValueError("Generated report failed validation: " + "; ".join(errors))

    context.report_md_path.parent.mkdir(parents=True, exist_ok=True)
    context.report_md_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return ReportGenerationResult(markdown=markdown, runs=runs)


def apply_code_observation(markdown: str, observation: str) -> str:
    if not observation.strip():
        return markdown
    pattern = re.compile(r"(?ms)^## (?:10|11)\. 代码实现观察\s*$.*?(?=^## \d+\. |\Z)")
    if pattern.search(markdown):
        return pattern.sub(observation.strip() + "\n", markdown).rstrip() + "\n"
    return markdown.rstrip() + "\n\n" + observation.strip() + "\n"


def render_report_html(config: AppConfig, context: ReportContext) -> None:
    script = config.root_dir / "scripts" / "render_report_html.py"
    result = subprocess.run(
        [
            "python3",
            str(script),
            str(context.report_md_path),
            str(context.report_html_path),
            "--slug",
            context.slug,
        ],
        cwd=config.root_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"HTML render failed: {result.stderr}")


def rebuild_wiki(config: AppConfig) -> None:
    script = config.root_dir / "scripts" / "build_wiki.py"
    result = subprocess.run(
        ["python3", str(script), str(config.report_dir)],
        cwd=config.root_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Wiki rebuild failed: {result.stderr}")


def context_from_output(output: dict[str, Any]) -> ReportContext:
    metadata = ArxivMetadata(
        arxiv_id=str(output["arxiv_id"]),
        title=str(output["title"]),
        authors=[str(author) for author in output.get("authors", [])],
        abstract=str(output.get("abstract", "")),
        published=str(output.get("published", "")),
        year=int(output["year"]) if output.get("year") else None,
        abs_url=str(output.get("abs_url", "")),
        pdf_url=str(output.get("pdf_url", "")),
        eprint_url=str(output.get("eprint_url", "")),
    )
    main_tex = Path(str(output.get("main_tex_path", ""))) if output.get("main_tex_path") else None
    return ReportContext(
        slug=str(output["slug"]),
        metadata=metadata,
        source_dir=Path(str(output["source_dir"])),
        main_tex_path=main_tex,
        report_md_path=Path(str(output["report_md_path"])),
        report_html_path=Path(str(output["report_html_path"])),
    )
