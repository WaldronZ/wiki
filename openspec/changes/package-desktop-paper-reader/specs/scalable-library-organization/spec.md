# Capability: Scalable Library Organization

## ADDED Requirements

### Requirement: Support Hundreds of Papers Locally

The system SHALL support a personal library containing at least 500 papers without requiring a server database.

#### Scenario: Browse 500-paper library

- **GIVEN** the local SQLite database contains at least 500 paper records
- **WHEN** the user opens the paper library view
- **THEN** the app returns the initial list using indexed queries
- **AND** supports filtering by year, status, reading stage, importance, code status, research line, and tags.

### Requirement: Use SQLite as the Primary Local Database

The system SHALL use SQLite as the primary local database for the desktop application.

#### Scenario: First launch initializes storage

- **GIVEN** the app starts with no existing database
- **WHEN** storage initialization runs
- **THEN** it creates a SQLite database
- **AND** creates tables for papers, jobs, tags, paper_tags, notes, settings, model_runs, and paper_chunks.

### Requirement: Preserve Files Outside the Database

The system SHALL store large and portable artifacts as files rather than database blobs.

#### Scenario: Paper assets are saved

- **GIVEN** a paper import completes
- **WHEN** the system persists the result
- **THEN** Markdown, HTML, arXiv source, PDF, images, and code repositories remain in the file system
- **AND** SQLite stores paths, metadata, indexes, and job state.

### Requirement: Classify Papers by Metadata, Not Folders

The system SHALL organize papers with metadata fields instead of relying on exclusive folder placement.

#### Scenario: Paper belongs to multiple areas

- **GIVEN** a paper is relevant to both `LLM Serving` and `KV Cache`
- **WHEN** the paper is saved
- **THEN** it can be assigned multiple topics and methods
- **AND** it can still have one primary research line for narrative organization.

### Requirement: Maintain Research Lines

The system SHALL support research-line organization for long-term paper review.

#### Scenario: View a research line

- **GIVEN** papers have `research_line` and `line_role` metadata
- **WHEN** the user opens a research-line view
- **THEN** the app groups papers by research line
- **AND** distinguishes roles such as `foundation`, `baseline`, `system`, `variant`, and `followup`.

### Requirement: Detect Duplicates at Scale

The system SHALL detect duplicate and near-duplicate papers during import and library maintenance.

#### Scenario: Duplicate arXiv id

- **GIVEN** a paper with arXiv id `2307.08691` already exists
- **WHEN** the user imports another URL for `2307.08691`
- **THEN** the system blocks the default import
- **AND** shows the existing paper and report paths.

#### Scenario: Similar title

- **GIVEN** a new paper has no arXiv id or has a different version marker
- **WHEN** its normalized title is highly similar to an existing paper
- **THEN** the system flags a possible duplicate for user confirmation.

### Requirement: Provide Full-Text Search

The system SHALL provide local full-text search across paper metadata, generated reports, chunks, and user notes.

#### Scenario: Search method detail

- **GIVEN** report chunks have been indexed in SQLite FTS5
- **WHEN** the user searches for `speculative decoding verification`
- **THEN** the app returns matching papers with relevant sections or snippets.

### Requirement: Keep Semantic Search Optional

The system SHALL treat semantic vector search as an optional expansion, not a dependency for the core local library.

#### Scenario: Semantic search disabled

- **GIVEN** no embedding provider is configured
- **WHEN** the user browses or searches the library
- **THEN** structured filters and full-text search still work.

#### Scenario: Semantic search enabled

- **GIVEN** an embedding provider and vector store are configured
- **WHEN** the user asks for papers similar to a query or selected paper
- **THEN** the system searches stored chunk embeddings
- **AND** returns similar papers with source chunks and metadata filters.

### Requirement: Support Review Queues

The system SHALL help users maintain a large library through review scheduling.

#### Scenario: Generate review queue

- **GIVEN** papers have importance, reading_stage, review_stage, last_reviewed, and next_review metadata
- **WHEN** the user opens the review queue
- **THEN** the app prioritizes overdue, important, or weakly understood papers.

### Requirement: Support Taxonomy Governance

The system SHALL provide maintenance signals for tag drift and weak metadata.

#### Scenario: Taxonomy cleanup needed

- **GIVEN** the library contains sparse tags, duplicate tag spellings, overloaded tags, or missing required fields
- **WHEN** the user opens the taxonomy cleanup view
- **THEN** the app shows suggested cleanup actions
- **AND** allows batch metadata edits before rebuilding the wiki.
