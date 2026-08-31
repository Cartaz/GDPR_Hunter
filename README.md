# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M18 — Approved Outbound Payloads** is implemented on the current development branch. GDPR Hunter can now bind explicit user review to an encrypted, immutable copy of the exact Python-generated request payload that a future delivery milestone may use. **M18 still does not send, queue, hand off or otherwise dispatch GDPR requests.**

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production. M14 added Python-owned opaque proposal identities and one-use Claim review. M15 added explicitly reviewed research-proposal execution while keeping outbound destinations under Python policy control. M16 added explicit controller-action jurisdiction and immutable deadline/calendar snapshots. M17 added deterministic local request composition for Articles 15, 17 and 21.

M18 adds the approval boundary that must exist before any future real dispatch:

- identifiers stored in the Identity Vault remain excluded by default; the user explicitly selects which identifiers, if any, are disclosed to help the controller locate relevant records;
- Python validates selected identifier IDs against the canonical local Identity and rejects duplicates, inactive identifiers or IDs that do not belong to the identity;
- `RequestComposer` remains the sole owner of request wording and inserts only the explicitly selected identifiers;
- JavaScript may provide only the Case ID, the typed Article 17 ground where applicable, selected identifier IDs and an explicit approval boolean; it cannot submit or override the recipient, subject or body;
- approval is allowed only while the Case is still `DRAFT` and requires a registered Target privacy email;
- `RequestApprovalService` recomposes from canonical Python state and persists the resulting exact recipient, subject, body, legal basis, Article 17 ground and identifier selection;
- approved recipient email, subject and body are encrypted with the existing authenticated `SensitiveStore` before SQLite persistence;
- approved payloads are append-only. A new approval creates a new historical record; existing approval records cannot be updated or deleted through SQLite;
- schema v7 adds `approved_outbound_requests` without putting mutable approval flags on the Case lifecycle;
- the UI invalidates a displayed preview when canonical state or identifier/Article 17 selection changes;
- approved payloads are displayed as **not sent**. There is no email transport, queue, external-mail-client handoff or generic dispatch bridge surface in M18.

The request templates remain deterministic legal-workflow templates based on GDPR Articles 12, 15, 17, 19 and 21 rather than model-generated legal advice. Case-specific facts remain the user's responsibility and the application does not assert that an Article 17 ground or exception is factually established merely because it is selected.

M16 remains the deadline foundation required before future real request delivery:

- the Case submission boundary requires an explicit two-letter controller-action jurisdiction;
- jurisdiction belongs to the Case submission, not the Target registry, so multinational controllers can be handled without hidden Target-level assumptions;
- `HolidayCalendarProvider` resolves deterministic, versioned holiday snapshots and never guesses a jurisdiction;
- unsupported jurisdictions remain usable only as explicitly unverified calendars: no legal holidays are fabricated and `publicHolidayReviewRequired` stays true;
- the initial Italian provider encodes verified national statutory holidays from 2001 onward, including the restored 2 June holiday and, from 2026 onward, the new 4 October national holiday;
- Italian local patronal holidays are deliberately not inferred, so the Italian calendar remains marked incomplete and requires review of the controller's actual place of action;
- the calendar source/revision, jurisdiction, holiday dates and resulting one-month/three-month deadlines are persisted atomically at submission;
- extension notices cannot precede the recorded request receipt date;
- a definitively late extension notice is rejected only when the stored holiday calendar is complete;
- when an incomplete calendar makes timeliness uncertain, the notice is preserved for review but does not activate the three-month deadline: the initial calculated deadline remains active until the uncertainty is resolved;
- extension handling and displayed deadlines use the stored snapshot rather than recalculating historical Cases against a newer holiday provider.

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `CaseService` owns Case lifecycle, deadline semantics and request-preview orchestration. `RequestComposer` hides deterministic request wording behind a small interface. `RequestApprovalService` owns the transition from a semantic review selection to a durable approved payload. `ApprovedOutboundRequestRepository` owns encrypted append-only approval persistence. `HolidayCalendarProvider` owns jurisdiction-calendar lookup only. The model has no filesystem, browser, arbitrary networking, command execution, generic network primitive, jurisdiction authority, request-composition authority or request-approval authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Verified complete multi-jurisdiction/local holiday calendars, real request delivery, response intake, monitoring and escalation remain future work. No real GDPR request dispatch is implemented yet.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence, append-only outbound audit and approved outbound payload records
- Python owns canonical state and business logic
- Sensitive personal/investigative data, audit destinations and approved outbound message contents are encrypted before persistence
- `CaseService` owns Case lifecycle, deadline semantics and request-preview orchestration
- `RequestComposer` owns deterministic request wording only
- `RequestApprovalService` owns explicit request approval and exact-payload capture
- `ApprovedOutboundRequestRepository` owns encrypted append-only approved-payload persistence
- `HolidayCalendarProvider` owns explicit jurisdiction-to-calendar resolution with source/version metadata
- `DeadlineEngine` owns calendar-month arithmetic, working-day roll-forward and extension-timeliness assessment
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use model proposal identities, explicit review gates and separation between LLM proposals and canonical application state. Request composition and approval are deterministic and Python-owned; the frontend cannot override generated request content. M18 adds encrypted append-only approved payload records but intentionally introduces no delivery mechanism. Historical deadline snapshots retain the legal/calendar inputs used when the Case was submitted.
