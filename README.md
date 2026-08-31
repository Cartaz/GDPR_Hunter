# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M15 — Reviewed Research Proposals** is implemented on the current development branch. Model-generated research suggestions can now be executed only after explicit user review, through a Python-owned opaque proposal token. The model and JavaScript still cannot choose an outbound destination at execution time: Python resolves the referenced Evidence from canonical state and derives the HTTP(S) URL from its persisted value.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production. M14 added Python-owned opaque proposal identities and one-use Claim review.

M15 extends that review boundary to research without giving the model network authority:

- `ProposalReviewService` remains the owner of generated, ephemeral proposals and resolves a reviewed `RESEARCH_EVIDENCE` token only to its Python-owned Investigation and Evidence IDs;
- JavaScript calls `executeModelResearchProposal(token, approved_by_user)` and cannot submit a URL, destination, rationale or Evidence ID to the privileged action;
- explicit user approval is required before a research proposal can be resolved;
- the accepted research token is consumed for one approved attempt, so replay is rejected even if the eventual network operation fails;
- `InvestigationService` verifies that the referenced Evidence belongs to the Investigation and derives the destination exclusively from the persisted Evidence value;
- only HTTP(S) Evidence values are researchable through this path;
- ordinary user-initiated Artifact research and reviewed model research share the same bounded fetch, redirect validation, deduplication, encrypted snapshot persistence and cancellation path;
- reviewed model research is audited through `EgressPolicy` with `actor=MODEL`, while direct user research remains `actor=USER`;
- `ResearchRunner` remains the single Qt owner of asynchronous research work, so neither bridge nor JavaScript owns threads or network mechanics;
- fetched documents remain REFERENCE Artifacts and their derived Evidence remains subject to the same deterministic analysis and provenance rules as existing public research.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `ProposalReviewService` owns only ephemeral proposal identity and reviewed resolution. Research and inference both require `EgressPolicy` authorization and enter the durable outbound audit. The model has no filesystem, browser, arbitrary networking, command execution, generic network primitive or generic canonical-state authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Automatic jurisdiction-specific holiday resolution, exposure discovery, automated delivery, monitoring and escalation remain future work.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- `InvestigationService` owns Investigation/Evidence/Claim mutations and semantic research orchestration
- `InvestigationRepository` provides atomic persistence operations for aggregate changes
- `ArtifactAnalyzer` is deterministic and has no network authority
- `ResearchService` owns bounded public-network mechanics behind `NetworkPolicy`
- `EgressPolicy` owns outbound authorization; `OutboundAuditRepository` owns durable audit persistence
- `ResearchRunner` owns Qt threading for both direct and reviewed model research
- `InferenceEndpoint` and `InferenceService` own configured model-server transport and bounded JSON inference
- `ModelProposalParser` validates untrusted model JSON into inert typed proposals
- `ModelAnalysisService` owns bounded Evidence-to-proposal orchestration without mutation
- `ModelAnalysisRunner` owns Qt threading for that orchestration
- `ProposalReviewService` owns opaque proposal identities and one-use reviewed resolution
- reviewed Claim acceptance and reviewed research execution remain explicit and separate from proposal generation

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
.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt
```

## Security posture

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use proposal identities, explicit review gates and separation between LLM proposals and canonical application state. Reviewed research proposals do not carry executable destinations: outbound targets are reconstructed from persisted Evidence under Python policy control.
