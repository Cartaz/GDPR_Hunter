# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M9 — Typed Model Proposals** is implemented on the current development branch. The codebase provides the desktop foundation, encrypted identity/artifact storage, Target Registry, GDPR Case workflow, deterministic rights/deadline logic, evidence-backed Investigations, deterministic Artifact analysis, guarded public-network research, non-blocking UI execution of that research, bounded OpenAI-compatible inference transport, and a strict inert proposal schema for future model output.

M6 established guarded public-network research behind `NetworkPolicy` and explicit `EgressPolicy` approval. M7 moved that research onto an owned Qt worker without moving network rules into QWebChannel. M8 introduced a configured, bounded OpenAI-compatible inference transport without tools or canonical-state authority.

M9 adds a deterministic boundary between untrusted model JSON and application behavior:

- model output is accepted only as a top-level `proposals` list with a maximum of 20 entries;
- supported proposal kinds are `CLAIM` and `RESEARCH_EVIDENCE` only;
- Claim proposals require a bounded statement, one or more existing Evidence IDs, unique citations and confidence in the range 0–1;
- Research proposals can reference only an existing Evidence ID plus a bounded rationale;
- arbitrary URLs, commands, destinations, tool names and unknown fields are rejected rather than ignored;
- every referenced Evidence ID must exist in the caller-provided investigation context;
- parsed proposals are immutable dataclasses and are intentionally inert: parsing does not create Claims, mutate Investigation state or perform network access.

Inference remains **not exposed through a generic QWebChannel prompt API**. The model has no direct filesystem, browser, networking or canonical-state mutation authority. A later application service may feed bounded Investigation context into inference and return these proposals for review, but proposal acceptance/execution must remain separate and deterministic.

Research requests remain restricted to HTTP(S) URLs first extracted as deterministic Evidence from an Artifact. The UI cannot supply arbitrary destinations or privileged evidence provenance.

Durable auditing of `EgressPolicy` decisions remains pending. It must be introduced before model-proposed outbound actions become executable, so user actions and model proposals share the same durable authorization trail.

The M5 `ArtifactAnalyzer` continues to cover SMS/text/company-response URLs, hosts and plausible telephone numbers; email sender-related headers/domains, Message-ID domain, DKIM `d=` domain and plain-text-body URLs; and URL artifacts. Parsing itself has no network authority.

The Investigation model continues to enforce encrypted Artifact storage, mandatory Evidence provenance, separation of Evidence from Claim/Hypothesis, evidence-backed Claim promotion and Python-only canonical mutations.

Supported GDPR Case workflows remain Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Deadline calculations use calendar months and support injected public holidays; automatic jurisdiction-specific holiday resolution is still planned.

Autonomous research planning, browser automation, exposure discovery, automated request delivery, monitoring and escalation are **not implemented yet**.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence
- Python owns canonical state and business logic
- Sensitive personal/investigative data is encrypted before persistence
- Raw and fetched Artifact bytes are stored encrypted outside SQLite behind `ArtifactStore`
- `InvestigationService` is the sole application owner of Investigation/Evidence/Claim mutations
- `ArtifactAnalyzer` is deterministic and has no network authority
- `ResearchService` owns bounded public-network mechanics behind `NetworkPolicy`
- outbound research requires explicit `EgressPolicy` authorization
- `ResearchRunner` owns Qt threading for research execution only; it contains no domain or network policy
- `InferenceEndpoint` and `InferenceService` own configured model-server transport validation and bounded JSON inference
- `ModelProposalParser` is the strict boundary from untrusted model JSON to inert typed proposals
- inference and proposals currently have no generic QWebChannel API and no authority over application state
- the QWebChannel bridge exposes no network primitive and performs no blocking research
- GDPR rights and deadline rules remain deterministic Python modules

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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case timelines, immutable Artifact metadata, evidence provenance, deterministic parsing without network authority, SSRF-resistant bounded research, owned asynchronous execution, bounded configured inference, strict model-output validation and separation between LLM proposals and canonical application state.
