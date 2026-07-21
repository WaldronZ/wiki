from __future__ import annotations

import json
import subprocess
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .config import load_config
from .db import (
    connect,
    create_job,
    delete_paper,
    get_all_settings,
    get_job,
    get_paper,
    filter_papers,
    get_quality_report,
    get_taxonomy_cleanup,
    get_setting,
    init_db,
    list_agent_artifacts,
    list_jobs,
    list_papers,
    list_review_queue,
    list_research_lines,
    search_papers,
    set_setting,
    update_job,
    update_paper_classification,
)
from .services.arxiv import normalize_arxiv_input
from .services.ingestion import run_import_queue as run_import_job
from .services.library import find_duplicate
from .services.llm import LLMConfigurationError, LLMGenerationError, list_claude_profiles, test_llm_connection
from .services.report import rebuild_wiki as rebuild_wiki_files
from .services.semantic import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    normalize_embedding_settings,
    rebuild_semantic_index,
    semantic_search,
)


class ImportPaperRequest(BaseModel):
    url: str = Field(..., min_length=1)
    force: bool = False
    llm_provider: str = ""
    model: str = ""


class ImportPaperResponse(BaseModel):
    job_id: str | None = None
    status: str
    duplicate: bool = False
    arxiv_id: str
    existing_slug: str = ""
    existing_report_path: str = ""
    message: str = ""


class AppSettingsRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    report_dir: str | None = None
    source_dir: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: str | None = None


class LLMConnectionTestRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    openai_base_url: str | None = None
    openai_api_key: str | None = None


class ApiProfileRequest(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    llm_provider: str = "openai"
    llm_model: str = "gpt-4.1"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str | None = None


class DirectoryPickerRequest(BaseModel):
    current_path: str = ""
    prompt: str = "选择文件夹"


class PaperClassificationRequest(BaseModel):
    research_line: str = ""
    line_role: str = ""
    topics: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


app = FastAPI(title="AutoPaperReader API", version="0.1.0")
API_PROFILES_SETTING = "api_key_profiles"
ACTIVE_API_PROFILE_SETTING = "active_api_profile_id"


@app.on_event("startup")
def startup() -> None:
    config = load_config()
    config.report_dir.mkdir(parents=True, exist_ok=True)
    config.source_dir.mkdir(parents=True, exist_ok=True)
    with closing(connect(config.db_path)) as conn:
        init_db(conn)


@app.get("/api/health")
def health() -> dict[str, Any]:
    config = load_config()
    return {
        "status": "ok",
        "db_path": str(config.db_path),
        "report_dir": str(config.report_dir),
        "source_dir": str(config.source_dir),
    }


def public_settings_payload(settings: dict[str, str], config) -> dict[str, Any]:
    api_key = settings.get("openai_api_key") or config.openai_api_key
    embedding = normalize_embedding_settings(
        provider=settings.get("embedding_provider", ""),
        model=settings.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        dimension=settings.get("embedding_dimension", str(DEFAULT_EMBEDDING_DIMENSION)),
    )
    return {
        "llm_provider": settings.get("llm_provider", "openai"),
        "llm_model": settings.get("llm_model", "gpt-4.1"),
        "openai_base_url": settings.get("openai_base_url", config.openai_base_url),
        "openai_api_key_set": bool(api_key),
        "embedding_enabled": embedding["enabled"],
        "embedding_provider": embedding["provider"],
        "embedding_model": embedding["model"],
        "embedding_dimension": embedding["dimension"],
        "report_dir": str(Path(settings.get("report_dir", "")).expanduser().resolve()) if settings.get("report_dir", "").strip() else str(config.report_dir),
        "source_dir": str(Path(settings.get("source_dir", "")).expanduser().resolve()) if settings.get("source_dir", "").strip() else str(config.source_dir),
        "db_path": str(config.db_path),
        "active_api_profile_id": settings.get(ACTIVE_API_PROFILE_SETTING, ""),
    }


def _load_api_profiles(settings: dict[str, str]) -> list[dict[str, str]]:
    raw = settings.get(API_PROFILES_SETTING, "[]")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    profiles: list[dict[str, str]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not profile_id or not name:
            continue
        profiles.append({
            "id": profile_id,
            "name": name,
            "llm_provider": str(item.get("llm_provider") or "openai").strip(),
            "llm_model": str(item.get("llm_model") or "gpt-4.1").strip(),
            "openai_base_url": str(item.get("openai_base_url") or "https://api.openai.com/v1").strip(),
            "openai_api_key": str(item.get("openai_api_key") or ""),
        })
    return profiles


def _public_api_profiles(settings: dict[str, str]) -> list[dict[str, Any]]:
    active_id = settings.get(ACTIVE_API_PROFILE_SETTING, "")
    return [
        {
            "id": profile["id"],
            "name": profile["name"],
            "llm_provider": profile["llm_provider"],
            "llm_model": profile["llm_model"],
            "openai_base_url": profile["openai_base_url"],
            "api_key_set": bool(profile["openai_api_key"]),
            "is_active": profile["id"] == active_id,
        }
        for profile in _load_api_profiles(settings)
    ]


def _applescript_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


@app.post("/api/system/select-directory")
def select_directory(request: DirectoryPickerRequest) -> dict[str, str]:
    prompt = request.prompt.strip() or "选择文件夹"
    command = f"choose folder with prompt {_applescript_string(prompt)}"
    if request.current_path.strip():
        current_path = Path(request.current_path).expanduser()
        if current_path.exists():
            command += f" default location POSIX file {_applescript_string(str(current_path))}"
    script = f"POSIX path of ({command})"

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=501, detail="当前系统不支持原生文件夹选择") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="文件夹选择超时") from exc

    if result.returncode != 0:
        message = (result.stderr or "").strip()
        if "User canceled" in message or "用户已取消" in message:
            raise HTTPException(status_code=409, detail="已取消选择")
        raise HTTPException(status_code=500, detail=message or "无法打开文件夹选择器")

    selected_path = result.stdout.strip()
    if not selected_path:
        raise HTTPException(status_code=500, detail="没有选择任何文件夹")
    return {"path": str(Path(selected_path).expanduser().resolve())}


