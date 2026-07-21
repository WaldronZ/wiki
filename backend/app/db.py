from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY,
            slug TEXT NOT NULL UNIQUE,
            arxiv_id TEXT UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            title_zh TEXT NOT NULL DEFAULT '',
            authors_json TEXT NOT NULL DEFAULT '[]',
            year INTEGER,
            abstract TEXT NOT NULL DEFAULT '',
            arxiv_url TEXT NOT NULL DEFAULT '',
            pdf_url TEXT NOT NULL DEFAULT '',
            code_url TEXT NOT NULL DEFAULT '',
            report_md_path TEXT NOT NULL DEFAULT '',
            report_html_path TEXT NOT NULL DEFAULT '',
            source_path TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'unread',
            reading_stage TEXT NOT NULL DEFAULT 'skim',
            review_stage TEXT NOT NULL DEFAULT '',
            last_reviewed TEXT NOT NULL DEFAULT '',
            next_review TEXT NOT NULL DEFAULT '',
            research_line TEXT NOT NULL DEFAULT '',
            line_role TEXT NOT NULL DEFAULT '',
            importance INTEGER,
            confidence INTEGER,
            reproducibility INTEGER,
            has_code INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            paper_slug TEXT,
            status TEXT NOT NULL,
            current_step TEXT NOT NULL DEFAULT '',
            progress INTEGER NOT NULL DEFAULT 0,
            input_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            logs_json TEXT NOT NULL DEFAULT '[]',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (paper_slug) REFERENCES papers(slug) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(type, normalized_name)
        );

        CREATE TABLE IF NOT EXISTS paper_tags (
            paper_slug TEXT NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (paper_slug, tag_id),
            FOREIGN KEY (paper_slug) REFERENCES papers(slug) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY,
            paper_slug TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (paper_slug) REFERENCES papers(slug) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_runs (
            id INTEGER PRIMARY KEY,
            job_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_version TEXT NOT NULL DEFAULT '',
            prompt_text TEXT NOT NULL DEFAULT '',
            response_text TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_estimate REAL,
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_artifacts (
            id INTEGER PRIMARY KEY,
            job_id TEXT NOT NULL,
            paper_slug TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL,
            artifact_type TEXT NOT NULL DEFAULT 'text',
            path TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS paper_chunks (
            id INTEGER PRIMARY KEY,
            paper_slug TEXT NOT NULL,
            source_type TEXT NOT NULL,
            section TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            token_count INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (paper_slug) REFERENCES papers(slug) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY,
            paper_slug TEXT NOT NULL,
            chunk_id INTEGER,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (paper_slug) REFERENCES papers(slug) ON DELETE CASCADE,
            FOREIGN KEY (chunk_id) REFERENCES paper_chunks(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS paper_search
        USING fts5(slug UNINDEXED, title, abstract, report_text, notes, chunks);

        CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
        CREATE INDEX IF NOT EXISTS idx_papers_status ON papers(status);
        CREATE INDEX IF NOT EXISTS idx_papers_reading_stage ON papers(reading_stage);
        CREATE INDEX IF NOT EXISTS idx_papers_importance ON papers(importance);
        CREATE INDEX IF NOT EXISTS idx_papers_has_code ON papers(has_code);
        CREATE INDEX IF NOT EXISTS idx_papers_research_line ON papers(research_line);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        CREATE INDEX IF NOT EXISTS idx_jobs_paper_slug ON jobs(paper_slug);
        CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at);
        CREATE INDEX IF NOT EXISTS idx_agent_artifacts_job_id ON agent_artifacts(job_id);
        CREATE INDEX IF NOT EXISTS idx_agent_artifacts_paper_slug ON agent_artifacts(paper_slug);
        CREATE INDEX IF NOT EXISTS idx_paper_tags_paper_slug ON paper_tags(paper_slug);
        CREATE INDEX IF NOT EXISTS idx_paper_tags_tag_id ON paper_tags(tag_id);
        CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_slug ON paper_chunks(paper_slug);
        CREATE INDEX IF NOT EXISTS idx_embeddings_paper_slug ON embeddings(paper_slug);
        CREATE INDEX IF NOT EXISTS idx_embeddings_provider_model ON embeddings(provider, model);
        """
    )
    _ensure_columns(
        conn,
        "model_runs",
        {
            "prompt_text": "TEXT NOT NULL DEFAULT ''",
            "response_text": "TEXT NOT NULL DEFAULT ''",
        },
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (SCHEMA_VERSION, utc_now()),
    )
    conn.commit()


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for column, definition in columns.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_job(
    conn: sqlite3.Connection,
    *,
    job_type: str,
    input_payload: dict[str, Any],
    paper_slug: str | None = None,
    current_step: str = "queued",
) -> str:
    now = utc_now()
    job_id = f"job_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO jobs (
            id, type, paper_slug, status, current_step, progress,
            input_json, output_json, logs_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            job_type,
            paper_slug,
            "queued",
            current_step,
            0,
            json.dumps(input_payload, ensure_ascii=False),
            "{}",
            json.dumps([f"{now} job queued"], ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    return job_id


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    progress: int | None = None,
    output_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
    log: str | None = None,
    paper_slug: str | None = None,
    finished: bool = False,
) -> None:
    row = conn.execute("SELECT logs_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"Job not found: {job_id}")

    now = utc_now()
    logs: list[str]
    try:
        logs = json.loads(str(row["logs_json"]))
        if not isinstance(logs, list):
            logs = []
    except json.JSONDecodeError:
        logs = []
    if log:
        logs.append(f"{now} {log}")

    fields: list[str] = ["updated_at = ?", "logs_json = ?"]
    values: list[Any] = [now, json.dumps(logs, ensure_ascii=False)]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if current_step is not None:
        fields.append("current_step = ?")
        values.append(current_step)
    if progress is not None:
        fields.append("progress = ?")
        values.append(max(0, min(100, int(progress))))
    if output_payload is not None:
        fields.append("output_json = ?")
        values.append(json.dumps(output_payload, ensure_ascii=False))
    if error_message is not None:
        fields.append("error_message = ?")
        values.append(error_message)
    if paper_slug is not None:
        fields.append("paper_slug = ?")
        values.append(paper_slug)
    if finished:
        fields.append("finished_at = ?")
        values.append(now)
    values.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()


def upsert_paper(conn: sqlite3.Connection, paper: dict[str, Any]) -> None:
    now = utc_now()
    payload = {
        "slug": paper["slug"],
        "arxiv_id": paper.get("arxiv_id", ""),
        "title": paper.get("title", ""),
        "title_zh": paper.get("title_zh", ""),
        "authors_json": json.dumps(paper.get("authors", []), ensure_ascii=False),
        "year": paper.get("year"),
        "abstract": paper.get("abstract", ""),
        "arxiv_url": paper.get("arxiv_url", ""),
        "pdf_url": paper.get("pdf_url", ""),
        "code_url": paper.get("code_url", ""),
        "report_md_path": paper.get("report_md_path", ""),
        "report_html_path": paper.get("report_html_path", ""),
        "source_path": paper.get("source_path", ""),
        "status": paper.get("status", "unread"),
        "reading_stage": paper.get("reading_stage", "skim"),
        "review_stage": paper.get("review_stage", ""),
        "last_reviewed": paper.get("last_reviewed", ""),
        "next_review": paper.get("next_review", ""),
        "research_line": paper.get("research_line", ""),
        "line_role": paper.get("line_role", ""),
        "importance": paper.get("importance"),
        "confidence": paper.get("confidence"),
        "reproducibility": paper.get("reproducibility"),
        "has_code": 1 if paper.get("has_code") else 0,
        "created_at": paper.get("created_at", now),
        "updated_at": now,
    }
    columns = list(payload)
    placeholders = ", ".join("?" for _ in columns)
    update_columns = [column for column in columns if column not in {"slug", "created_at"}]
    updates = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    conn.execute(
        f"""
        INSERT INTO papers ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(slug) DO UPDATE SET {updates}
        """,
        [payload[column] for column in columns],
    )
    conn.commit()


def delete_paper(conn: sqlite3.Connection, slug: str) -> dict[str, Any]:
    paper = get_paper(conn, slug)
    if paper is None:
        raise KeyError(f"Paper not found: {slug}")

    conn.execute("DELETE FROM paper_search WHERE slug = ?", (slug,))
    conn.execute("DELETE FROM embeddings WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM paper_chunks WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM agent_artifacts WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM paper_tags WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM notes WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM jobs WHERE paper_slug = ?", (slug,))
    conn.execute("DELETE FROM papers WHERE slug = ?", (slug,))
    conn.commit()
    return paper


def normalize_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def replace_paper_tags(
    conn: sqlite3.Connection,
    paper_slug: str,
    tag_map: dict[str, list[str]],
) -> None:
    now = utc_now()
    conn.execute("DELETE FROM paper_tags WHERE paper_slug = ?", (paper_slug,))
    for tag_type, names in tag_map.items():
        normalized_type = normalize_tag(tag_type).replace(" ", "_")
        if not normalized_type:
            continue
        seen: set[str] = set()
        for name in names:
            label = str(name).strip()
            normalized_name = normalize_tag(label)
            if not normalized_name or normalized_name in seen:
                continue
            seen.add(normalized_name)
            conn.execute(
                """
                INSERT INTO tags (name, normalized_name, type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(type, normalized_name) DO UPDATE SET
                    name = excluded.name,
                    updated_at = excluded.updated_at
                """,
                (label, normalized_name, normalized_type, now, now),
            )
            row = conn.execute(
                "SELECT id FROM tags WHERE type = ? AND normalized_name = ?",
                (normalized_type, normalized_name),
            ).fetchone()
            if row is None:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO paper_tags (paper_slug, tag_id, created_at)
                VALUES (?, ?, ?)
                """,
                (paper_slug, int(row["id"]), now),
            )
    conn.commit()


def update_paper_classification(
    conn: sqlite3.Connection,
    slug: str,
    *,
    research_line: str = "",
    line_role: str = "",
    tags: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT slug FROM papers WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise KeyError(f"Paper not found: {slug}")
    conn.execute(
        """
        UPDATE papers
        SET research_line = ?, line_role = ?, updated_at = ?
        WHERE slug = ?
        """,
        (research_line.strip(), line_role.strip(), utc_now(), slug),
    )
    if tags is not None:
        replace_paper_tags(conn, slug, tags)
    conn.commit()
    paper = get_paper(conn, slug)
    if paper is None:
        raise KeyError(f"Paper not found after update: {slug}")
    return paper


def record_model_run(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    provider: str,
    model: str,
    prompt_version: str,
    prompt_text: str,
    response_text: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_estimate: float | None = None,
    error_message: str = "",
) -> int:
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO model_runs (
            job_id, provider, model, prompt_version, prompt_text, response_text,
            input_tokens, output_tokens, cost_estimate, error_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            provider,
            model,
            prompt_version,
            prompt_text,
            response_text,
            input_tokens,
            output_tokens,
            cost_estimate,
            error_message,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def record_agent_artifact(
    conn: sqlite3.Connection,
    *,
    job_id: str,
    paper_slug: str,
    stage: str,
    artifact_type: str = "text",
    path: str = "",
    content_text: str = "",
    metadata: dict[str, Any] | None = None,
) -> int:
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO agent_artifacts (
            job_id, paper_slug, stage, artifact_type, path, content_text, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            paper_slug,
            stage,
            artifact_type,
            path,
            content_text,
            json.dumps(metadata or {}, ensure_ascii=False),
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_agent_artifacts(
    conn: sqlite3.Connection,
    *,
    job_id: str = "",
    paper_slug: str = "",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if job_id:
        clauses.append("job_id = ?")
        values.append(job_id)
    if paper_slug:
        clauses.append("paper_slug = ?")
        values.append(paper_slug)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT * FROM agent_artifacts
        {where}
        ORDER BY created_at ASC, id ASC
        """,
        values,
    ).fetchall()
    artifacts: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row) or {}
        try:
            item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
        except json.JSONDecodeError:
            item["metadata"] = {}
        artifacts.append(item)
    return artifacts


def replace_paper_chunks(
    conn: sqlite3.Connection,
    paper_slug: str,
    chunks: list[dict[str, Any]],
) -> None:
    now = utc_now()
    conn.execute("DELETE FROM paper_chunks WHERE paper_slug = ?", (paper_slug,))
    conn.executemany(
        """
        INSERT INTO paper_chunks (paper_slug, source_type, section, text, token_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                paper_slug,
                chunk.get("source_type", "report"),
                chunk.get("section", ""),
                chunk.get("text", ""),
                chunk.get("token_count"),
                now,
            )
            for chunk in chunks
            if str(chunk.get("text", "")).strip()
        ],
    )
    conn.commit()


def upsert_paper_search(
    conn: sqlite3.Connection,
    *,
    slug: str,
    title: str,
    abstract: str,
    report_text: str,
    notes: str = "",
    chunks: str = "",
) -> None:
    conn.execute("DELETE FROM paper_search WHERE slug = ?", (slug,))
    conn.execute(
        """
        INSERT INTO paper_search (slug, title, abstract, report_text, notes, chunks)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (slug, title, abstract, report_text, notes, chunks),
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("input_json", "output_json", "logs_json", "authors_json"):
        if key in data:
            try:
                data[key.removesuffix("_json")] = json.loads(data[key])
            except json.JSONDecodeError:
                data[key.removesuffix("_json")] = None
    return data


def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return str(row["value"])


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, now),
    )
    conn.commit()


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def list_papers(conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    return filter_papers(conn, limit=limit, offset=offset)


def _tag_match_clause(tag_type: str, tag_value: str) -> tuple[str, list[Any]]:
    normalized_type = normalize_tag(tag_type).replace(" ", "_")
    normalized_value = normalize_tag(tag_value)
    if not normalized_type or not normalized_value:
        return "", []
    return (
        """
        EXISTS (
            SELECT 1
            FROM paper_tags pt
            JOIN tags t ON t.id = pt.tag_id
            WHERE pt.paper_slug = papers.slug
              AND t.type = ?
              AND t.normalized_name LIKE ?
        )
        """,
        [normalized_type, f"%{normalized_value}%"],
    )


def _attach_tags(conn: sqlite3.Connection, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slugs = [str(paper.get("slug", "")) for paper in papers if paper.get("slug")]
    if not slugs:
        return papers
    placeholders = ", ".join("?" for _ in slugs)
    rows = conn.execute(
        f"""
        SELECT pt.paper_slug, t.type, t.name
        FROM paper_tags pt
        JOIN tags t ON t.id = pt.tag_id
        WHERE pt.paper_slug IN ({placeholders})
        ORDER BY t.type, t.name
        """,
        slugs,
    ).fetchall()
    tags_by_slug: dict[str, dict[str, list[str]]] = {
        slug: {} for slug in slugs
    }
    for row in rows:
        slug = str(row["paper_slug"])
        tag_type = str(row["type"])
        tags_by_slug.setdefault(slug, {}).setdefault(tag_type, []).append(str(row["name"]))
    for paper in papers:
        paper["tags"] = tags_by_slug.get(str(paper.get("slug", "")), {})
    return papers


def filter_papers(
    conn: sqlite3.Connection,
    *,
    status: str = "",
    importance: int | None = None,
    has_code: bool | None = None,
    research_line: str = "",
    topic: str = "",
    method: str = "",
    tag_type: str = "",
    tag: str = "",
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if status:
        clauses.append("status = ?")
        values.append(status)
    if importance is not None:
        clauses.append("importance = ?")
        values.append(importance)
    if has_code is not None:
        clauses.append("has_code = ?")
        values.append(1 if has_code else 0)
    if research_line == "__unassigned__":
        clauses.append("research_line = ''")
    elif research_line:
        clauses.append("research_line = ?")
        values.append(research_line)
    for clause, clause_values in (
        _tag_match_clause("topic", topic),
        _tag_match_clause("method", method),
        _tag_match_clause(tag_type, tag),
    ):
        if clause:
            clauses.append(clause)
            values.extend(clause_values)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.extend([limit, offset])
    rows = conn.execute(
        f"""
        SELECT * FROM papers
        {where}
        ORDER BY COALESCE(year, 0) DESC, updated_at DESC
        LIMIT ? OFFSET ?
        """,
        values,
    ).fetchall()
    return _attach_tags(conn, [row_to_dict(row) or {} for row in rows])


def list_jobs(conn: sqlite3.Connection, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM jobs
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def list_research_lines(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM papers
        ORDER BY
            CASE WHEN research_line = '' THEN 1 ELSE 0 END,
            research_line COLLATE NOCASE,
            COALESCE(year, 0) DESC,
            updated_at DESC
        """
    ).fetchall()
    papers = _attach_tags(conn, [row_to_dict(row) or {} for row in rows])
    grouped: dict[str, dict[str, Any]] = {}
    for paper in papers:
        line_name = str(paper.get("research_line") or "Unassigned")
        role = str(paper.get("line_role") or "Unassigned")
        line = grouped.setdefault(
            line_name,
            {
                "name": line_name,
                "count": 0,
                "roles": {},
            },
        )
        line["count"] += 1
        line["roles"].setdefault(role, []).append(paper)
    return list(grouped.values())


def list_review_queue(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
    today: str | None = None,
) -> list[dict[str, Any]]:
    today = today or datetime.now(timezone.utc).date().isoformat()
    rows = conn.execute(
        """
        SELECT * FROM papers
        WHERE status != 'archived'
        ORDER BY
            CASE
                WHEN next_review != '' AND next_review <= ? THEN 0
                WHEN next_review != '' THEN 1
                ELSE 2
            END,
            COALESCE(importance, 0) DESC,
            CASE WHEN next_review = '' THEN '9999-12-31' ELSE next_review END ASC,
            updated_at DESC
        LIMIT ?
        """,
        (today, limit),
    ).fetchall()
    papers = _attach_tags(conn, [row_to_dict(row) or {} for row in rows])
    for paper in papers:
        next_review = str(paper.get("next_review") or "")
        if next_review and next_review <= today:
            paper["review_priority"] = "due"
        elif next_review:
            paper["review_priority"] = "scheduled"
        else:
            paper["review_priority"] = "unscheduled"
    return papers


def get_taxonomy_cleanup(
    conn: sqlite3.Connection,
    *,
    sparse_threshold: int = 1,
    overloaded_threshold: int = 20,
    missing_limit: int = 50,
) -> dict[str, Any]:
    tag_counts = conn.execute(
        """
        SELECT t.type, t.name, t.normalized_name, COUNT(pt.paper_slug) AS paper_count
        FROM tags t
        LEFT JOIN paper_tags pt ON pt.tag_id = t.id
        GROUP BY t.id
        ORDER BY t.type, paper_count DESC, t.name
        """
    ).fetchall()
    duplicate_rows = conn.execute(
        """
        SELECT normalized_name, COUNT(*) AS tag_count, GROUP_CONCAT(type || ':' || name, ', ') AS labels
        FROM tags
        GROUP BY normalized_name
        HAVING COUNT(*) > 1
        ORDER BY tag_count DESC, normalized_name
        """
    ).fetchall()
    missing_rows = conn.execute(
        """
        SELECT * FROM papers
        WHERE research_line = ''
           OR NOT EXISTS (
                SELECT 1 FROM paper_tags pt
                JOIN tags t ON t.id = pt.tag_id
                WHERE pt.paper_slug = papers.slug AND t.type = 'topic'
           )
           OR NOT EXISTS (
                SELECT 1 FROM paper_tags pt
                JOIN tags t ON t.id = pt.tag_id
                WHERE pt.paper_slug = papers.slug AND t.type = 'method'
           )
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (missing_limit,),
    ).fetchall()
    tags = [dict(row) for row in tag_counts]
    sparse = [
        tag for tag in tags if int(tag["paper_count"]) <= sparse_threshold
    ]
    overloaded = [
        tag for tag in tags if int(tag["paper_count"]) >= overloaded_threshold
    ]
    missing_metadata = _attach_tags(
        conn,
        [row_to_dict(row) or {} for row in missing_rows],
    )
    return {
        "duplicates": [dict(row) for row in duplicate_rows],
        "sparse": sparse,
        "overloaded": overloaded,
        "missing_metadata": missing_metadata,
    }


def get_quality_report(conn: sqlite3.Connection, report_dir: Path) -> dict[str, Any]:
    duplicate_titles = [
        dict(row)
        for row in conn.execute(
            """
            SELECT lower(trim(title)) AS normalized_title, COUNT(*) AS paper_count,
                   GROUP_CONCAT(slug, ', ') AS slugs
            FROM papers
            WHERE trim(title) != ''
            GROUP BY lower(trim(title))
            HAVING COUNT(*) > 1
            ORDER BY paper_count DESC, normalized_title
            """
        ).fetchall()
    ]
    duplicate_arxiv_ids = [
        dict(row)
        for row in conn.execute(
            """
            SELECT arxiv_id, COUNT(*) AS paper_count, GROUP_CONCAT(slug, ', ') AS slugs
            FROM papers
            WHERE trim(arxiv_id) != ''
            GROUP BY arxiv_id
            HAVING COUNT(*) > 1
            ORDER BY paper_count DESC, arxiv_id
            """
        ).fetchall()
    ]

    papers = [row_to_dict(row) or {} for row in conn.execute("SELECT * FROM papers").fetchall()]
    missing_report_files: list[dict[str, str]] = []
    malformed_metadata: list[dict[str, str]] = []
    latest_report_mtime = 0.0
    for paper in papers:
        slug = str(paper.get("slug") or "")
        for field in ("report_md_path", "report_html_path"):
            path_text = str(paper.get(field) or "")
            if not path_text:
                missing_report_files.append({"slug": slug, "field": field, "path": ""})
                continue
            path = Path(path_text)
            if not path.exists():
                missing_report_files.append({"slug": slug, "field": field, "path": path_text})
                continue
            latest_report_mtime = max(latest_report_mtime, path.stat().st_mtime)
        md_path_text = str(paper.get("report_md_path") or "")
        md_path = Path(md_path_text) if md_path_text else None
        if md_path and md_path.exists():
            issue = _frontmatter_issue(md_path, slug)
            if issue:
                malformed_metadata.append({"slug": slug, "path": md_path_text, "issue": issue})

    wiki_files = [
        report_dir / "papers.json",
        report_dir / "search_index.json",
        report_dir / "index.html",
        report_dir / "tags.html",
    ]
    wiki_issues: list[dict[str, str]] = []
    for path in wiki_files:
        if not path.exists():
            wiki_issues.append({"path": str(path), "issue": "missing"})
        elif latest_report_mtime and path.stat().st_mtime < latest_report_mtime:
            wiki_issues.append({"path": str(path), "issue": "stale"})

    return {
        "summary": {
            "paper_count": len(papers),
            "issue_count": (
                len(duplicate_titles)
                + len(duplicate_arxiv_ids)
                + len(missing_report_files)
                + len(malformed_metadata)
                + len(wiki_issues)
            ),
        },
        "duplicate_titles": duplicate_titles,
        "duplicate_arxiv_ids": duplicate_arxiv_ids,
        "missing_report_files": missing_report_files,
        "malformed_metadata": malformed_metadata,
        "wiki_issues": wiki_issues,
    }


def _frontmatter_issue(md_path: Path, expected_slug: str) -> str:
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    match = re.match(r"(?s)^---\n(.*?)\n---", text)
    if not match:
        return "missing_frontmatter"
    frontmatter = match.group(1)
    required = ("slug", "title", "arxiv_id", "year", "topics", "methods", "status")
    for key in required:
        if not re.search(rf"(?m)^{re.escape(key)}\s*:", frontmatter):
            return f"missing_frontmatter_field:{key}"
    slug_match = re.search(r"(?m)^slug\s*:\s*[\"']?([^\"'\n]+)", frontmatter)
    if slug_match and slug_match.group(1).strip() != expected_slug:
        return "slug_mismatch"
    return ""


def get_paper(conn: sqlite3.Connection, slug: str) -> dict[str, Any] | None:
    paper = row_to_dict(conn.execute("SELECT * FROM papers WHERE slug = ?", (slug,)).fetchone())
    if paper is None:
        return None
    return _attach_tags(conn, [paper])[0]


def get_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def search_papers(conn: sqlite3.Connection, query: str, *, limit: int = 25) -> list[dict[str, Any]]:
    safe_query = " ".join(
        f'"{part.replace(chr(34), " ")}"' for part in query.split() if part.strip()
    )
    if not safe_query:
        return []
    rows = conn.execute(
        """
        SELECT
            papers.*,
            snippet(paper_search, 3, '<mark>', '</mark>', '...', 16) AS snippet,
            bm25(paper_search) AS rank
        FROM paper_search
        JOIN papers ON papers.slug = paper_search.slug
        WHERE paper_search MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (safe_query, limit),
    ).fetchall()
    return _attach_tags(conn, [row_to_dict(row) or {} for row in rows])
