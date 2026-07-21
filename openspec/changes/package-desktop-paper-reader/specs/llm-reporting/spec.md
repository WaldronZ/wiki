# Capability: LLM Report Generation

## ADDED Requirements

### Requirement: Generate Structured Chinese Report

The system SHALL generate a Markdown paper report that follows the existing AutoPaperReader report contract.

#### Scenario: Successful analysis

- **GIVEN** paper metadata and source context are available
- **WHEN** the LLM analysis job completes
- **THEN** the system writes `docs/<slug>.md`
- **AND** the report includes YAML frontmatter
- **AND** the report includes the required Chinese sections for paper overview, contribution, story line, references, critique, method details, experiments, and optional code observations.

### Requirement: Validate Report Metadata

The system SHALL validate generated frontmatter before finalizing the report.

#### Scenario: Missing required metadata

- **GIVEN** the generated report lacks `slug` or `title`
- **WHEN** the backend validates the report
- **THEN** the job is marked as needing repair
- **AND** the incomplete report is not promoted as the final knowledge-base entry.

### Requirement: Support Configurable LLM Providers

The system SHALL call LLMs through a provider interface rather than directly embedding one vendor in the paper pipeline.

#### Scenario: OpenAI-compatible provider

- **GIVEN** the user has configured an OpenAI-compatible API key and model
- **WHEN** a paper analysis job starts
- **THEN** the backend uses that provider to generate the report
- **AND** records model and provider metadata on the job.

