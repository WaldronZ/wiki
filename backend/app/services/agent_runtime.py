from __future__ import annotations

import json
import re
import subprocess
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .llm import LLMProvider
from .code import (
    CodeSummary,
    build_code_analyst_prompt,
    build_code_context,
    build_code_observation,
    build_code_revision_prompt,
    validate_code_observation,
)
from .report import (
    ReportContext,
    ReportMaterials,
    ReportModelRun,
    build_deep_critique_prompt,
    build_deep_final_prompt,
    build_deep_notes_prompt,
    build_deep_repair_prompt,
    build_report_materials,
    estimate_tokens,
    validate_report,
)


StageCallback = Callable[[str, str], None]
RunCallback = Callable[[ReportModelRun], None]
ArtifactCallback = Callable[[str, str, Path, str, dict[str, object]], None]


@dataclass(frozen=True)
class PaperAgentRunResult:
    markdown: str
    runs: list[ReportModelRun]
    artifacts_dir: Path


@dataclass(frozen=True)
class CodeAgentRunResult:
    markdown: str
    observation: str
    runs: list[ReportModelRun]
    artifacts_dir: Path


@dataclass(frozen=True)
class HtmlPresenterRunResult:
    html_path: Path
    validation_errors: list[str]
    artifacts_dir: Path


class AgentRuntimeBase:
    def __init__(
        self,
        context: ReportContext,
        provider: LLMProvider,
        *,
        root_dir: Path,
        on_stage: StageCallback | None = None,
        on_run: RunCallback | None = None,
        on_artifact: ArtifactCallback | None = None,
    ) -> None:
        self.context = context
        self.provider = provider
        self.root_dir = root_dir
        self.on_stage = on_stage
        self.on_run = on_run
        self.on_artifact = on_artifact
        self.runs: list[ReportModelRun] = []
        self.artifacts_dir = context.report_md_path.parent / "artifacts" / context.slug
        self._lock = threading.Lock()

    def _run_stage(self, stage: str, label: str, prompt: str, artifact_name: str) -> str:
        if self.on_stage:
            self.on_stage(stage, label)
        try:
            raw_response = self.provider.generate(prompt).strip()
            # Extract clean report from Claude Code's output (strips explanatory text)
            from .report import extract_report_from_llm_output
            response = extract_report_from_llm_output(raw_response)
        except Exception as exc:
            run = ReportModelRun(stage=stage, prompt=prompt, error=str(exc))
            with self._lock:
                self.runs.append(run)
                if self.on_run:
                    self.on_run(run)
            raise

        run = ReportModelRun(stage=stage, prompt=prompt, response=response)
        with self._lock:
            self.runs.append(run)
            if self.on_run:
                self.on_run(run)
        self._write_artifact(
            stage,
            "llm_response",
            artifact_name,
            response,
            {
                "label": label,
                "input_tokens_estimate": estimate_tokens(prompt),
                "output_tokens_estimate": estimate_tokens(response),
            },
        )
        return response

    def _write_artifact(
        self,
        stage: str,
        artifact_type: str,
        filename: str,
        content: str,
        metadata: dict[str, object] | None = None,
    ) -> Path:
        target = self.artifacts_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content.rstrip() + "\n", encoding="utf-8")
        if self.on_artifact:
            with self._lock:
                self.on_artifact(stage, artifact_type, target, content, metadata or {})
        return target


def _read_agent_contract(root_dir: Path, agent_name: str) -> str:
    path = root_dir / ".Codex" / "agents" / f"{agent_name}.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    return str(data.get("developer_instructions") or "").strip()


