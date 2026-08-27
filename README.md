# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M11 — Reviewed Model Claims** is implemented on the current development branch. The codebase includes encrypted identity/artifact storage, GDPR Case workflows, evidence-backed Investigations, guarded asynchronous public research, bounded model inference, strict typed proposals, durable outbound auditing, and a reviewed path for converting a model Claim proposal into canonical state.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added an encrypted append-only audit trail for outbound policy decisions.

M11 allows only reviewed Claim proposals to cross the model/canonical-state boundary:

- the caller must provide an already typed `ClaimProposal` and explicit user approval;
- without approval the operation fails before any mutation;
- the claim is always persisted with provenance `MODEL_INFERENCE` and starts as `HYPOTHESIS`, regardless of model confidence;
- every cited Evidence ID must belong to the target Investigation;
- duplicate Evidence IDs and invalid confidence are rejected before persistence;
- Claim creation and all `SUPPORTS` links are committed in one repository transaction;
- if any cited Evidence is invalid, the entire operation rolls back and no partial Claim remains;
- model research proposals remain inert and cannot use this acceptance path.

`InvestigationService` remains the sole application owner of Investigation/Evidence/Claim mutations. The atomic repository operation hides persistence mechanics rather than leaking SQLite transactions into the application layer.

Inference is still **not exposed through a generic QWebChannel prompt API**. The model has no direct filesystem, browser, networking or arbitrary canonical-state mutation authority. Research remains restricted to deterministic URL Evidence and outbound access remains subject to `EgressPolicy` and durable audit.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Automatic jurisdiction-specific holiday resolution, model orchestration, exposure discovery, automated delivery, monitoring and escalation remain future work.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- `InvestigationService` is the sole application owner of Investigation/Evidence/Claim mutations
- `InvestigationRepository` provides atomic persistence operations for aggregate changes
- `ArtifactAnalyzer` is deterministic and has no network authority
- `ResearchService` owns bounded public-network mechanics behind `NetworkPolicy`
- `EgressPolicy` owns authorization; `OutboundAuditRepository` owns durable audit persistence
- `ResearchRunner` owns Qt threading for research execution only
- `InferenceEndpoint` and `InferenceService` own configured model-server transport and bounded JSON inference
- `ModelProposalParser` is the strict boundary from untrusted model JSON to inert typed proposals
- reviewed Claim acceptance is explicit and separate from proposal generation

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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference, strict model-output validation, explicit review gates and separation between LLM proposals and canonical application state.
