# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M4 — Investigator Core + Evidence Model** is implemented. The current codebase provides the desktop foundation, encrypted identity/artifact storage, Target Registry, GDPR Case workflow, deterministic rights/deadline logic, and a first evidence-backed Investigation workflow.

M4 adds:

- Investigation lifecycle with explicit state transitions;
- encrypted raw Artifact storage with immutable metadata;
- Evidence records with mandatory provenance;
- Claim/Hypothesis records kept distinct from Evidence;
- explicit support/contradiction links between Evidence and Claims;
- a rule that model-originated claims start as hypotheses and cannot become verified from confidence alone;
- a rule that a verified Claim requires supporting Evidence;
- a local Investigation workbench for creating investigations, importing text artifacts, recording evidence, and adding hypotheses.

Supported GDPR Case workflows remain:

- Article 15 access and provenance, including available source information when data were not collected from the data subject;
- Article 17 erasure, with the application explicitly preserving the need for a case-specific ground and possible statutory exceptions;
- Article 21(2)-(3) objection to processing for direct marketing.

Cases record the date the controller received a request. Deadline calculations use calendar months rather than fixed 30-day intervals, roll weekend deadlines to the following working day, and support an injected public-holiday set. The current production workflow does not yet know the relevant jurisdiction-specific holiday calendar, so the UI explicitly flags that public-holiday review remains required.

LLM inference, web research, automatic artifact analysis, exposure discovery, automated delivery, monitoring, and escalation are planned but are **not implemented yet**.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence
- Python owns canonical state and business logic
- Sensitive personal/investigative data is encrypted before persistence
- Raw Artifact bytes are stored encrypted outside SQLite behind `ArtifactStore`
- `InvestigationService` is the sole application owner of Investigation/Evidence/Claim mutations
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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case timelines, immutable Artifact metadata, evidence provenance, and strict separation between future LLM inference and canonical application state.
