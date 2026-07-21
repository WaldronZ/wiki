# Capability: Paper Ingestion

## ADDED Requirements

### Requirement: Submit arXiv Link

The system SHALL allow a user to submit an arXiv abstract or PDF URL from the application UI.

#### Scenario: Accepted arXiv abstract URL

- **GIVEN** the user submits `https://arxiv.org/abs/1706.03762`
- **WHEN** the backend receives the request
- **THEN** it extracts `1706.03762`
- **AND** creates an import job.

#### Scenario: Accepted arXiv PDF URL

- **GIVEN** the user submits `https://arxiv.org/pdf/1706.03762`
- **WHEN** the backend receives the request
- **THEN** it normalizes the input to the corresponding abstract/source workflow.

### Requirement: Detect Duplicate Papers

The system SHALL detect existing papers before starting a new analysis.

#### Scenario: Existing report file

- **GIVEN** `docs/1706.03762-attention.md` exists
- **WHEN** the user submits `https://arxiv.org/abs/1706.03762`
- **THEN** the system marks the submission as duplicate
- **AND** shows the existing report path
- **AND** does not start a new analysis unless the user explicitly chooses re-run.

### Requirement: Track Import Job State

The system SHALL persist import job status and current step in SQLite.

#### Scenario: Long-running analysis

- **GIVEN** a paper import is running
- **WHEN** the frontend polls the job endpoint
- **THEN** the response includes status, current step, progress estimate, logs, errors, and output paths when available.

### Requirement: Preserve Source Artifacts

The system SHALL store downloaded paper source and optional code using the current repository layout.

#### Scenario: Source download succeeds

- **GIVEN** an import job has slug `1706.03762-attention`
- **WHEN** the arXiv source package is downloaded and extracted
- **THEN** the files are stored under `sources/1706.03762-attention/arxiv/`.

