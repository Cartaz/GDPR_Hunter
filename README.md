# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M3 — Rights Policy + Deadline Engine** is implemented. The current codebase provides the desktop foundation, encrypted identity/artifact storage, Target Registry, GDPR Case workflow, deterministic rights policy for the initial supported use cases, and calendar-based Article 12 deadline tracking.

Supported M3 GDPR workflows are:

- Article 15 access and provenance, including available source information when data were not collected from the data subject;
- Article 17 erasure, with the application explicitly preserving the need for a case-specific ground and possible statutory exceptions;
- Article 21(2)-(3) objection to processing for direct marketing.

Cases record the date the controller received a request. Deadline calculations use calendar months rather than fixed 30-day intervals, roll weekend deadlines to the following working day, and support an injected public-holiday set. The current production workflow does not yet know the relevant jurisdiction-specific holiday calendar, so the UI explicitly flags that public-holiday review remains required.

Investigator, LLM inference, web research, exposure discovery, automated delivery, monitoring, and escalation are planned but are **not implemented yet**.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence
- Python owns canonical state and business logic
- Sensitive personal data is encrypted before persistence
- GDPR rights and deadline rules are deterministic Python modules; no LLM participates in legal workflow decisions

## Install

```bash
chmod +x install.sh
./install.sh
```

## Run

```bash
.venv/bin/python main.py
```

## Development validation

```bash
.venv/bin/python -m compileall -q main.py config core ui tests
.venv/bin/python -m pytest
.venv/bin/ruff check main.py config core ui tests
```

## Security posture

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case timelines, and strict separation between future LLM inference and canonical application state.
