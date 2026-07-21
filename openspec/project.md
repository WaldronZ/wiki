# Project: AutoPaperReader Desktop Knowledge Base

AutoPaperReader is evolving from an agent-driven repository workflow into a local desktop application for paper intake, LLM-assisted analysis, and personal knowledge-base management.

## Goals

- Let users submit an arXiv link from a graphical interface.
- Run the existing paper-reading pipeline as a recoverable backend job.
- Store paper metadata, job state, user notes, and knowledge-base indexes in a local database.
- Preserve the current Markdown/HTML/wiki artifacts as portable files.
- Package the application as a macOS DMG after the local web version is stable.

## Non-Goals

- Multi-user SaaS hosting in the first product phase.
- Replacing the existing `docs/` static wiki output.
- Requiring cloud storage for the personal library.
- Building a full reference manager clone before the import/analyze/browse loop works.

## Architecture Preferences

- Backend: Python FastAPI, because the current scripts are Python and can be reused directly.
- Frontend: React + Vite for a local web UI.
- Database: SQLite as the primary local store, with optional vector-search expansion later.
- Desktop shell: Tauri or Electron after the web app and backend are stable.
- File layout: keep `docs/`, `sources/`, and generated HTML/JSON artifacts as first-class outputs.
