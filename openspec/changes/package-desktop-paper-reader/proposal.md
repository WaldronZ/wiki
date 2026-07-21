# Change: Package AutoPaperReader as a Local Desktop Paper Knowledge App

## Summary

Build a local app layer around the current AutoPaperReader pipeline. The user enters an arXiv link, the backend downloads and analyzes the paper with an LLM provider, writes the structured report into the knowledge base, refreshes wiki indexes, and exposes all papers through a searchable UI. After the local web version is reliable, package it as a macOS DMG.

## Motivation

The repository already solves the hard knowledge-production part: paper source download, report generation, HTML rendering, and static wiki refresh. The current workflow still requires a coding-agent session and command-line orchestration. A local app would make the workflow repeatable, observable, and usable as a personal research tool.

## Scope

- Add a backend API for paper intake, job status, report access, metadata edits, and knowledge-base refresh.
- Add a local database for durable application state.
- Add a frontend for submitting arXiv links, watching progress, browsing papers, searching the library, and opening reports.
- Add an LLM provider abstraction so the app can call OpenAI-compatible or other APIs.
- Add a background job runner for long-running import/analyze/render operations.
- Add packaging preparation for a macOS DMG.

## Out of Scope

- Cloud sync.
- Team accounts and permissions.
- Mobile apps.
- Automatic paid API billing management beyond storing local provider configuration.
- Rewriting all current wiki pages as dynamic frontend views.

## Success Criteria

- A user can submit `https://arxiv.org/abs/<id>` from the UI and receive a finished Markdown and HTML report.
- The app records job progress and failure reasons in SQLite.
- Duplicate arXiv submissions are detected before re-running analysis.
- Generated reports remain compatible with `scripts/build_wiki.py`.
- The knowledge base can be browsed from the UI without manually opening `docs/index.html`.
- A local library with at least 500 paper records remains searchable and filterable by metadata, tags, research line, status, importance, and code availability.
- Full-text search works across titles, abstracts, generated report content, and user notes without requiring a remote service.
- Semantic search remains optional and can be added with `sqlite-vec`, Chroma, or Qdrant local mode without changing the primary paper database.
- The same app can be bundled into a local macOS application without changing the core pipeline.
