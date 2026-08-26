# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M6 — Research Foundation** is implemented. The current codebase provides the desktop foundation, encrypted identity/artifact storage, Target Registry, GDPR Case workflow, deterministic rights/deadline logic, evidence-backed Investigations, deterministic Artifact analysis, and a guarded public-network research foundation.

M6 adds:

- `NetworkPolicy` validation for outbound public HTTP(S) research;
- rejection of localhost, private, link-local, reserved and otherwise non-public resolved IP addresses;
- rejection of embedded URL credentials, non-HTTP(S) schemes and ports other than the scheme default (HTTP 80 / HTTPS 443);
- DNS resolution before connection and transport pinning to the validated IP while retaining the original hostname/SNI for HTTPS;
- manual redirect handling with full policy revalidation on every hop and a bounded redirect count;
- bounded response size, short timeout, restricted textual/JSON content types, and no browser execution;
- `ResearchService` helpers for public document fetch, public DNS resolution and IANA-bootstrap-based domain RDAP lookup;
- explicit `EgressPolicy` authorization before research-capable operations;
- encrypted storage of fetched public documents as reference Artifacts and `REMOTE_DOCUMENT` Evidence;
- preservation of redirect observations and final URL as Evidence;
- deterministic analysis of fetched reference documents after they are stored locally.

Research requests are restricted to HTTP(S) URLs first extracted as deterministic Evidence from an Artifact, and the application service requires explicit approval before network access. The network workflow is intentionally **not exposed through QWebChannel/UI yet**: executing it synchronously would block the Qt GUI thread. The next integration step must run research in an owned worker with completion/error signalling and cancellation where feasible. There is no disconnected `Research` control in the UI.

Durable auditing of `EgressPolicy` decisions is also intentionally deferred until the inference milestone, when both user actions and model-proposed research will share one outbound-intent model. Authorization is already enforced; the deferred work is persistence of the audit trail, not the security gate itself.

The M5 `ArtifactAnalyzer` continues to cover SMS/text/company-response URLs, hosts and plausible telephone numbers; email sender-related headers/domains, Message-ID domain, DKIM `d=` domain and plain-text-body URLs; and URL artifacts. Parsing itself has no network authority.

The Investigation model continues to enforce encrypted Artifact storage, mandatory Evidence provenance, separation of Evidence from Claim/Hypothesis, evidence-backed Claim promotion and Python-only canonical mutations.

Supported GDPR Case workflows remain Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Deadline calculations use calendar months and support injected public holidays; automatic jurisdiction-specific holiday resolution is still planned.

LLM inference, asynchronous UI research execution, autonomous research planning, browser automation, exposure discovery, automated request delivery, monitoring and escalation are **not implemented yet**.

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
- `ResearchService` owns bounded network mechanics behind `NetworkPolicy`
- outbound research requires explicit `EgressPolicy` authorization
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

The application is designed around local-first processing, explicit outbound-data control, local-only WebEngine content, redacted diagnostics, encrypted sensitive persistence, append-only Case timelines, immutable Artifact metadata, evidence provenance, deterministic parsing without network authority, SSRF-resistant bounded research, and strict separation between future LLM inference and canonical application state.