class PaperAgentRuntime(AgentRuntimeBase):
    """Small local agent harness for deep paper analysis.

    This intentionally mirrors the old repository-agent workflow without
    requiring Claude Code or Codex to be installed. Each stage gets its own
    prompt, produces a durable artifact, and passes through deterministic
    quality gates before the final report is accepted.
    """

    def run(self) -> PaperAgentRunResult:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        materials = build_report_materials(self.context)
        self._write_context_package(materials)

        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="paper-agent") as executor:
            notes_future = executor.submit(
                self._run_stage,
                "reading_notes",
                "阅读札记",
                build_deep_notes_prompt(self.context, materials),
                "reading_notes.md",
            )
            critique_future = executor.submit(
                self._run_stage,
                "critical_memo",
                "批判性分析备忘录",
                build_deep_critique_prompt(self.context, materials),
                "critical_memo.md",
            )
            notes = notes_future.result()
            critique = critique_future.result()
        markdown = self._run_stage(
            "final_report",
            "正式深度报告",
            build_deep_final_prompt(self.context, materials, notes, critique),
            "draft_report.md",
        )

        errors = validate_report(markdown, figure_context=materials.figure_context)
        self._write_quality_report(errors, repaired=False)
        if errors:
            markdown = self._run_stage(
                "quality_repair",
                "质量修订",
                build_deep_repair_prompt(self.context, materials, markdown, errors),
                "repaired_report.md",
            )
            errors = validate_report(markdown, figure_context=materials.figure_context)
            self._write_quality_report(errors, repaired=True)

        if errors:
            raise ValueError("Generated report failed validation: " + "; ".join(errors))

        self.context.report_md_path.parent.mkdir(parents=True, exist_ok=True)
        self.context.report_md_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
        self._write_artifact(
            "final_report",
            "report",
            "final_report.md",
            markdown,
            {"accepted": True},
        )
        return PaperAgentRunResult(
            markdown=markdown,
            runs=self.runs,
            artifacts_dir=self.artifacts_dir,
        )

    def _write_context_package(self, materials: ReportMaterials) -> None:
        metadata = self.context.metadata
        payload = {
            "slug": self.context.slug,
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "published": metadata.published,
            "abs_url": metadata.abs_url,
            "pdf_url": metadata.pdf_url,
            "source_dir": str(self.context.source_dir),
            "main_tex_path": str(self.context.main_tex_path or ""),
            "report_md_path": str(self.context.report_md_path),
            "report_html_path": str(self.context.report_html_path),
            "pdf_fallback_path": materials.pdf_fallback_path,
        }
        self._write_artifact(
            "context_builder",
            "context_json",
            "context.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            {"description": "paper metadata and local paths"},
        )
        self._write_artifact(
            "context_builder",
            "figure_map",
            "figure_map.txt",
            materials.figure_context,
            {"description": "TeX figure/table environments"},
        )
        self._write_artifact(
            "context_builder",
            "memory_context",
            "memory_context.md",
            materials.memory_context,
            {"description": "long-term user and project preferences"},
        )
        self._write_artifact(
            "context_builder",
            "bibliography_context",
            "bibliography_context.bib",
            materials.bibliography_context,
            {"description": "BibTeX snippets used for related work"},
        )
        self._write_artifact(
            "context_builder",
            "source_context",
            "source_context.tex",
            materials.source_context,
            {"description": "ordered TeX context passed to the analysis agents"},
        )

    def _write_quality_report(self, errors: list[str], *, repaired: bool) -> None:
        payload = {
            "status": "passed" if not errors else "failed",
            "repaired": repaired,
            "errors": errors,
        }
        self._write_artifact(
            "quality_gate",
            "quality_report",
            "quality_report.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
            {"repaired": repaired},
        )

