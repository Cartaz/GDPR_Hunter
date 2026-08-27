# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M13 — Async Model Analysis Integration** is implemented on the current development branch. The application now composes the configured inference endpoint/model at startup and can execute M12 Evidence-to-proposal analysis on an owned Qt worker rather than the GUI thread.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation.

M13 adds the native asynchronous integration while preserving those boundaries:

- settings provide the inference endpoint, location classification and model to Python startup composition;
- `InferenceEndpoint`, `InferenceService`, `ModelAnalysisService` and the durable `EgressPolicy` are wired in Python, not JavaScript;
- `ModelAnalysisRunner` owns a dedicated `QThread` and prevents concurrent model-analysis jobs;
- the runner has bounded, idempotent shutdown and is cleaned up during application shutdown;
- QWebChannel exposes only the semantic operation `analyzeInvestigationWithModel(investigation_id, approved_by_user)`;
- JavaScript cannot provide a prompt, model, endpoint, URL, command or tool name;
- explicit approval is required before a model-analysis worker is started;
- typed proposals are serialized to simple read-only DTOs and delivered through Qt signals;
- proposal generation still performs no canonical-state mutation and no research execution;
- existing bridge users remain compatible when model analysis is not configured.

M13 intentionally does **not** add proposal-acceptance controls to the web frontend. A later review workflow must not accept a fabricated JavaScript proposal payload; it should refer to Python-owned generated proposals by an opaque identity before allowing M11 Claim acceptance.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. Research and inference both require `EgressPolicy` authorization and enter the durable outbound audit. The model has no filesystem, browser, arbitrary networking, command execution or generic canonical-state authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Automatic jurisdiction-specific holiday resolution, proposal-review UI, reviewed research-proposal execution, exposure discovery, automated delivery, monitoring and escalation remain future work.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- `InvestigationService` owns Investigation/Evidence/Claim mutations
- `InvestigationRepository` provides atomic persistence operations for aggregate changes
- `ArtifactAnalyzer` is deterministic and has no network authority
- `ResearchService` owns bounded public-network mechanics behind `NetworkPolicy`
- `EgressPolicy` owns outbound authorization; `OutboundAuditRepository` owns durable audit persistence
- `ResearchRunner` owns Qt threading for public research
- `InferenceEndpoint` and `InferenceService` own configured model-server transport and bounded JSON inference
- `ModelProposalParser` validates untrusted model JSON into inert typed proposals
- `ModelAnalysisService` owns bounded Evidence-to-proposal orchestration without mutation
- `ModelAnalysisRunner` owns Qt threading for that orchestration
- reviewed Claim acceptance remains explicit and separate from proposal generation

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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, explicit review gates and separation between LLM proposals and canonical application state.
