# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M16 — Jurisdiction-aware Deadline Snapshots** is implemented on the current development branch. A GDPR Case now records the controller-action jurisdiction explicitly when submission is recorded and persists the exact deadline/calendar snapshot used for that Case. Jurisdiction is never inferred from the user's location, IP address, Target domain or model output.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production. M14 added Python-owned opaque proposal identities and one-use Claim review. M15 added explicitly reviewed research-proposal execution while keeping outbound destinations under Python policy control.

M16 establishes the deadline foundation required before any future real request dispatch:

- the Case submission boundary requires an explicit two-letter controller-action jurisdiction;
- jurisdiction belongs to the Case submission, not the Target registry, so multinational controllers can be handled without hidden Target-level assumptions;
- `HolidayCalendarProvider` resolves deterministic, versioned holiday snapshots and never guesses a jurisdiction;
- unsupported jurisdictions remain usable only as explicitly unverified calendars: no legal holidays are fabricated and `publicHolidayReviewRequired` stays true;
- the initial Italian provider encodes verified national statutory holidays from 2001 onward, including the restored 2 June holiday and, from 2026 onward, the new 4 October national holiday;
- Italian local patronal holidays are deliberately not inferred, so the Italian calendar remains marked incomplete and requires review of the controller's actual place of action;
- the calendar source/revision, jurisdiction, holiday dates and resulting one-month/three-month deadlines are persisted atomically at submission;
- the repository creates Draft Cases with the entire deadline snapshot unset and establishes all snapshot fields atomically on submission; SQLite rejects partial snapshot updates and prevents an established snapshot from being modified later;
- extension notices cannot precede the recorded request receipt date;
- a definitively late extension notice is rejected only when the stored holiday calendar is complete; incomplete calendars preserve the notice and keep manual legal-calendar review explicit instead of producing a false definitive rejection;
- extension handling and displayed deadlines use the stored snapshot rather than recalculating historical Cases against a newer holiday provider;
- pre-M16 submitted Cases remain readable without invented historical metadata and are clearly treated as requiring holiday/jurisdiction review.

The deadline model follows GDPR Article 12(3) calendar-month timing together with Council Regulation (EEC, Euratom) No 1182/71: where the relevant last day is a Saturday, Sunday or public holiday, the period ends on the next working day. For public holidays, the relevant Member State is the one in which the action is to be performed. Calendar datasets are therefore treated as legal inputs with explicit provenance rather than generic locale data.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `CaseService` owns Case lifecycle and deadline semantics. `HolidayCalendarProvider` owns jurisdiction-calendar lookup only; it does not infer jurisdiction or mutate Cases. `CaseRepository` persists the immutable deadline snapshot atomically with submission. The model has no filesystem, browser, arbitrary networking, command execution, generic network primitive, jurisdiction authority or generic canonical-state authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Verified complete multi-jurisdiction/local holiday calendars, exposure discovery, automated delivery, monitoring and escalation remain future work. No real GDPR request dispatch is implemented yet.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- `CaseService` owns Case lifecycle and deadline semantics
- `HolidayCalendarProvider` owns explicit jurisdiction-to-calendar resolution with source/version metadata
- `DeadlineEngine` owns calendar-month arithmetic and working-day roll-forward
- `CaseRepository` atomically persists Case lifecycle changes and immutable deadline snapshots
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use proposal identities, explicit review gates and separation between LLM proposals and canonical application state. Reviewed research proposals do not carry executable destinations, and deadline jurisdiction is an explicit Case input rather than an inferred property. Historical deadline snapshots retain the legal/calendar inputs used when the Case was submitted.