class CodeAnalystRuntime(AgentRuntimeBase):
    def __init__(
        self,
        context: ReportContext,
        provider: LLMProvider,
        *,
        root_dir: Path,
        summary: CodeSummary,
        on_stage: StageCallback | None = None,
        on_run: RunCallback | None = None,
        on_artifact: ArtifactCallback | None = None,
    ) -> None:
        super().__init__(
            context,
            provider,
            root_dir=root_dir,
            on_stage=on_stage,
            on_run=on_run,
            on_artifact=on_artifact,
        )
        self.summary = summary

    def run(self, markdown: str) -> CodeAgentRunResult:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        code_dir = Path(self.summary.path) if self.summary.path else Path()
        code_context = build_code_context(code_dir)
        self._write_artifact(
            "code_context_builder",
            "code_context",
            "code_context.txt",
            code_context,
            {"repository": self.summary.url, "local_path": self.summary.path},
        )
        prompt = build_code_analyst_prompt(
            slug=self.context.slug,
            report_markdown=markdown,
            summary=self.summary,
            code_context=code_context,
        )
        fallback = build_code_observation(self.summary)
        try:
            observation = self._run_stage(
                "code_analyst",
                "代码实现观察",
                prompt,
                "code_observation.md",
            )
        except Exception:
            observation = fallback
        errors = validate_code_observation(observation)
        if errors:
            observation = fallback
            self._write_artifact(
                "code_analyst",
                "fallback",
                "code_observation_fallback.md",
                observation,
                {"validation_errors": errors},
            )
        updated = self._revise_report(markdown, observation, code_context)
        self.context.report_md_path.write_text(updated.rstrip() + "\n", encoding="utf-8")
        return CodeAgentRunResult(
            markdown=updated,
            observation=observation,
            runs=self.runs,
            artifacts_dir=self.artifacts_dir,
        )

    @staticmethod
    def _apply_code_observation(markdown: str, observation: str) -> str:
        from .report import apply_code_observation

        return apply_code_observation(markdown, observation)

    def _revise_report(self, markdown: str, observation: str, code_context: str) -> str:
        fallback = self._apply_code_observation(markdown, observation)
        prompt = build_code_revision_prompt(
            slug=self.context.slug,
            report_markdown=markdown,
            observation=observation,
            summary=self.summary,
            code_context=code_context,
        )
        try:
            revised = self._run_stage(
                "code_report_revision",
                "代码核对后修订报告",
                prompt,
                "code_revised_report.md",
            )
        except Exception:
            return fallback

        errors = validate_report(revised) + validate_code_observation(revised)
        if errors:
            self._write_artifact(
                "code_report_revision",
                "fallback",
                "code_revision_fallback.md",
                fallback,
                {"validation_errors": errors},
            )
            return fallback
        return revised


