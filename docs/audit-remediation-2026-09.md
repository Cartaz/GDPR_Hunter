# Audit remediation — September 2026

Baseline: `5151f7db2d0a1463a080fd5a2d0c5cbb0b8470ac` (M21). Scope: the fifteen findings in the 5 September audit. This change preserves the local desktop architecture and does not add autonomous model authority or email sending.

| Finding | Correction | Regression evidence |
| --- | --- | --- |
| A01 — Article 17 enum/SQL mismatch | Schema v11 uses all six canonical grounds and maps the three legacy spellings. Approval ciphertext, IDs, delivery events and submission bindings survive migration. | Every enum round-trips; populated legacy migration and append-only tests. |
| A02 — Partial DDL migration | Explicit `BEGIN IMMEDIATE` covers schema creation and each version step, including the schema-version update. The approval rebuild validates foreign keys before commit. | Injected failures during fresh creation, v9→10 and v10→11 leave the old schema intact and retry successfully. |
| A03 — Incomplete research marked done | One database transaction stores the reference artifact metadata, redirects, final URL, derived findings and completion marker. Failed writes compensate the newly stored encrypted file. | Mid-batch failure, retry, deduplication and historical incomplete-marker tests. |
| A04 — Response context mixed between Cases | Dedicated response module owns drafts by Case ID and ignores stale list/detail callbacks. Submission captures the Case and draft, and does not erase newer edits or another Case's draft. | Actual Qt WebEngine/bridge/database test plus deliberately reordered callbacks. |
| A05 — Running threads destroyed on exit | Window close requests cancellation and keeps the event loop and worker owners alive until finished. Final application teardown joins workers. Network operations have total deadlines, socket interruption and an owned, terminated/reaped DNS helper. | Worker ownership, pending window close, blocked DNS, trickling headers/body and cancellation tests. |
| A06 — Local analysis blocks the GUI | Analysis uses the existing owned worker, deduplicates under one database write lock, commits a batch and rejects more than 2,000 findings without partial results. | Off-thread execution, batch rollback, duplicate-analysis and finding-limit tests. |
| A07 — Unhandled errors leave busy state | Storage integrity has a dedicated error. UI boundaries return safe errors and every worker emits exactly one terminal outcome. A committed action whose refresh fails returns success with a warning against repeating it. | SQLite, integrity, runtime and validation failures exercised for all worker modes and bridge refresh. |
| A08 — CSS overrides hidden state | Explicit `[hidden]` rule wins over layout classes. | Computed styles checked in the real WebEngine document. |
| A09 — Malformed settings/startup | Invalid encodings recover with a logged warning, preserving the original. Endpoint validation lives in configuration. Atomic geometry saving preserves configured endpoints and refuses to overwrite malformed settings. Rotating local logs provide a durable diagnostic location. | Invalid UTF-8, settings round-trip and geometry-preservation tests. |
| A10 — Claim support/verification invariants | Support is rechecked atomically for status and relationship changes. Corroboration requires at least two artifacts with distinct content hashes; corroboration and verification each require a recorded human review note. Schema v12 stores encrypted append-only reviews. | Same-source and duplicate-content rejection, support-removal rollback and required/encrypted/immutable review tests. |
| A11 — Historical approved payload inaccessible | A semantic read-by-ID API exposes the exact encrypted historical payload on demand, including older approvals. A separate read-only dialog cannot approve or recompose it. | Real UI reads the first approval after identity changes and reapproval; bootstrap stays metadata-only. |
| A12 — Bridge/frontend ownership | Proposal review DTOs move into an application controller; the bridge keeps transport and scheduling glue. Response workflow moves into its own JS module. Manual evidence drops the discarded artifact argument. Selections survive unrelated refreshes; stale preview/investigation/timeline callbacks are guarded. | Existing semantic bridge tests, manual provenance tests and native response/history tests. |
| A13 — HTML-only email missing links | Inert HTML parsing reads visible text and anchor URLs, preserves MIME-part locators, and excludes script/style/head/template content and attachment subtrees. | HTML-only and multipart extraction tests; no renderer or network fetch is involved. |
| A14 — NaN accepted as confidence | Confidence validation rejects non-finite/extreme numbers; model JSON rejects non-standard constants, overflowing floats and duplicate object keys. | Parameterized parser/JSON regressions. |
| A15 — Missing key silently replaced | Startup checks for an existing archive before database initialization and refuses to create a replacement key. Recovery instructions identify the original keyring and encrypted data as a single backup set. | Mocked-keyring test proves no replacement write; startup test proves existing database bytes are untouched. |

