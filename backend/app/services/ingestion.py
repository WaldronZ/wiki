from __future__ import annotations

import traceback
import re
from contextlib import closing
from pathlib import Path
from typing import Callable, TypeVar

from ..config import AppConfig
from ..db import (
    connect,
    get_job,
    init_db,
    record_agent_artifact,
    record_model_run,
    replace_paper_chunks,
    replace_paper_tags,
    update_job,
    upsert_paper,
    upsert_paper_search,
)
from .arxiv import fetch_arxiv_metadata
from .agent_runtime import CodeAnalystRuntime, HtmlPresenterRuntime, PaperAgentRuntime
from .code import CodeDiscovery, discover_and_clone_code, summarize_code_repo
from .llm import LLMConfigurationError, LLMGenerationError, build_effective_provider, effective_llm_settings
from .report import (
    ReportContext,
    REPORT_PROMPT_VERSION,
    build_mock_report,
    chunk_report,
    estimate_tokens,
    extract_report_tags,
    parse_report_frontmatter,
    rebuild_wiki,
)
from .slug import make_paper_slug
from .source import download_eprint, download_pdf, extract_source_package, find_main_tex


T = TypeVar("T")

VALID_PAPER_STATUSES = {"queued", "unread", "reading", "read", "triaged", "archived"}


class JobPaused(RuntimeError):
    pass


class JobCanceled(RuntimeError):
    pass


def frontmatter_score(value: object) -> int | None:
    if value in {None, ""}:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def frontmatter_status(value: object, *, default: str = "read") -> str:
    status = str(value or "").strip()
    return status if status in VALID_PAPER_STATUSES else default


def ensure_job_active(job_id: str, config: AppConfig) -> None:
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
    status = str((job or {}).get("status") or "")
    if status == "paused":
        raise JobPaused("Job paused by user")
    if status == "canceled":
        raise JobCanceled("Job canceled by user")


def next_runnable_import_job(conn, preferred_job_id: str | None = None) -> str:
    if preferred_job_id:
        preferred = get_job(conn, preferred_job_id)
        if preferred and preferred.get("type") == "paper_import" and preferred.get("status") in {"queued", "needs_llm"}:
            return preferred_job_id
    blocker = conn.execute(
        """
        SELECT id FROM jobs
        WHERE type = 'paper_import' AND status IN ('running', 'needs_llm', 'paused')
        AND id != ?
        LIMIT 1
        """,
        (preferred_job_id or "",),
    ).fetchone()
    if blocker is not None:
        return ""
    row = conn.execute(
        """
        SELECT id FROM jobs
        WHERE type = 'paper_import' AND status = 'queued'
        ORDER BY created_at ASC
        LIMIT 1
        """
    ).fetchone()
    return str(row["id"]) if row else ""


def run_import_queue(config: AppConfig, preferred_job_id: str | None = None) -> None:
    next_preferred = preferred_job_id
    while True:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            job_id = next_runnable_import_job(conn, next_preferred)
            if not job_id:
                return
            update_job(
                conn,
                job_id,
                status="running",
                log="analysis started from queue",
            )
        run_import_job(job_id, config)
        next_preferred = None
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            job = get_job(conn, job_id)
        if not job or job.get("status") in {"running", "needs_llm", "paused"}:
            return