class HtmlPresenterRuntime(AgentRuntimeBase):
    def run(self) -> HtmlPresenterRunResult:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        contract = _read_agent_contract(self.root_dir, "html-presenter")
        markdown = self.context.report_md_path.read_text(encoding="utf-8", errors="ignore")
        mindmap_path = self._build_mindmap_artifact(markdown, contract)
        self._write_artifact(
            "html_presenter",
            "contract",
            "html_presenter_contract.txt",
            contract,
            {"description": "original html-presenter agent contract"},
        )
        self._write_artifact(
            "html_presenter",
            "presenter_context",
            "html_presenter_context.json",
            json.dumps(
                {
                    "slug": self.context.slug,
                    "report_md_path": str(self.context.report_md_path),
                    "report_html_path": str(self.context.report_html_path),
                    "title": self.context.metadata.title,
                    "arxiv_url": self.context.metadata.abs_url,
                    "pdf_url": self.context.metadata.pdf_url,
                },
                ensure_ascii=False,
                indent=2,
            ),
            {"description": "html presenter input context"},
        )
        if self.on_stage:
            self.on_stage("html_presenter", "HTML 阅读页渲染")
        script = self.root_dir / "scripts" / "render_report_html.py"
        result = subprocess.run(
            [
                "python3",
                str(script),
                str(self.context.report_md_path),
                str(self.context.report_html_path),
                "--slug",
                self.context.slug,
                *(
                    ["--mindmap-path", str(mindmap_path)]
                    if mindmap_path is not None
                    else []
                ),
            ],
            cwd=self.root_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self._write_artifact(
            "html_presenter",
            "renderer_log",
            "html_renderer.log",
            "\n".join(
                [
                    f"returncode={result.returncode}",
                    "[stdout]",
                    result.stdout,
                    "[stderr]",
                    result.stderr,
                ]
            ),
            {"returncode": result.returncode},
        )
        if result.returncode != 0:
            raise RuntimeError(f"HTML render failed: {result.stderr}")
        errors = self._validate_html(markdown)
        self._write_artifact(
            "html_presenter",
            "quality_report",
            "html_quality_report.json",
            json.dumps(
                {
                    "status": "passed" if not errors else "failed",
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            {"error_count": len(errors)},
        )
        if errors:
            raise ValueError("HTML presenter validation failed: " + "; ".join(errors))
        return HtmlPresenterRunResult(
            html_path=self.context.report_html_path,
            validation_errors=errors,
            artifacts_dir=self.artifacts_dir,
        )

    def _build_mindmap_artifact(self, markdown: str, contract: str) -> Path | None:
        prompt = f"""
你现在扮演 AutoPaperReader 的 `html-presenter` 子 agent。请只为 HTML 页面生成“内容脑图”的 Markmap markdown 源，不要重写报告。

【html-presenter 契约摘录】
```text
{contract}
```

输出要求：
- 只输出 mindmap markdown，不要代码围栏，不要解释。
- 第一行必须是 `# <论文短名>`。
- 下面生成 4-7 个 `##` 主干，每个主干 2-4 个 `-` 叶子。
- 这不是目录；主干必须概括论文叙事，例如问题动机、关键观察、方法核心、实验闭环、局限等，但要贴合报告实际内容。
- 叶子节点用短中文短语，关键英文术语可保留。

报告原文：
```markdown
{markdown[:80000]}
```
""".strip()
        try:
            raw = self._run_stage(
                "html_mindmap",
                "内容脑图提炼",
                prompt,
                "html_mindmap.md",
            )
        except Exception:
            return None
        mindmap = self._normalize_mindmap(raw)
        errors = self._validate_mindmap(mindmap)
        if errors:
            self._write_artifact(
                "html_mindmap",
                "fallback",
                "html_mindmap_fallback.txt",
                "\n".join(errors),
                {"validation_errors": errors},
            )
            return None
        return self._write_artifact(
            "html_mindmap",
            "mindmap",
            "html_mindmap.accepted.md",
            mindmap,
            {"branch_count": len(re.findall(r"(?m)^##\s+", mindmap))},
        )

    @staticmethod
    def _normalize_mindmap(raw: str) -> str:
        text = raw.strip()
        fence = re.match(r"(?s)^```(?:markdown|md)?\s*(.*?)\s*```$", text)
        if fence:
            text = fence.group(1).strip()
        return text

    @staticmethod
    def _validate_mindmap(mindmap: str) -> list[str]:
        errors: list[str] = []
        lines = [line.rstrip() for line in mindmap.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("# ") or lines[0].startswith("## "):
            errors.append("mindmap must start with a single # root")
        branch_count = len(re.findall(r"(?m)^##\s+\S", mindmap))
        leaf_count = len(re.findall(r"(?m)^-\s+\S", mindmap))
        if branch_count < 4 or branch_count > 7:
            errors.append("mindmap must contain 4-7 branches")
        if leaf_count < branch_count * 2:
            errors.append("mindmap must contain at least two leaves per branch on average")
        if mindmap.startswith("---"):
            errors.append("mindmap must not include report frontmatter")
        return errors

    def _validate_html(self, markdown: str) -> list[str]:
        errors: list[str] = []
        html_path = self.context.report_html_path
        if not html_path.exists() or html_path.stat().st_size == 0:
            return ["html file was not created"]
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        if "$$" in html:
            errors.append("html contains raw display math delimiters")
        section_numbers = sorted(set(re.findall(r"(?m)^##\s+(\d+)\.\s+", markdown)))
        for section in section_numbers:
            if f"{section}." not in html:
                errors.append(f"html may be missing section {section}")
        if re.search(r"!\[[^\]]*\]\((?:\.\./)?sources/[^)]+\)", markdown) and "assets/" not in html:
            errors.append("markdown references local media but html has no copied assets")
        if "media-viewer" not in html:
            errors.append("html is missing media viewer support")
        if "<meta charset=\"utf-8\"" not in html.lower() and "<meta charset='utf-8'" not in html.lower():
            errors.append("html is missing utf-8 meta charset")
        return errors
