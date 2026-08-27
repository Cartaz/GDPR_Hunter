# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M14 — Python-owned Proposal Review** is implemented on the current development branch. Model analysis now produces reviewable UI proposals whose authoritative payload remains owned by Python. The web frontend receives only display data plus an opaque token and can accept or discard a proposal only by returning that token.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production.

M14 closes the review loop without trusting JavaScript as a proposal source:

- `ProposalReviewService` is the single owner of generated, ephemeral model proposals;
- each generated proposal receives a cryptographically random opaque token;
- a new analysis invalidates previous tokens for the same Investigation;
- JavaScript receives proposal display fields and the opaque token, but cannot submit statement, confidence or Evidence IDs for acceptance;
- `acceptModelClaim(token, approved_by_user)` resolves the original Python-owned proposal before invoking the M11 atomic acceptance path;
- successful Claim acceptance consumes the token, so replay is rejected;
- denied approval, forged tokens and expired tokens do not mutate canonical state;
- `RESEARCH_EVIDENCE` proposals cannot be accepted as Claims;
- proposals can be explicitly discarded, which also consumes their token;
- the frontend now exposes asynchronous model analysis and review controls while retaining only temporary presentation state.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `ProposalReviewService` owns only ephemeral proposal identity and review resolution. Research and inference both require `EgressPolicy` authorization and enter the durable outbound audit. The model has no filesystem, browser, arbitrary networking, command execution or generic canonical-state authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Automatic jurisdiction-specific holiday resolution, reviewed research-proposal execution, exposure discovery, automated delivery, monitoring and escalation remain future work.

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
- `ProposalReviewService` owns opaque proposal identities and one-use review resolution
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use proposal identities, explicit review gates and separation between LLM proposals and canonical application state.
