# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M10 — Durable Outbound Audit** is implemented on the current development branch. The codebase now includes encrypted identity/artifact storage, Target Registry, GDPR Case workflows, evidence-backed Investigations, deterministic Artifact analysis, guarded asynchronous public research, bounded OpenAI-compatible inference, strict inert model proposals, and a persistent authorization trail for outbound actions.

M6 established guarded public-network research behind `NetworkPolicy` and explicit `EgressPolicy` approval. M7 moved that research onto an owned Qt worker. M8 added a bounded configured inference transport without tools or canonical-state authority. M9 introduced a strict parser that turns untrusted model JSON into immutable `CLAIM` or `RESEARCH_EVIDENCE` proposals referencing existing Evidence only.

M10 makes outbound authorization auditable:

- SQLite schema version 5 adds `outbound_audit` through the normal `Database` migration path;
- every production `EgressPolicy` decision is written by `OutboundAuditRepository`;
- both `ALLOW` and `REQUIRE_APPROVAL` decisions are recorded;
- intents identify their actor as `USER` or `MODEL`;
- destination values are encrypted with the application `SensitiveStore` before persistence;
- operation, data class, actor, approval state, decision and timestamp remain queryable audit metadata;
- database triggers reject UPDATE and DELETE, making the audit table append-only through normal application access;
- fresh databases create the v5 schema directly and existing v1–v4 databases migrate sequentially to v5;
- test-only policies may omit an audit sink, while the production composition in `main.py` always wires the persistent repository.

Model proposals remain inert. No model proposal can currently mutate Investigation state or execute network access. Before any future model-proposed outbound action is executed, it must be converted into an `OutboundIntent`, pass the same `EgressPolicy` used for user actions, and therefore enter the same durable audit trail.

Inference remains **not exposed through a generic QWebChannel prompt API**. The model has no direct filesystem, browser, networking or canonical-state mutation authority.

Research requests remain restricted to HTTP(S) URLs first extracted as deterministic Evidence from an Artifact. The UI cannot supply arbitrary destinations or privileged evidence provenance.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Deadline calculations use calendar months and support injected public holidays; automatic jurisdiction-specific holiday resolution is still planned.

Autonomous research planning, browser automation, exposure discovery, automated request delivery, monitoring and escalation are **not implemented yet**.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- Raw and fetched Artifact bytes are stored encrypted outside SQLite behind `ArtifactStore`
- `InvestigationService` is the sole application owner of Investigation/Evidence/Claim mutations
- `ArtifactAnalyzer` is deterministic and has no network authority
- `ResearchService` owns bounded public-network mechanics behind `NetworkPolicy`
- `EgressPolicy` owns authorization; `OutboundAuditRepository` owns durable audit persistence
- `ResearchRunner` owns Qt threading for research execution only
- `InferenceEndpoint` and `InferenceService` own configured model-server transport validation and bounded JSON inference
- `ModelProposalParser` is the strict boundary from untrusted model JSON to inert typed proposals
- inference and proposals have no generic QWebChannel API and no authority over application state

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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case and outbound-audit records, immutable Artifact metadata, evidence provenance, deterministic parsing without network authority, SSRF-resistant bounded research, owned asynchronous execution, bounded configured inference, strict model-output validation and separation between LLM proposals and canonical application state.
