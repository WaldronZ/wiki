# Tasks

## Phase 1: Product Skeleton

- [x] Create `backend/` FastAPI app with health check and configuration loading.
- [x] Create `frontend/` React + Vite app with app shell, paper import form, job list, and paper list.
- [x] Add SQLite database setup and migration strategy.
- [x] Create initial SQLite schema for papers, jobs, tags, paper_tags, notes, settings, model_runs, and paper_chunks.
- [x] Add required uniqueness and lookup indexes for slug, arXiv id, status, reading stage, importance, research line, job status, and tag relations.
- [x] Add development commands for starting backend and frontend.

## Phase 2: Import Pipeline

- [x] Implement arXiv URL normalization and metadata fetch.
- [x] Implement duplicate detection using SQLite and existing report files.
- [x] Implement source download and extraction using current project conventions.
- [x] Implement main `.tex` discovery and source-context collection.
- [x] Implement optional code-link detection and shallow clone.

## Phase 3: LLM Analysis

- [x] Add LLM provider abstraction and local settings.
- [x] Implement paper report generation using the existing report structure contract.
- [x] Implement internal paper/code/html agent harness stages aligned with the old `.Codex/agents` contracts.
- [x] Implement code-observation supplement when a code repository exists.
- [x] Validate generated Markdown frontmatter before writing final report.
- [x] Store all model, prompt, token, and error metadata needed for reproducibility.

## Phase 4: Knowledge Base Output

- [x] Reuse `scripts/render_report_html.py` to generate single-paper HTML.
- [x] Reuse `scripts/build_wiki.py` to refresh the report directory.
- [x] Persist final paper metadata into SQLite.
- [x] Split generated reports into searchable chunks and store them in `paper_chunks`.
- [x] Build SQLite FTS5 search over title, abstract, report text, notes, and chunks.
- [x] Expose generated Markdown, HTML, and wiki paths through the API.

## Phase 5: UI Experience

- [x] Build import screen with arXiv link input and provider/model selection.
- [x] Build job progress screen with current step, logs, retry, and failure display.
- [x] Build paper library screen with search, status, importance, and code filters.
- [x] Add tag/topic/method filters to the paper library screen.
- [x] Build paper detail screen with metadata, notes, and links to Markdown/HTML reports.
- [x] Build research-line view that groups papers by line and role.
- [x] Build taxonomy cleanup view for duplicate tags, sparse tags, overloaded tags, and missing metadata.
- [x] Build review queue view using `last_reviewed`, `next_review`, `review_stage`, and `importance`.
- [x] Add settings screen for report directory, source directory, API keys, and model defaults.

## Phase 6: Scale, Quality, and Recovery

- [x] Add unit tests for URL parsing, duplicate detection, metadata validation, and job transitions.
- [x] Add unit tests for tag normalization, research-line assignment, FTS indexing, and review queue generation.
- [x] Add integration test for import pipeline using a small fixture or mocked arXiv response.
- [x] Add scale fixture or generated dataset with at least 500 paper records to verify library query performance.
- [x] Add retry behavior for failed download, render, and wiki-refresh steps.
- [x] Add clear error reporting for missing TeX source, failed LLM call, malformed report, and packaging path issues.
- [x] Add quality checks for duplicate arXiv ids, duplicate titles, missing report files, stale wiki indexes, and malformed metadata.

## Phase 7: Semantic Search Optional Expansion

- [x] Evaluate `sqlite-vec`, `sqlite-vss`, Chroma, and Qdrant local mode for local semantic search.
- [x] Add embedding settings for provider, model, dimension, and chunking strategy.
- [x] Add semantic search API for similar papers and natural-language paper lookup.
- [x] Keep semantic vector storage optional so the core local library remains usable without embeddings.

## Phase 8: Desktop Packaging

- [x] Serve built frontend from FastAPI for single-process local deployment.
- [x] Package backend with PyInstaller.
- [x] Choose Tauri or Electron based on packaging complexity and binary size.
- [x] Configure app data paths under macOS Application Support.
- [x] Build unsigned local DMG.
- [x] Add signing and notarization plan for distribution.
