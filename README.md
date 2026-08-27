# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M12 — Read-only Model Analysis** is implemented on the current development branch. The codebase includes encrypted identity/artifact storage, GDPR Case workflows, evidence-backed Investigations, guarded asynchronous public research, bounded OpenAI-compatible inference, strict typed model proposals, durable outbound auditing, reviewed Claim acceptance, and a read-only application service that can turn bounded Investigation Evidence into inert proposals.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added an encrypted append-only audit trail for outbound policy decisions. M11 added an explicit reviewed path that can atomically persist an approved Claim proposal as `MODEL_INFERENCE/HYPOTHESIS` with its cited Evidence.

M12 connects those existing boundaries without granting the model additional authority:

- `ModelAnalysisService` reads Evidence through `InvestigationService`; it does not access SQLite directly;
- one analysis accepts at most 50 persisted Evidence items and at most 32,000 serialized context characters;
- empty, unpersisted or oversized contexts are rejected before inference;
- the exact configured inference destination is submitted through `EgressPolicy` before Evidence leaves the application boundary;
- denied inference is auditable and the inference client is not called;
- only Evidence IDs present in the supplied Investigation snapshot are accepted from model output;
- the response is parsed exclusively through `ModelProposalParser` into immutable typed proposals;
- model output cannot create Claims, perform research or mutate Investigation state through this service;
- invalid model output is rejected rather than partially accepted.

M12 intentionally remains backend-only. It is **not exposed synchronously through QWebChannel**, because inference is network work and must not block the Qt GUI thread. A later UI integration must use an owned worker/runner in the same way research does.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. Model proposal generation and reviewed Claim acceptance remain separate use cases, so producing a proposal never implies accepting it.

Research remains restricted to deterministic URL Evidence, while outbound research and inference both require explicit `EgressPolicy` authorization. The model still has no filesystem, browser, arbitrary networking, command execution or generic canonical-state mutation authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Automatic jurisdiction-specific holiday resolution, asynchronous model UI integration, reviewed research-proposal execution, exposure discovery, automated delivery, monitoring and escalation remain future work.

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
- `EgressPolicy` owns outbound authorization; `OutboundAuditRepository` owns durable audit persistence
- `ResearchRunner` owns Qt threading for public research only
- `InferenceEndpoint` and `InferenceService` own configured model-server transport and bounded JSON inference
- `ModelProposalParser` is the strict boundary from untrusted model JSON to inert typed proposals
- `ModelAnalysisService` owns bounded Evidence-to-proposal orchestration without canonical-state mutation
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference, bounded model context, strict model-output validation, explicit review gates and separation between LLM proposals and canonical application state.
