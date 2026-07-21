# Design: Local App Architecture

## Proposed Stack

- Frontend: React + Vite.
- Backend: FastAPI.
- Primary database: SQLite via SQLModel or SQLAlchemy.
- Background jobs: SQLite-backed local analysis queue.
- LLM: provider interface with OpenAI-compatible client first.
- Search: SQLite FTS5 for full-text search in the first scalable version; optional `sqlite-vec` or Qdrant local mode for semantic search later.
- Packaging: start with local web app; later wrap with Tauri or Electron.

## High-Level Flow

1. User submits an arXiv URL in the frontend.
2. Backend normalizes the URL and extracts `arxiv_id`.
3. Backend checks the database and existing `docs/<arxiv_id>-*.md` files for duplicates.
4. Backend creates an import job.
5. Worker downloads arXiv metadata, source tarball, and optional code repository.
6. Worker builds a local paper context package.
7. Worker runs the Paper Agent Harness to produce reading notes, critical memo, final report, and quality repair artifacts.
8. If code exists, worker runs the Code Analyst Harness to append a structured implementation-observation section.
9. Worker runs the HTML Presenter Harness to render and validate a single-paper HTML report.
10. Worker runs `python3 scripts/build_wiki.py <report_dir>`.
11. Backend stores the final paper metadata, internal agent artifact paths, and report paths for the UI.

## Paper Agent Harness

The desktop app does not treat the LLM API as a one-shot report generator. It wraps model calls in a deterministic local harness inspired by Claude Code / Codex style workflows:

- **Context builder:** extracts ordered TeX context, figure/table map, bibliography snippets, related-work arXiv metadata, local PDF fallback paths, and long-term user preferences.
- **Memory layer:** loads durable Markdown preferences from `memory/` and injects them into analysis stages.
- **Paper-analyst runtime:** runs separate prompts for reading notes, critical analysis, final report generation, and quality repair. It also passes a related-work evidence package built from arXiv ids found in TeX/BibTeX, so criticism can cite concrete external paper metadata when available.
- **Code-analyst runtime:** when a public code repository is cloned, reads prioritized README/config/entrypoint/source files, asks the LLM to produce `## 10. 代码实现观察`, validates required `10.1`-`10.4` subsections, then runs a second revision pass that can directly correct `## 8. 方法细节` and `## 9. 实验` with `（已据代码核对修订）` markers. If either model output is invalid, it falls back to a deterministic structured observation without corrupting the original report.
- **HTML-presenter runtime:** records the original presenter contract, asks the LLM to distill a report-specific Markmap source, renders through `scripts/render_report_html.py`, captures renderer logs, and validates the generated HTML before the wiki rebuild. If mindmap generation fails validation, the renderer uses its deterministic fallback map without blocking the report.
- **Artifacts:** writes `context.json`, `figure_map.txt`, `memory_context.md`, `reading_notes.md`, `critical_memo.md`, `draft_report.md`, `quality_report.json`, and `final_report.md` under `docs/artifacts/<slug>/`.
- **Quality gates:** validates frontmatter, required sections, inline figure handling, and figure interpretation before accepting the report.
- **Internal audit trail:** stores artifacts in SQLite and under `docs/artifacts/<slug>/` for debugging and quality review. This is intentionally kept out of the main product UI unless a developer needs to inspect it.

## Core Modules

### Backend API

- `POST /api/papers/import`: create a paper import job.
- `GET /api/jobs/{id}`: return progress, current step, errors, and output paths.
- `GET /api/papers`: list papers with filters.
- `GET /api/papers/{slug}`: return metadata and report paths.
- `PATCH /api/papers/{slug}`: update status, tags, importance, review fields, and notes.
- `POST /api/wiki/rebuild`: manually refresh generated wiki files.

### Database

Initial tables:

- `papers`: arXiv id, slug, title, translated title, authors JSON, year, abstract, URLs, report paths, source paths, status fields, review fields, quality scores, timestamps.
- `jobs`: type, paper slug, status, current step, progress, input payload, output payload, logs, error message, timestamps.
- `tags`: normalized tag values with field/type information such as `domain`, `track`, `topic`, `method`, and `problem`.
- `paper_tags`: many-to-many relation between papers and tags.
- `notes`: user note text linked to a paper.
- `settings`: provider configuration metadata, report directory, source directory, default model, and packaging paths.
- `model_runs`: provider, model, prompt version, token usage, cost estimate, and error metadata for reproducibility.
- `agent_artifacts`: context packages, reading notes, critical memos, quality reports, and other harness outputs linked to jobs and papers.
- `paper_chunks`: report/source chunks for full-text and future semantic search.
- `embeddings`: optional local vector metadata when using `sqlite-vec`; if Qdrant is selected, SQLite stores only chunk ids and vector collection references.

Recommended indexes:

- Unique index on `papers.slug`.
- Unique nullable index on `papers.arxiv_id`.
- Indexes on `papers.year`, `papers.status`, `papers.reading_stage`, `papers.importance`, `papers.has_code`, and `papers.research_line`.
- Indexes on `jobs.status`, `jobs.paper_slug`, and `jobs.updated_at`.
- Indexes on `paper_tags.paper_slug` and `paper_tags.tag_id`.
- Index on `paper_chunks.paper_slug`.
- FTS5 virtual table over title, abstract, report text, notes, and chunk text.

SQLite is the default because the target is a local DMG and a few hundred papers is a small workload for a local relational database. PostgreSQL is a later migration target only if the product becomes multi-user, cloud-hosted, or team-collaborative. DuckDB can be added later for analytics exports, but it should not be the primary application database. Qdrant or `sqlite-vec` should be added only when semantic search and similar-paper recommendations become product requirements.

### Library Organization

The app should not use folder hierarchy as the main classification system. A paper can belong to multiple research areas at once, so classification should be metadata-driven:

- `domain`: broad area, such as `LLM Systems`.
- `track`: mid-level direction, such as `Efficient Attention Kernels`.
- `problem`: concrete problem, such as `Long Context Inference`.
- `topics`: cross-cutting subject tags, such as `Transformer`, `KV Cache`, or `RAG`.
- `methods`: method tags, such as `FlashAttention`, `speculative decoding`, or `tiling`.
- `research_line`: narrative thread for related papers.
- `line_role`: role inside the research line, such as `foundation`, `baseline`, `system`, `variant`, or `followup`.
- `status`, `reading_stage`, `review_stage`, `last_reviewed`, and `next_review`: lifecycle and review fields.

At a few hundred papers, the main product risk is not raw database performance. The main risks are tag drift, duplicates, missing metadata, stale review queues, and weak report quality. The UI and backend should therefore support duplicate detection, taxonomy cleanup, batch metadata edits, and review planning.

### File System

The app should preserve existing project conventions:

- `sources/<slug>/arxiv/`: downloaded paper source.
- `sources/<slug>/code/`: optional code repository.
- `docs/<slug>.md`: generated Chinese report.
- `docs/<slug>.html`: generated readable page.
- `docs/papers.json` and `docs/search_index.json`: static wiki indexes.

## LLM Provider Design

Use a small internal interface:

- `analyze_paper(metadata, source_context, report_contract) -> markdown`
- `summarize_code(repo_context, report_context) -> markdown_patch`
- `classify_metadata(report_text) -> metadata_patch`

The first implementation can be OpenAI-compatible. The app should not hard-code one model into business logic.

## Packaging Plan

Recommended sequence:

1. Ship local web app with `uvicorn` backend and Vite frontend.
2. Build frontend assets and serve them from FastAPI.
3. Package Python backend with PyInstaller.
4. Wrap the executable and frontend in Tauri or Electron.
5. Store user data under `~/Library/Application Support/AutoPaperReader/`.
6. Produce signed/notarized DMG after the local app, storage paths, and analysis queue are stable.

## Risks

- arXiv source packages vary in format and sometimes only provide PDFs.
- Long LLM jobs can fail midway; jobs must be resumable or at least retryable.
- LLM output must obey the existing report contract or `build_wiki.py` quality will degrade.
- A few hundred papers can become hard to navigate if metadata is inconsistent; taxonomy governance is a first-class requirement, not a later polish task.
- Full wiki rebuilds may eventually become slower as the library grows; the first desktop release can rebuild fully, but the design should leave room for incremental report rendering and scheduled full governance rebuilds.
- Desktop packaging with Python adds operational complexity, especially around paths and subprocess management.