@app.get("/api/settings")
def read_settings() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
    return public_settings_payload(settings, config)


@app.get("/api/settings/api-profiles")
def list_api_profiles() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
    return {"items": _public_api_profiles(settings)}


@app.get("/api/claude-profiles")
def list_claude_code_profiles() -> dict[str, Any]:
    """List available Claude Code profiles from ~/.claude/profiles/*.env."""
    return {"items": list_claude_profiles()}


@app.post("/api/settings/api-profiles")
def save_api_profile(request: ApiProfileRequest) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
        profiles = _load_api_profiles(settings)
        profile_id = (request.id or "").strip() or f"profile_{uuid.uuid4().hex}"
        existing = next((profile for profile in profiles if profile["id"] == profile_id), None)
        api_key = (request.openai_api_key or "").strip()
        if not api_key and existing:
            api_key = existing.get("openai_api_key", "")
        if not api_key:
            api_key = settings.get("openai_api_key") or config.openai_api_key
        if not api_key:
            raise HTTPException(status_code=422, detail="请先填写 API Key，再保存为密钥配置。")
        next_profile = {
            "id": profile_id,
            "name": request.name.strip(),
            "llm_provider": (request.llm_provider or "openai").strip(),
            "llm_model": (request.llm_model or "gpt-4.1").strip(),
            "openai_base_url": (request.openai_base_url or config.openai_base_url).strip(),
            "openai_api_key": api_key,
        }
        profiles = [profile for profile in profiles if profile["id"] != profile_id]
        profiles.append(next_profile)
        set_setting(conn, API_PROFILES_SETTING, json.dumps(profiles, ensure_ascii=False))
        if settings.get(ACTIVE_API_PROFILE_SETTING) == profile_id:
            set_setting(conn, "llm_provider", next_profile["llm_provider"])
            set_setting(conn, "llm_model", next_profile["llm_model"])
            set_setting(conn, "openai_base_url", next_profile["openai_base_url"])
            set_setting(conn, "openai_api_key", next_profile["openai_api_key"])
        settings = get_all_settings(conn)
    return {
        "settings": public_settings_payload(settings, config),
        "items": _public_api_profiles(settings),
    }