## Migration and recovery details

- The current schema is **v12**. Upgrading from v10 applies v11 and then v12. Each version step is atomic; an interrupted step can be retried. Migration tests use the old CHECK constraint and real referenced rows, not only a changed version number.
- Incomplete historical research snapshots are retained. A pre-fix `research.request` marker alone no longer proves completion; the next explicitly approved research action may fetch a new, complete snapshot. Successful pre-fix snapshots without the new completion marker can also be fetched once again.
- Pre-v12 Claim statuses are not silently rewritten or retroactively called human-verified. A historical `CORROBORATED`/`VERIFIED` Claim without a matching review record is explicitly labeled in the UI. Distinct artifact contents are a necessary provenance check, not an automatic proof of source independence or truth; the human review note must explain that assessment.
- Database and artifact-file operations cannot form a cross-filesystem SQLite transaction. Ordinary failures delete the newly created encrypted file. A process/power failure between file creation and database commit can leave an unreferenced encrypted file; existing referenced data is retained. No automatic deletion of historical/orphan files is added.
- If a database was already left partially migrated by an old version, this change does not blindly delete tables or rewrite its version. Preserve the database and original keyring and diagnose that specific archive before repair.

## Validation and limits

Local checks use Python 3.12 and supported PySide6 6.10.2, with offscreen WebEngine and temporary synthetic archives. The native probe runs in a separate QApplication process so QCoreApplication unit tests cannot mask UI failures. No real mailbox, user keyring or inference server is touched. GitHub CI also runs compileall, Ruff, pytest and the dependency audit against the declared dependency range.

Local result at review: **201 tests passed** (147 baseline cases plus 54 additional cases), compileall passed, Ruff passed, installer syntax and `git diff --check` passed. CI results remain independently attached to the pull request and its exact commit. Runner cancellation uses a thread-safe Python event, including the network watchdog; Qt interruption queries are not called from foreign threads.

Production still needs an acceptance check on the user's KDE/CachyOS keyring and native mail client and against the configured llama.cpp LAN endpoint. These platform integrations cannot be verified by an isolated CI environment. The previously observed PySide6 6.11.2 import failure was environment-specific and is not attributed to this application without evidence.

Analysis is bounded per artifact; the application does not yet paginate all archive-wide bootstrap metadata. Very large archives may still need pagination and targeted state updates. The work here fixes the demonstrated synchronous analysis/batch-write path and the concrete ownership defects; it does not claim unlimited archive scalability.

Network limits are 120 seconds per inference request and 48 seconds per fetched research document, including redirects. DNS is limited to at most 8 seconds within that budget. A research job with multiple URLs can take longer overall; cancellation is checked between documents and before starting a persistence unit. The final filesystem transaction is allowed to finish coherently. No software timeout can guarantee progress if the operating system or underlying storage is itself hung.

## Implementation references

- [SQLite generalized ALTER TABLE procedure](https://www.sqlite.org/lang_altertable.html): table rebuild with foreign keys disabled outside the transaction and checked before commit.
- [Qt QThread lifecycle](https://doc.qt.io/qt-6/qthread.html): a running QThread must remain owned until it finishes; interruption is cooperative.
- The executable regressions are in `tests/test_audit_integrity.py`, `tests/test_audit_lifecycle.py`, `tests/test_audit_native_ui.py` and `tests/native_audit_probe.py`, alongside the existing milestone tests.
