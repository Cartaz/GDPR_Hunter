# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M5 — Deterministic Artifact Analysis** is implemented. The current codebase provides the desktop foundation, encrypted identity/artifact storage, Target Registry, GDPR Case workflow, deterministic rights/deadline logic, an evidence-backed Investigation workflow, and local deterministic extraction from supported Artifact types.

M5 adds a bounded `ArtifactAnalyzer` that reads only encrypted Artifact bytes already owned by the application and produces `DETERMINISTIC_ANALYSIS` Evidence without network access or LLM inference. Current extraction covers:

- SMS/text/company-response artifacts: HTTP(S) URLs, URL hosts, and plausible telephone numbers;
- email artifacts: `From`, `Reply-To`, `Return-Path`, sender-related domains, `Message-ID` domain, DKIM `d=` domain, and HTTP(S) URLs/hosts from plain-text body parts;
- URL artifacts: validated HTTP(S) URL and hostname extraction.

Analysis is idempotent against the canonical Evidence already stored for an Artifact: re-running the same deterministic parser adds only missing findings. Invalid or non-HTTP(S) URL artifacts do not become network operations or Evidence merely because they are strings.

The Investigation model continues to enforce:

- encrypted raw Artifact storage with immutable metadata;
- Evidence records with mandatory provenance;
- Claim/Hypothesis records kept distinct from Evidence;
- explicit support/contradiction links between Evidence and Claims;
- model-originated claims start as hypotheses and cannot be promoted by confidence alone;
- `SUPPORTED` requires at least one supporting Evidence item, while `CORROBORATED` and `VERIFIED` require at least two.

Supported GDPR Case workflows remain:

- Article 15 access and provenance, including available source information when data were not collected from the data subject;
- Article 17 erasure, with the application explicitly preserving the need for a case-specific ground and possible statutory exceptions;
- Article 21(2)-(3) objection to processing for direct marketing.

Cases record the date the controller received a request. Deadline calculations use calendar months rather than fixed 30-day intervals, roll weekend deadlines to the following working day, and support an injected public-holiday set. The current production workflow does not yet know the relevant jurisdiction-specific holiday calendar, so the UI explicitly flags that public-holiday review remains required.

LLM inference, web research, redirect resolution, exposure discovery, automated delivery, monitoring, and escalation are planned but are **not implemented yet**.

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
- `ArtifactAnalyzer` is a pure deterministic parser and has no network, filesystem, browser, or inference authority
- the QWebChannel bridge exposes semantic user actions; the frontend cannot assign authoritative/model/deterministic provenance
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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case timelines, immutable Artifact metadata, evidence provenance, deterministic parsing without network authority, and strict separation between future LLM inference and canonical application state.
