# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M1 — Foundation** is in progress. The current codebase provides the desktop application skeleton, settings, persistence/security foundations, identity storage, encrypted artifact storage, QWebChannel bridge, and local HTML UI shell.

Investigator, LLM inference, web research, GDPR request workflows, exposure discovery, monitoring, and escalation are planned but are **not implemented yet**.

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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, and strict separation between future LLM inference and canonical application state.