def retry_operation(
    operation: Callable[[], T],
    *,
    attempts: int = 3,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    last_error: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return operation()
        except retry_exceptions as exc:
            last_error = exc
            if attempt >= attempts:
                break
            if on_retry:
                on_retry(attempt, exc)
    assert last_error is not None
    raise last_error


def classify_job_error(exc: BaseException) -> str:
    message = str(exc).lower()
    if isinstance(exc, LLMConfigurationError):
        return "failed_llm_configuration"
    if isinstance(exc, LLMGenerationError) or "llm provider" in message:
        return "llm_generation_failed"
    if "no tex file" in message or "main_tex" in message:
        return "missing_tex_source"
    if "generated report failed validation" in message:
        return "malformed_report"
    if "html render failed" in message:
        return "html_render_failed"
    if "wiki rebuild failed" in message:
        return "wiki_rebuild_failed"
    if "unsupported arxiv source package" in message or "archive member escapes" in message:
        return "packaging_path_issue"
    if "urlopen" in message or "timed out" in message or "download" in message:
        return "download_failed"
    return "unknown_error"


def run_import_job(job_id: str, config: AppConfig) -> None:
    resume_report = False
    resume_input_payload: dict[str, object] = {}
    resume_output_payload: dict[str, object] = {}
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        if job is None:
            return
        if job.get("status") in {"completed", "canceled"}:
            return
        input_payload = job.get("input") or {}
        output_payload = job.get("output") or {}
        arxiv_id = str(input_payload.get("arxiv_id") or "")
        if output_payload and job.get("status") in {"needs_llm", "paused"}:
            resume_report = True
            resume_input_payload = input_payload
            resume_output_payload = output_payload
        if not arxiv_id:
            update_job(
                conn,
                job_id,
                status="failed",
                current_step="invalid_input",
                progress=100,
                error_message="Missing arXiv id in job input.",
                log="failed: missing arXiv id",
                finished=True,
            )
            return

    if resume_report:
        try:
            _run_report_stage(job_id, config, resume_input_payload, resume_output_payload)
        except (JobPaused, JobCanceled):
            return
        except LLMConfigurationError as exc:
            _mark_job_needs_llm(job_id, config, exc)
        except Exception as exc:  # noqa: BLE001
            _mark_job_failed(job_id, config, exc, resume_output_payload)
        return

    try:
        _run_import_job(job_id, config, arxiv_id)
    except (JobPaused, JobCanceled):
        return
    except LLMConfigurationError as exc:
        _mark_job_needs_llm(job_id, config, exc)
    except Exception as exc:  # noqa: BLE001 - job boundary must capture failures
        _mark_job_failed(job_id, config, exc)


def _mark_job_failed(
    job_id: str,
    config: AppConfig,
    exc: BaseException,
    output_payload: dict[str, object] | None = None,
) -> None:
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        existing_job = get_job(conn, job_id)
        existing_output = existing_job.get("output") if existing_job else {}
        update_job(
            conn,
            job_id,
            status="failed",
            current_step="failed",
            progress=100,
            output_payload={
                **(existing_output or {}),
                **(output_payload or {}),
                "error_type": classify_job_error(exc),
                "error_detail": str(exc),
                "error_trace": traceback.format_exc(),
            },
            error_message=f"{classify_job_error(exc)}: {exc}",
            log=f"failed [{classify_job_error(exc)}]: {exc}",
            finished=True,
        )


def _mark_job_needs_llm(job_id: str, config: AppConfig, exc: LLMConfigurationError) -> None:
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        existing_job = get_job(conn, job_id)
        existing_output = existing_job.get("output") if existing_job else {}
        update_job(
            conn,
            job_id,
            status="needs_llm",
            current_step="needs_llm_report_generation",
            progress=55,
            output_payload={
                **(existing_output or {}),
                "error_type": classify_job_error(exc),
                "error_detail": str(exc),
            },
            error_message=str(exc),
            log=f"waiting for LLM configuration: {exc}",
        )


def _log_retry(job_id: str, config: AppConfig, step: str) -> Callable[[int, BaseException], None]:
    def on_retry(attempt: int, exc: BaseException) -> None:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            update_job(
                conn,
                job_id,
                current_step=step,
                log=f"retrying {step} after attempt {attempt} failed: {exc}",
            )

    return on_retry


def _run_import_job(job_id: str, config: AppConfig, arxiv_id: str) -> None:
    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            status="running",
            current_step="fetching_metadata",
            progress=10,
            log=f"fetching arXiv metadata for {arxiv_id}",
        )

    ensure_job_active(job_id, config)
    metadata = fetch_arxiv_metadata(arxiv_id)
    slug = make_paper_slug(arxiv_id, metadata.title)
    slug_root = config.source_dir / slug
    arxiv_dir = slug_root / "arxiv"
    package_path = slug_root / "arxiv.eprint"
    pdf_path = arxiv_dir / "paper.pdf"

    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            current_step="downloading_source",
            progress=25,
            log=f"metadata fetched: {metadata.title}",
        )

    ensure_job_active(job_id, config)
    retry_operation(
        lambda: download_eprint(arxiv_id, package_path),
        attempts=3,
        on_retry=_log_retry(job_id, config, "downloading_source"),
    )

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            current_step="extracting_source",
            progress=40,
            log=f"downloaded e-print to {package_path}",
        )

    ensure_job_active(job_id, config)
    package_kind = extract_source_package(package_path, arxiv_dir)
    try:
        package_path.unlink()
    except OSError:
        pass
    pdf_error = ""
    if not pdf_path.exists():
        try:
            download_pdf(metadata.pdf_url, pdf_path)
        except Exception as exc:
            pdf_error = str(exc)
    main_tex = find_main_tex(arxiv_dir)

    if main_tex is None and package_kind != "pdf":
        raise ValueError(f"No TeX file found under {arxiv_dir}")

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            current_step="detecting_code",
            progress=50,
            log="scanning paper source for public code links",
        )

    ensure_job_active(job_id, config)
    code_discovery = discover_and_clone_code(
        abstract=metadata.abstract,
        source_dir=arxiv_dir,
        target_dir=slug_root / "code",
    )
    has_code = bool(code_discovery.url)

    report_md_path = config.report_dir / f"{slug}.md"
    report_html_path = config.report_dir / f"{slug}.html"
    output_payload = {
        "slug": slug,
        "arxiv_id": arxiv_id,
        "title": metadata.title,
        "authors": metadata.authors,
        "year": metadata.year,
        "published": metadata.published,
        "abstract": metadata.abstract,
        "abs_url": metadata.abs_url,
        "pdf_url": metadata.pdf_url,
        "eprint_url": metadata.eprint_url,
        "source_dir": str(arxiv_dir),
        "source_package_kind": package_kind,
        "pdf_path": str(pdf_path) if pdf_path.exists() else "",
        "pdf_error": pdf_error,
        "main_tex_path": str(main_tex) if main_tex else "",
        "code_url": code_discovery.url,
        "code_path": code_discovery.path,
        "code_cloned": code_discovery.cloned,
        "code_error": code_discovery.error,
        "report_md_path": str(report_md_path),
        "report_html_path": str(report_html_path),
        "next_step": "llm_report_generation",
        "llm_provider": "",
        "model": "",
    }

    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        upsert_paper(
            conn,
            {
                "slug": slug,
                "arxiv_id": arxiv_id,
                "title": metadata.title,
                "authors": metadata.authors,
                "year": metadata.year,
                "abstract": metadata.abstract,
                "arxiv_url": metadata.abs_url,
                "pdf_url": metadata.pdf_url,
                "report_md_path": str(report_md_path),
                "report_html_path": str(report_html_path),
                "source_path": str(arxiv_dir),
                "code_url": code_discovery.url,
                "status": "unread",
                "reading_stage": "skim",
                "has_code": has_code,
            },
        )
        output_payload["llm_provider"] = str((get_job(conn, job_id) or {}).get("input", {}).get("llm_provider", ""))
        output_payload["model"] = str((get_job(conn, job_id) or {}).get("input", {}).get("model", ""))
        update_job(
            conn,
            job_id,
            status="needs_llm",
            current_step="needs_llm_report_generation",
            progress=55,
            output_payload=output_payload,
            paper_slug=slug,
            log=(
                f"source prepared; code repo detected: {code_discovery.url}"
                if code_discovery.url
                else "source prepared; no public code repo detected"
            ),
        )

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        input_payload = job.get("input") if job else {}

    _run_report_stage(job_id, config, input_payload or {}, output_payload)


