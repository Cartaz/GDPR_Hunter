# GDPR Hunter

GDPR Hunter is a local-first desktop privacy application under active development.

## Current status

Milestone **M21 — Response Intake** is implemented on the current development branch. GDPR Hunter can manually record controller correspondence against a submitted Case while it is awaiting a response, preserving the raw response locally without interpreting it or changing the Case outcome. **M21 is manual local intake: it does not read an inbox, verify delivery, classify GDPR compliance, or automatically complete a Case.**

M8 introduced bounded OpenAI-compatible inference without tools or direct application authority. M9 added strict inert `CLAIM` and `RESEARCH_EVIDENCE` proposals. M10 added encrypted append-only outbound auditing. M11 added explicitly reviewed, atomic Claim acceptance. M12 connected bounded Investigation Evidence to inference and strict proposal parsing without mutation. M13 moved model analysis onto an owned Qt worker and wired configured inference into production. M14 added Python-owned opaque proposal identities and one-use Claim review. M15 added explicitly reviewed research-proposal execution while keeping outbound destinations under Python policy control. M16 added explicit controller-action jurisdiction and immutable deadline/calendar snapshots. M17 added deterministic local request composition for Articles 15, 17 and 21. M18 added encrypted append-only approved outbound payloads. M19 added reviewed default-mail-client handoff without claiming that opening a mail client proves transmission. M20 bound each confirmed submission to the exact immutable approved payload the user states was actually transmitted.

M21 adds a separate inbound-correspondence boundary:

- `ResponseIntakeService` owns manual controller-response intake and does not reuse Investigation `Artifact` semantics;
- a new response may be recorded only while the Case is `AWAITING_RESPONSE` and has a recorded request receipt date;
- the response date cannot precede that request receipt date;
- the repository repeats the Case-status precondition inside the SQLite insert so a concurrent Case state change cannot create an incoherent response record;
- supported channels are email, postal mail, web portal, phone/call notes and other;
- sender and subject are optional; the response body/call notes are required;
- sender, subject and body are encrypted with `SensitiveStore` before SQLite persistence;
- schema v10 adds append-only `case_responses`; SQLite rejects updates and deletes;
- multiple responses may be recorded for one Case and do not alter the stored deadline snapshot;
- recording a response does not classify whether the controller complied with the GDPR and does not automatically move the Case to `COMPLETED`;
- response summaries are loaded only for the Case the user opens, and full response content is decrypted only when the user explicitly opens one response;
- response content is not included in application bootstrap state;
- no IMAP, Gmail/provider API, inbox credentials, new network path, worker thread, runtime dependency or model authority is introduced.

M20 remains the submission-provenance boundary:

- every newly recorded submission requires an exact `approved_request_id` belonging to that Case;
- the UI exposes the Case's approval history and lets the user select the precise payload that was actually transmitted, rather than silently assuming the newest approval;
- JavaScript and QWebChannel provide only Case ID, approved-request ID, controller receipt date, jurisdiction and an explicit confirmation boolean; recipient, subject and body cannot be supplied or rewritten at submission time;
- `CaseService` keeps submission and deadline semantics in one use case while `CaseRepository` atomically persists the Case transition, immutable deadline snapshot, submission binding and existing `REQUEST_SUBMITTED` timeline event;
- schema v9 adds `case_submission_bindings`, with one immutable binding per Case and one Case per approved payload; SQLite rejects updates and deletes;
- a payload belonging to another Case causes the entire transaction to roll back, leaving the Case `DRAFT` with no deadline snapshot or submission event;
- M19 handoff events are deliberately not required and are never interpreted as proof of sending; a user may have transmitted the approved payload through another client;
- pre-M20 submitted Cases remain usable but are not assigned fabricated payload provenance. They may legitimately have no submission binding.

M19 remains the deliberately narrow mail-client handoff boundary:

- JavaScript may provide only an approved-request ID and an explicit approval boolean; it cannot provide or override the recipient, subject or body;
- `OutboundDeliveryService` resolves the immutable approved payload by ID and never recomposes request content at handoff time;
- the approved payload may be handed off only while its Case remains `DRAFT`;
- the existing `EgressPolicy` authorizes and audits the outbound destination before native handoff;
- the native adapter uses Qt `QDesktopServices` to open an RFC 6068 `mailto:` URL in the operating system's default mail client; no SMTP credentials, provider API, generic network primitive or new dependency is introduced;
- schema v8 adds append-only `outbound_delivery_events`, recording `HANDOFF_REQUESTED` followed by `HANDOFF_ACCEPTED` or `HANDOFF_REJECTED`;
- delivery events contain only approved-request IDs, attempt IDs, event types and timestamps; recipient, subject and body are not duplicated into the event log;
- an incomplete attempt may remain with only `HANDOFF_REQUESTED`, preserving crash ambiguity rather than inventing a terminal result;
- `HANDOFF_ACCEPTED` is **not** evidence that the user pressed Send or that the controller received the request.

