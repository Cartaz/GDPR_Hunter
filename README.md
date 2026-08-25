# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M2 — Target Registry + Case Workflow** is implemented. The current codebase provides the desktop foundation from M1 plus:

- a local Target registry for data holders/controllers;
- deterministic database migration from schema v1 to v2;
- Case creation linked to the local Identity and a Target;
- a Python-owned Case state machine (`DRAFT`, `OPEN`, `COMPLETED`, `CANCELLED`);
- append-only Case timeline events persisted atomically with lifecycle transitions;
- local UI controls for Target creation, Case creation/transitions, and timeline inspection.

Investigator, LLM inference, web research, GDPR rights/deadline policy, request delivery, exposure discovery, monitoring, and escalation are planned but are **not implemented yet**.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence
- Python owns canonical state and business logic
- Sensitive personal data is encrypted before persistence

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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, append-only workflow evidence, and strict separation between future LLM inference and canonical application state.