def _run_report_stage(
    job_id: str,
    config: AppConfig,
    input_payload: dict[str, object],
    output_payload: dict[str, object],
) -> None:
    ensure_job_active(job_id, config)
    context = ReportContext(
        slug=str(output_payload["slug"]),
        metadata=fetch_arxiv_metadata(str(output_payload["arxiv_id"]))
        if not output_payload.get("title")
        else _metadata_from_output(output_payload),
        source_dir=Path(str(output_payload["source_dir"])),
        main_tex_path=Path(str(output_payload["main_tex_path"])) if output_payload.get("main_tex_path") else None,
        report_md_path=Path(str(output_payload["report_md_path"])),
        report_html_path=Path(str(output_payload["report_html_path"])),
    )
    provider_name = str(input_payload.get("llm_provider") or output_payload.get("llm_provider") or "")
    model = str(input_payload.get("model") or output_payload.get("model") or "")
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        llm_settings = effective_llm_settings(conn, config, provider_name=provider_name, model=model)
    provider = build_effective_provider(llm_settings, mock_markdown=build_mock_report(context))
    # Set report_path for Claude Code provider to check if CLI wrote report directly
    if hasattr(provider, 'report_path'):
        object.__setattr__(provider, 'report_path', str(context.report_md_path))
    output_payload = {
        **output_payload,
        "llm_provider": llm_settings["provider"],
        "model": llm_settings["model"],
    }

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            status="running",
            current_step="generating_report",
            progress=65,
            output_payload=output_payload,
            log=f"starting deep paper analysis with provider={llm_settings['provider']}",
        )

    stage_progress = {
        "reading_notes": (58, "正在精读 TeX 源码并整理阅读札记"),
        "critical_memo": (64, "正在核对相关工作并生成批判性分析备忘录"),
        "final_report": (70, "正在生成正式中文深度阅读报告"),
        "quality_repair": (76, "正在按质量规则修订报告"),
        "code_analyst": (78, "正在核对公开代码实现"),
        "html_mindmap": (81, "正在提炼 HTML 内容脑图"),
        "html_presenter": (82, "正在渲染 HTML 阅读页"),
    }

    def on_report_stage(stage: str, label: str = "") -> None:
        ensure_job_active(job_id, config)
        progress, message = stage_progress.get(stage, (65, f"running report stage: {stage}"))
        current_step = "rendering_html" if stage in {"html_mindmap", "html_presenter"} else "generating_report"
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            update_job(
                conn,
                job_id,
                current_step=current_step,
                progress=progress,
                output_payload={**output_payload, "analysis_stage": stage},
                log=message,
            )

    def on_model_run(run) -> None:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            record_model_run(
                conn,
                job_id=job_id,
                provider=llm_settings["provider"],
                model=llm_settings["model"],
                prompt_version=f"{REPORT_PROMPT_VERSION}:{run.stage}",
                prompt_text=run.prompt,
                response_text=run.response,
                input_tokens=estimate_tokens(run.prompt),
                output_tokens=estimate_tokens(run.response),
                error_message=run.error,
            )

    def on_agent_artifact(stage, artifact_type, path, content, metadata) -> None:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            record_agent_artifact(
                conn,
                job_id=job_id,
                paper_slug=context.slug,
                stage=stage,
                artifact_type=artifact_type,
                path=str(path),
                content_text=content[:12000],
                metadata=metadata,
            )

    try:
        ensure_job_active(job_id, config)
        runtime = PaperAgentRuntime(
            context,
            provider,
            root_dir=config.root_dir,
            on_stage=on_report_stage,
            on_run=on_model_run,
            on_artifact=on_agent_artifact,
        )
        generation = runtime.run()
        markdown = generation.markdown
        output_payload = {
            **output_payload,
            "agent_artifacts_dir": str(generation.artifacts_dir),
        }
    except LLMConfigurationError as exc:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            record_model_run(
                conn,
                job_id=job_id,
                provider=llm_settings["provider"],
                model=llm_settings["model"],
                prompt_version=REPORT_PROMPT_VERSION,
                prompt_text="deep report generation did not start",
                input_tokens=0,
                error_message=str(exc),
            )
        raise
    except (JobPaused, JobCanceled):
        raise
    except Exception as exc:
        with closing(connect(config.db_path)) as conn:
            init_db(conn)
            record_model_run(
                conn,
                job_id=job_id,
                provider=llm_settings["provider"],
                model=llm_settings["model"],
                prompt_version=REPORT_PROMPT_VERSION,
                prompt_text="deep report generation failed",
                input_tokens=0,
                error_message=str(exc),
            )
        raise
    ensure_job_active(job_id, config)
    if output_payload.get("code_url"):
        code_summary = summarize_code_repo(
            CodeDiscovery(
                url=str(output_payload.get("code_url", "")),
                cloned=bool(output_payload.get("code_cloned")),
                path=str(output_payload.get("code_path", "")),
                error=str(output_payload.get("code_error", "")),
            )
        )
        code_runtime = CodeAnalystRuntime(
            context,
            provider,
            root_dir=config.root_dir,
            summary=code_summary,
            on_stage=on_report_stage,
            on_run=on_model_run,
            on_artifact=on_agent_artifact,
        )
        code_generation = code_runtime.run(markdown)
        markdown = code_generation.markdown
        output_payload = {
            **output_payload,
            "code_observation_added": True,
            "code_file_count": len(code_summary.files),
            "code_entrypoints": code_summary.entrypoints,
        }
    chunks = chunk_report(markdown)
    tag_map = extract_report_tags(markdown)
    frontmatter = parse_report_frontmatter(markdown)

    ensure_job_active(job_id, config)
    output_payload = {
        **output_payload,
        "report_md_path": str(context.report_md_path),
        "report_html_path": str(context.report_html_path),
        "next_step": "render_html",
    }
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            current_step="rendering_html",
            progress=80,
            output_payload=output_payload,
            log=f"report written to {context.report_md_path}",
        )
        replace_paper_tags(conn, context.slug, tag_map)
        replace_paper_chunks(conn, context.slug, chunks)
        upsert_paper_search(
            conn,
            slug=context.slug,
            title=context.metadata.title,
            abstract=context.metadata.abstract,
            report_text=markdown,
            chunks="\n\n".join(chunk["text"] for chunk in chunks),
        )

    ensure_job_active(job_id, config)
    retry_operation(
        lambda: HtmlPresenterRuntime(
            context,
            provider,
            root_dir=config.root_dir,
            on_stage=on_report_stage,
            on_run=on_model_run,
            on_artifact=on_agent_artifact,
        ).run(),
        attempts=3,
        on_retry=_log_retry(job_id, config, "rendering_html"),
    )

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        update_job(
            conn,
            job_id,
            current_step="rebuilding_wiki",
            progress=92,
            output_payload={**output_payload, "next_step": "wiki_rebuild"},
            log=f"HTML rendered to {context.report_html_path}",
        )

    ensure_job_active(job_id, config)
    retry_operation(
        lambda: rebuild_wiki(config),
        attempts=3,
        on_retry=_log_retry(job_id, config, "rebuilding_wiki"),
    )

    ensure_job_active(job_id, config)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        upsert_paper(
            conn,
            {
                "slug": context.slug,
                "arxiv_id": context.metadata.arxiv_id,
                "title": context.metadata.title,
                "title_zh": str(frontmatter.get("title_zh") or ""),
                "authors": context.metadata.authors,
                "year": context.metadata.year,
                "abstract": context.metadata.abstract,
                "arxiv_url": context.metadata.abs_url,
                "pdf_url": context.metadata.pdf_url,
                "report_md_path": str(context.report_md_path),
                "report_html_path": str(context.report_html_path),
                "source_path": str(context.source_dir),
                "code_url": str(output_payload.get("code_url", "")),
                "status": frontmatter_status(frontmatter.get("status"), default="read"),
                "reading_stage": str(frontmatter.get("reading_stage") or "skim"),
                "review_stage": str(frontmatter.get("review_stage") or ""),
                "research_line": str(frontmatter.get("research_line") or ""),
                "line_role": str(frontmatter.get("line_role") or ""),
                "importance": frontmatter_score(frontmatter.get("importance")),
                "confidence": frontmatter_score(frontmatter.get("confidence")),
                "reproducibility": frontmatter_score(frontmatter.get("reproducibility")),
                "has_code": bool(output_payload.get("code_url")),
            },
        )
        update_job(
            conn,
            job_id,
            status="completed",
            current_step="completed",
            progress=100,
            output_payload={**output_payload, "next_step": ""},
            paper_slug=context.slug,
            log="paper import pipeline completed",
            finished=True,
        )


def _metadata_from_output(output_payload: dict[str, object]):
    from .arxiv import ArxivMetadata

    return ArxivMetadata(
        arxiv_id=str(output_payload["arxiv_id"]),
        title=str(output_payload.get("title", "")),
        authors=[str(author) for author in output_payload.get("authors", [])],
        abstract=str(output_payload.get("abstract", "")),
        published=str(output_payload.get("published", "")),
        year=int(output_payload["year"]) if output_payload.get("year") else None,
        abs_url=str(output_payload.get("abs_url", "")),
        pdf_url=str(output_payload.get("pdf_url", "")),
        eprint_url=str(output_payload.get("eprint_url", "")),
    )
