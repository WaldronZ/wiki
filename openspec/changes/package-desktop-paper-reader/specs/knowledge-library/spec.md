# Capability: Knowledge Library

## ADDED Requirements

### Requirement: Preserve Markdown and HTML Outputs

The system SHALL keep Markdown and HTML reports as portable files in the report directory.

#### Scenario: Report generation completes

- **GIVEN** a paper has slug `1706.03762-attention`
- **WHEN** analysis and rendering complete
- **THEN** `docs/1706.03762-attention.md` and `docs/1706.03762-attention.html` exist
- **AND** the database stores their paths.

### Requirement: Refresh Static Wiki

The system SHALL refresh the static wiki after a report is created or updated.

#### Scenario: New paper added

- **GIVEN** `docs/<slug>.md` has been written
- **WHEN** the pipeline reaches the wiki-refresh step
- **THEN** it runs `python3 scripts/build_wiki.py docs`
- **AND** updates `papers.json`, `search_index.json`, `index.html`, and related wiki pages.

### Requirement: Browse Papers in UI

The system SHALL provide an application view for browsing papers stored in SQLite and generated wiki indexes.

#### Scenario: Filter by topic and status

- **GIVEN** the library contains multiple papers
- **WHEN** the user filters by topic and reading status
- **THEN** the UI shows matching papers with title, year, authors, importance, tags, code status, and report links.

### Requirement: Store User Notes

The system SHALL allow users to store local notes linked to a paper.

#### Scenario: Add note to paper

- **GIVEN** the user is viewing a paper detail page
- **WHEN** the user saves a note
- **THEN** the note is persisted in SQLite
- **AND** remains separate from the generated report unless the user explicitly exports it.