@app.post("/api/settings/api-profiles/{profile_id}/activate")
def activate_api_profile(profile_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
        profiles = _load_api_profiles(settings)
        profile = next((item for item in profiles if item["id"] == profile_id), None)
        if profile is None:
            raise HTTPException(status_code=404, detail="密钥配置不存在")
        set_setting(conn, "llm_provider", profile["llm_provider"])
        set_setting(conn, "llm_model", profile["llm_model"])
        set_setting(conn, "openai_base_url", profile["openai_base_url"])
        set_setting(conn, "openai_api_key", profile["openai_api_key"])
        set_setting(conn, ACTIVE_API_PROFILE_SETTING, profile["id"])
        settings = get_all_settings(conn)
    return {
        "settings": public_settings_payload(settings, config),
        "items": _public_api_profiles(settings),
    }


@app.post("/api/settings/api-profiles/{profile_id}/deactivate")
def deactivate_api_profile(profile_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
        if settings.get(ACTIVE_API_PROFILE_SETTING) == profile_id:
            set_setting(conn, ACTIVE_API_PROFILE_SETTING, "")
        settings = get_all_settings(conn)
    return {
        "settings": public_settings_payload(settings, config),
        "items": _public_api_profiles(settings),
    }


@app.post("/api/settings/api-profiles/{profile_id}/test")
def test_api_profile(profile_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
        profiles = _load_api_profiles(settings)
    profile = next((item for item in profiles if item["id"] == profile_id), None)
    if profile is None:
        raise HTTPException(status_code=404, detail="密钥配置不存在")

    llm_settings = {
        "provider": profile["llm_provider"],
        "model": profile["llm_model"],
        "openai_base_url": profile["openai_base_url"],
        "openai_api_key": profile["openai_api_key"],
    }
    try:
        response_text = test_llm_connection(llm_settings)
    except (LLMConfigurationError, LLMGenerationError) as exc:
        return {
            "ok": False,
            "message": str(exc),
            "provider": llm_settings["provider"],
            "model": llm_settings["model"],
        }
    return {
        "ok": True,
        "message": f"连接成功，模型返回：{response_text[:80]}",
        "provider": llm_settings["provider"],
        "model": llm_settings["model"],
    }


@app.delete("/api/settings/api-profiles/{profile_id}")
def delete_api_profile(profile_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
        profiles = [profile for profile in _load_api_profiles(settings) if profile["id"] != profile_id]
        set_setting(conn, API_PROFILES_SETTING, json.dumps(profiles, ensure_ascii=False))
        if settings.get(ACTIVE_API_PROFILE_SETTING) == profile_id:
            set_setting(conn, ACTIVE_API_PROFILE_SETTING, "")
        settings = get_all_settings(conn)
    return {"items": _public_api_profiles(settings)}


@app.patch("/api/settings")
def update_settings(request: AppSettingsRequest) -> dict[str, Any]:
    config = load_config()
    allowed = {
        "llm_provider": request.llm_provider,
        "llm_model": request.llm_model,
        "openai_base_url": request.openai_base_url,
        "openai_api_key": request.openai_api_key,
        "report_dir": request.report_dir,
        "source_dir": request.source_dir,
        "embedding_provider": request.embedding_provider,
        "embedding_model": request.embedding_model,
        "embedding_dimension": request.embedding_dimension,
    }
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        for key, value in allowed.items():
            if value is not None:
                set_setting(conn, key, value.strip())
        settings = get_all_settings(conn)
    payload = public_settings_payload(settings, config)
    Path(str(payload["report_dir"])).mkdir(parents=True, exist_ok=True)
    Path(str(payload["source_dir"])).mkdir(parents=True, exist_ok=True)
    return payload


@app.post("/api/settings/test-llm")
def test_llm_settings(request: LLMConnectionTestRequest) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        settings = get_all_settings(conn)
    llm_settings = {
        "provider": (request.llm_provider or settings.get("llm_provider") or "openai").strip(),
        "model": (request.llm_model or settings.get("llm_model") or "gpt-4.1").strip(),
        "openai_base_url": (request.openai_base_url or settings.get("openai_base_url") or config.openai_base_url).strip(),
        "openai_api_key": (
            request.openai_api_key
            if request.openai_api_key and request.openai_api_key.strip()
            else settings.get("openai_api_key") or config.openai_api_key
        ).strip(),
    }
    try:
        response_text = test_llm_connection(llm_settings)
    except (LLMConfigurationError, LLMGenerationError) as exc:
        return {
            "ok": False,
            "message": str(exc),
            "provider": llm_settings["provider"],
            "model": llm_settings["model"],
        }
    return {
        "ok": True,
        "message": f"连接成功，模型返回：{response_text[:80]}",
        "provider": llm_settings["provider"],
        "model": llm_settings["model"],
    }


@app.post("/api/papers/import", response_model=ImportPaperResponse)
def import_paper(request: ImportPaperRequest, background_tasks: BackgroundTasks) -> ImportPaperResponse:
    try:
        normalized = normalize_arxiv_input(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        llm_provider = request.llm_provider or get_setting(conn, "llm_provider", "openai")
        model = request.model or get_setting(conn, "llm_model", "gpt-4.1")
        duplicate = find_duplicate(conn, config.report_dir, normalized.arxiv_id)
        if duplicate.duplicate and not request.force:
            return ImportPaperResponse(
                status="duplicate",
                duplicate=True,
                arxiv_id=normalized.arxiv_id,
                existing_slug=duplicate.slug,
                existing_report_path=duplicate.report_path,
                message="Paper already exists. Re-run requires force=true.",
            )

        job_id = create_job(
            conn,
            job_type="paper_import",
            input_payload={
                "url": request.url,
                "arxiv_id": normalized.arxiv_id,
                "abs_url": normalized.abs_url,
                "pdf_url": normalized.pdf_url,
                "eprint_url": normalized.eprint_url,
                "force": request.force,
                "llm_provider": llm_provider,
                "model": model,
            },
        )
    background_tasks.add_task(run_import_job, config, job_id)
    return ImportPaperResponse(status="queued", arxiv_id=normalized.arxiv_id, job_id=job_id)


@app.get("/api/jobs")
def read_jobs(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        jobs = list_jobs(conn, limit=limit, offset=offset)
    return {"items": jobs, "limit": limit, "offset": offset}


@app.get("/api/jobs/{job_id}")
def read_job(job_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/artifacts")
def read_job_artifacts(job_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        artifacts = list_agent_artifacts(conn, job_id=job_id)
    return {"job_id": job_id, "items": artifacts}


@app.post("/api/jobs/{job_id}/run")
def run_job(job_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] not in {"paused", "needs_llm", "failed"}:
            raise HTTPException(status_code=409, detail="当前任务状态不能继续执行")
        resume_status = "needs_llm" if job.get("output") else "queued"
        update_job(
            conn,
            job_id,
            status=resume_status,
            error_message="",
            log="analysis resumed",
        )
        job = get_job(conn, job_id)
    background_tasks.add_task(run_import_job, config, job_id)
    return {"status": resume_status, "job_id": job_id, "job": job}


@app.post("/api/jobs/{job_id}/pause")
def pause_job(job_id: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] not in {"queued", "running", "needs_llm"}:
            raise HTTPException(status_code=409, detail="当前任务状态不能暂停")
        update_job(
            conn,
            job_id,
            status="paused",
            log="analysis paused by user",
        )
        job = get_job(conn, job_id)
    return {"status": "paused", "job_id": job_id, "job": job}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, background_tasks: BackgroundTasks) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        job = get_job(conn, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job["status"] in {"completed", "canceled"}:
            raise HTTPException(status_code=409, detail="当前任务已经结束")
        update_job(
            conn,
            job_id,
            status="canceled",
            current_step="canceled",
            error_message="",
            log="analysis canceled by user",
            finished=True,
        )
        job = get_job(conn, job_id)
    background_tasks.add_task(run_import_job, config)
    return {"status": "canceled", "job_id": job_id, "job": job}


@app.get("/api/papers")
def read_papers(
    limit: int = 100,
    offset: int = 0,
    status: str = "",
    importance: int | None = None,
    has_code: str = "",
    research_line: str = "",
    topic: str = "",
    method: str = "",
    tag_type: str = "",
    tag: str = "",
) -> dict[str, Any]:
    config = load_config()
    code_filter: bool | None = None
    if has_code.lower() in {"yes", "true", "1"}:
        code_filter = True
    elif has_code.lower() in {"no", "false", "0"}:
        code_filter = False
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        papers = filter_papers(
            conn,
            status=status,
            importance=importance,
            has_code=code_filter,
            research_line=research_line,
            topic=topic,
            method=method,
            tag_type=tag_type,
            tag=tag,
            limit=limit,
            offset=offset,
        )
    return {"items": papers, "limit": limit, "offset": offset}


@app.get("/api/papers/{slug}")
def read_paper(slug: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        paper = get_paper(conn, slug)
    if paper is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@app.get("/api/papers/{slug}/artifacts")
def read_paper_artifacts(slug: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        paper = get_paper(conn, slug)
        if paper is None:
            raise HTTPException(status_code=404, detail="Paper not found")
        artifacts = list_agent_artifacts(conn, paper_slug=slug)
    return {"slug": slug, "items": artifacts}


@app.patch("/api/papers/{slug}/classification")
def update_classification(slug: str, request: PaperClassificationRequest) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        try:
            paper = update_paper_classification(
                conn,
                slug,
                research_line=request.research_line,
                line_role=request.line_role,
                tags={
                    "topic": request.topics,
                    "method": request.methods,
                },
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc
    return paper


@app.delete("/api/papers/{slug}")
def remove_paper(slug: str) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        try:
            paper = delete_paper(conn, slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Paper not found") from exc

    deleted_files: list[str] = []
    file_errors: list[str] = []
    for key in ("report_md_path", "report_html_path"):
        path_text = str(paper.get(key) or "").strip()
        if not path_text:
            continue
        path = Path(path_text).expanduser()
        try:
            if path.exists() and path.is_file():
                path.unlink()
                deleted_files.append(str(path))
        except OSError as exc:
            file_errors.append(f"{path}: {exc}")

    wiki_error = ""
    try:
        rebuild_wiki_files(config)
    except RuntimeError as exc:
        wiki_error = str(exc)

    return {
        "status": "deleted",
        "slug": slug,
        "deleted_files": deleted_files,
        "file_errors": file_errors,
        "wiki_error": wiki_error,
    }


@app.get("/api/search")
def search_library(q: str, limit: int = 25) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        results = search_papers(conn, q, limit=limit)
    return {"items": results, "query": q, "limit": limit}


def _embedding_settings_or_404(conn, config) -> dict[str, Any]:
    settings = get_all_settings(conn)
    embedding = normalize_embedding_settings(
        provider=settings.get("embedding_provider", ""),
        model=settings.get("embedding_model", DEFAULT_EMBEDDING_MODEL),
        dimension=settings.get("embedding_dimension", str(DEFAULT_EMBEDDING_DIMENSION)),
    )
    if not embedding["enabled"]:
        raise HTTPException(
            status_code=409,
            detail="Semantic search is disabled. Set embedding_provider to local-hash first.",
        )
    return embedding


@app.post("/api/semantic/reindex")
def reindex_semantic_search() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        embedding = _embedding_settings_or_404(conn, config)
        result = rebuild_semantic_index(
            conn,
            provider=str(embedding["provider"]),
            model=str(embedding["model"]),
            dimension=int(embedding["dimension"]),
        )
    return {"status": "ok", **result}


@app.get("/api/semantic/search")
def search_semantic(q: str, limit: int = 10) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        embedding = _embedding_settings_or_404(conn, config)
        results = semantic_search(
            conn,
            q,
            provider=str(embedding["provider"]),
            model=str(embedding["model"]),
            dimension=int(embedding["dimension"]),
            limit=limit,
        )
    return {"items": results, "query": q, "limit": limit}


@app.get("/api/research-lines")
def read_research_lines() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        lines = list_research_lines(conn)
    return {"items": lines}


@app.get("/api/review-queue")
def read_review_queue(limit: int = 100) -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        papers = list_review_queue(conn, limit=limit)
    return {"items": papers, "limit": limit}


@app.get("/api/taxonomy-cleanup")
def read_taxonomy_cleanup() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        return get_taxonomy_cleanup(conn)


@app.get("/api/quality")
def read_quality_report() -> dict[str, Any]:
    config = load_config()
    with closing(connect(config.db_path)) as conn:
        init_db(conn)
        return get_quality_report(conn, config.report_dir)


@app.post("/api/wiki/rebuild")
def rebuild_wiki() -> dict[str, Any]:
    config = load_config()
    script = config.root_dir / "scripts" / "build_wiki.py"
    if not script.exists():
        raise HTTPException(status_code=500, detail=f"Missing script: {script}")
    result = subprocess.run(
        ["python3", str(script), str(config.report_dir)],
        cwd=config.root_dir,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={"message": "Wiki rebuild failed", "stderr": result.stderr},
        )
    return {
        "status": "ok",
        "report_dir": str(config.report_dir),
        "stdout": result.stdout,
    }


@app.get("/api/files")
def read_local_file(path: str = Query(..., min_length=1)):
    config = load_config()
    target = Path(path).expanduser().resolve()
    allowed_roots = [config.report_dir.resolve(), config.source_dir.resolve()]
    if not any(target == root or target.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="File is outside AutoPaperReader data directories")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


def _safe_report_asset(asset_path: str) -> Path:
    config = load_config()
    assets_root = (config.report_dir / "assets").resolve()
    target = (assets_root / asset_path).resolve()
    if not (target == assets_root or target.is_relative_to(assets_root)):
        raise HTTPException(status_code=404, detail="Asset not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return target


@app.get("/api/assets/{asset_path:path}", include_in_schema=False)
def read_report_asset(asset_path: str):
    return FileResponse(_safe_report_asset(asset_path))


def frontend_dist() -> Path:
    return load_config().root_dir / "frontend" / "dist"


def _safe_frontend_asset(dist: Path, asset_path: str) -> Path:
    target = (dist / "assets" / asset_path).resolve()
    if not str(target).startswith(str((dist / "assets").resolve())):
        raise HTTPException(status_code=404, detail="Asset not found")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return target


@app.get("/", include_in_schema=False)
def read_frontend_index():
    dist = frontend_dist()
    index_path = dist / "index.html"
    if not index_path.exists():
        return HTMLResponse(
            "<h1>AutoPaperReader API is running</h1><p>Run npm run build in frontend/ to serve the desktop UI.</p>",
            status_code=200,
        )
    return FileResponse(index_path)


@app.get("/assets/{asset_path:path}", include_in_schema=False)
def read_frontend_asset(asset_path: str):
    return FileResponse(_safe_frontend_asset(frontend_dist(), asset_path))