M18 remains the approval boundary before any outbound handoff or confirmed submission:

- identifiers stored in the Identity Vault remain excluded by default; the user explicitly selects which identifiers, if any, are disclosed to help the controller locate relevant records;
- Python validates selected identifier IDs against the canonical local Identity and rejects duplicates, inactive identifiers or IDs that do not belong to the identity;
- `RequestComposer` remains the sole owner of request wording and inserts only the explicitly selected identifiers;
- approval is allowed only while the Case is still `DRAFT` and requires a registered Target privacy email;
- `RequestApprovalService` recomposes from canonical Python state and persists the exact recipient, subject, body, legal basis, Article 17 ground and identifier selection;
- approved recipient email, subject and body are encrypted with the authenticated `SensitiveStore` before SQLite persistence;
- approved payloads are append-only. A new approval creates a new historical record; existing approval records cannot be updated or deleted through SQLite;
- normal approval listings expose metadata only and do not decrypt message subject or body.

The request templates remain deterministic legal-workflow templates based on GDPR Articles 12, 15, 17, 19 and 21 rather than model-generated legal advice. Case-specific facts remain the user's responsibility and the application does not assert that an Article 17 ground or exception is factually established merely because it is selected.

M16 remains the deadline foundation required for recorded submissions:

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

`InvestigationService` remains the sole owner of Investigation/Evidence/Claim mutations. `CaseService` owns Case lifecycle, confirmed-submission semantics, deadline semantics and request-preview orchestration. `CaseRepository` owns atomic Case persistence and the immutable submission binding. `ResponseIntakeService` owns manual Case correspondence intake. `CaseResponseRepository` owns encrypted append-only response persistence. `RequestComposer` owns deterministic request wording. `RequestApprovalService` owns the transition from semantic review selection to a durable approved payload. `ApprovedOutboundRequestRepository` owns encrypted append-only approval persistence. `OutboundDeliveryService` owns the reviewed approved-ID-to-native-handoff use case. `DeliveryEventRepository` owns its append-only handoff event log. `HolidayCalendarProvider` owns jurisdiction-calendar lookup only. The model has no filesystem, browser, arbitrary networking, command execution, generic network primitive, jurisdiction authority, request-composition authority, request-approval authority, mail-client handoff authority, submission-confirmation authority or response-intake authority.

Supported GDPR Case workflows are Article 15 access/provenance, Article 17 erasure and Article 21(2)-(3) direct-marketing objection. Verified complete multi-jurisdiction/local holiday calendars, independently verifiable email transport/delivery receipts, automated inbox intake, response-compliance review, monitoring and escalation remain future work.

## Architecture

- Python 3.12+
- PySide6 / Qt6
- QWebEngineView with local HTML/CSS/vanilla JavaScript only
- QWebChannel with a single `backend` object
- SQLite for operational persistence, append-only outbound audit, approved outbound payload records, delivery events, immutable submission bindings and encrypted Case-response records
- Python owns canonical state and business logic
- Sensitive personal/investigative data, audit destinations, approved outbound message contents and inbound response contents are encrypted before persistence
- `CaseService` owns Case lifecycle, confirmed-submission semantics, deadline semantics and request-preview orchestration
- `CaseRepository` atomically persists Case lifecycle changes, immutable deadline snapshots and exact approved-payload submission bindings
- `ResponseIntakeService` owns manual inbound correspondence validation without interpreting compliance
- `CaseResponseRepository` owns encrypted append-only Case-response persistence and metadata-only listings
- `RequestComposer` owns deterministic request wording only
- `RequestApprovalService` owns explicit request approval and exact-payload capture
- `ApprovedOutboundRequestRepository` owns encrypted append-only approved-payload persistence
- `OutboundDeliveryService` owns reviewed handoff of an immutable approved request by ID
- `DeliveryEventRepository` owns append-only handoff event persistence
- `SystemMailClientHandoff` is the narrow Qt-native adapter for the default mail client
- `HolidayCalendarProvider` owns explicit jurisdiction-to-calendar resolution with source/version metadata
- `DeadlineEngine` owns calendar-month arithmetic, working-day roll-forward and extension-timeliness assessment
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

The application is designed around local-first processing, explicit outbound-data control, encrypted sensitive persistence, append-only audit/correspondence records, immutable Artifact metadata, evidence provenance, deterministic parsing, SSRF-resistant bounded research, owned asynchronous execution, bounded inference/context, strict model-output validation, opaque one-use model proposal identities, explicit review gates and separation between LLM proposals and canonical application state. Request composition, approval, mail-client handoff, confirmed submission and response intake are Python-owned. M20 records which exact immutable payload the user confirms was transmitted while preserving M19 handoff as a distinct weaker event that never implies sending. M21 keeps inbound correspondence encrypted and outside bootstrap state, decrypting full content only on explicit local access and making no automatic legal/compliance conclusion from the response.