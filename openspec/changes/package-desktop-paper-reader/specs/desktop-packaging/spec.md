# Capability: Desktop Packaging

## ADDED Requirements

### Requirement: Run as Local Application

The system SHALL support running the frontend and backend as a local application.

#### Scenario: App starts locally

- **GIVEN** the user launches the packaged app
- **WHEN** startup completes
- **THEN** the backend API is available locally
- **AND** the frontend opens without requiring a separate terminal command.

### Requirement: Store User Data in macOS App Support

The packaged macOS app SHALL store mutable user data under Application Support by default.

#### Scenario: First launch

- **GIVEN** the app starts for the first time
- **WHEN** it initializes storage
- **THEN** it creates an app data directory under `~/Library/Application Support/AutoPaperReader/`
- **AND** initializes SQLite, reports, sources, and settings paths there unless the user chooses another workspace.

### Requirement: Build DMG

The system SHALL provide a packaging path to produce a macOS DMG.

#### Scenario: Local unsigned DMG

- **GIVEN** the frontend is built and backend executable is packaged
- **WHEN** the packaging command runs
- **THEN** it produces a local DMG suitable for manual installation and testing.

