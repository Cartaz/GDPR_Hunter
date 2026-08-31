# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M17 — Deterministic Request Composition** is implemented on the current development branch. Supported GDPR Cases can now produce a local, read-only request preview from canonical Python state. No message is sent, queued or handed to an external mail client in this milestone.

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production. M14 added Python-owned opaque proposal identities and one-use Claim review. M15 added explicitly reviewed research-proposal execution while keeping outbound destinations under Python policy control. M16 added explicit controller-action jurisdiction and immutable deadline/calendar snapshots.

M17 adds the final composition boundary before future real dispatch:

- `RequestComposer` deterministically produces recipient metadata, subject, legal basis and plain-text body; it has no network, model, filesystem or persistence authority;
- Article 15 previews request confirmation, a copy of the personal data and the information required by the supported access/provenance workflow, including source information where the data were not collected from the data subject;
- Article 17 previews require the user to select one of the six grounds in Article 17(1); Python validates the ground and incorporates its precise legal reference into the preview;
- Article 21(2)-(3) previews object specifically to direct-marketing processing, including related profiling where applicable;
- common wording reflects Article 12 timing, refusal-information and identity-verification rules without claiming that a response or outcome is guaranteed;
- the profile display name is required before composition, while stored Identity identifiers are deliberately not copied automatically into outgoing text to avoid unnecessary disclosure;
- a Target privacy email is shown when registered but is not required merely to preview a request;
- JavaScript can provide only the Case id and, for an erasure preview, the selected typed ground id; it cannot supply or override the generated subject/body/recipient;
- request previews are temporary presentation state and are invalidated whenever canonical application state changes;
- the Article 17 ground remains preview-only in M17. No schema migration is introduced solely for preview state; M18 must persist the exact user-approved outbound payload at dispatch time to bind review to what is actually sent.

The request templates are based on GDPR Articles 12, 15, 17, 19 and 21. They are deterministic legal-workflow templates rather than model-generated legal advice. Case-specific facts remain the user's responsibility and the application does not assert that an Article 17 ground or exception is factually established merely because it is selected for preview.

M16 remains the deadline foundation required before any future real request dispatch:

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

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `CaseService` owns Case lifecycle, deadline semantics and the request-preview use case. `RequestComposer` hides request wording behind a small deterministic interface. `HolidayCalendarProvider` owns jurisdiction-calendar lookup only. The model has no filesystem, browser, arbitrary networking, command execution, generic network primitive, jurisdiction authority or request-composition authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Verified complete multi-jurisdiction/local holiday calendars, real request delivery, response intake, monitoring and escalation remain future work. No real GDPR request dispatch is implemented yet.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence and append-only outbound audit
- Python owns canonical state and business logic
- Sensitive personal/investigative data and audit destinations are encrypted before persistence
- `CaseService` owns Case lifecycle, deadline semantics and request-preview orchestration
- `RequestComposer` owns deterministic request wording only
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use proposal identities, explicit review gates and separation between LLM proposals and canonical application state. Request composition is deterministic and local; the frontend cannot override generated request content, and M17 introduces no delivery mechanism. Historical deadline snapshots retain the legal/calendar inputs used when the Case was submitted.
