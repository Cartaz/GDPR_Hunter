from __future__ import annotations

import sqlite3

import pytest
from PySide6.QtCore import QUrlQuery

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.egress_policy import EgressDecision, EgressPolicy, OutboundActor
from core.application.identity_service import IdentityService
from core.application.outbound_delivery_service import OutboundDeliveryService
from core.application.request_approval_service import RequestApprovalService
from core.application.target_service import TargetService
from core.domain.case import CaseStatus
from core.domain.delivery import DeliveryEventType
from core.domain.identity import IdentifierKind
from core.domain.rights import CaseRight, RightsPolicy
from core.storage.approved_outbound_request_repository import (
    ApprovedOutboundRequestRepository,
)
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.delivery_event_repository import DeliveryEventRepository
from core.storage.identity_repository import IdentityRepository
from core.storage.outbound_audit_repository import OutboundAuditRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository
from ui.native_mail import build_mailto_url

TEST_KEY = b"b" * 32


class FakeMailClient:
    def __init__(self, accepted: bool = True, error: OSError | None = None) -> None:
        self.accepted = accepted
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def open_message(self, recipient_email: str, subject: str, body: str) -> bool:
        self.calls.append((recipient_email, subject, body))
        if self.error is not None:
            raise self.error
        return self.accepted


def build_services(tmp_path, mail_client: FakeMailClient | None = None):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    targets = TargetService(TargetRepository(database))
    cases = CaseService(
        CaseRepository(database),
        identity,
        targets,
        RightsPolicy(),
        DeadlineEngine(),
    )
    approvals = RequestApprovalService(
        cases,
        ApprovedOutboundRequestRepository(database, sensitive),
    )
    audit = OutboundAuditRepository(database, sensitive)
    events = DeliveryEventRepository(database)
    client = mail_client or FakeMailClient()
    delivery = OutboundDeliveryService(
        approvals,
        cases,
        EgressPolicy(audit),
        events,
        client,
    )
    return database, identity, targets, cases, approvals, audit, events, client, delivery


def create_approved_request(tmp_path, mail_client: FakeMailClient | None = None):
    services = build_services(tmp_path, mail_client)
    _database, identity, targets, cases, approvals, _audit, _events, _client, _delivery = services
    identity.set_display_name("Alice Example")
    identifier = identity.add_identifier(IdentifierKind.EMAIL, "alice@example.test", "account")
    target = targets.create_target("Example Corp", "example.test", "privacy@example.test")
    assert identifier.id is not None
    assert target.id is not None
    case = cases.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None
    approved = approvals.approve(
        case.id,
        identifier_ids=(identifier.id,),
        approved_by_user=True,
    )
    assert approved.id is not None
    return services, case, approved


def test_handoff_requires_explicit_user_approval_without_side_effects(tmp_path) -> None:
    services, _case, approved = create_approved_request(tmp_path)
    _database, _identity, _targets, _cases, _approvals, audit, events, client, delivery = services

    with pytest.raises(PermissionError, match="explicit user approval"):
        delivery.handoff_approved_request(approved.id, approved_by_user=False)

    assert client.calls == []
    assert events.list_events() == []
    assert audit.list_entries() == []


def test_handoff_uses_exact_approved_payload_even_after_identity_changes(tmp_path) -> None:
    services, _case, approved = create_approved_request(tmp_path)
    _database, identity, _targets, _cases, approvals, audit, events, client, delivery = services
    identity.set_display_name("Changed Name")

    result = delivery.handoff_approved_request(approved.id, approved_by_user=True)
    persisted = approvals.get(approved.id)

    assert result.approved_request_id == approved.id
    assert result.accepted is True
    assert client.calls == [(persisted.recipient_email, persisted.subject, persisted.body)]
    assert "Alice Example" in client.calls[0][1]
    assert "Changed Name" not in client.calls[0][1]
    assert "Alice Example" in client.calls[0][2]
    assert "Changed Name" not in client.calls[0][2]

    delivery_events = events.list_events()
    assert [item.event_type for item in delivery_events] == [
        DeliveryEventType.HANDOFF_ACCEPTED,
        DeliveryEventType.HANDOFF_REQUESTED,
    ]
    assert delivery_events[0].attempt_id == delivery_events[1].attempt_id == result.attempt_id
    assert all(item.approved_request_id == approved.id for item in delivery_events)

    audit_entries = audit.list_entries()
    assert len(audit_entries) == 1
    assert audit_entries[0].operation == "SYSTEM_MAIL_CLIENT_HANDOFF"
    assert audit_entries[0].destination == persisted.recipient_email
    assert audit_entries[0].data_class == "APPROVED_GDPR_REQUEST"
    assert audit_entries[0].actor is OutboundActor.USER
    assert audit_entries[0].approved_by_user is True
    assert audit_entries[0].decision is EgressDecision.ALLOW


def test_rejected_handoff_is_recorded_without_claiming_send(tmp_path) -> None:
    client = FakeMailClient(accepted=False)
    services, _case, approved = create_approved_request(tmp_path, client)
    _database, _identity, _targets, _cases, _approvals, _audit, events, _client, delivery = services

    result = delivery.handoff_approved_request(approved.id, approved_by_user=True)

    assert result.accepted is False
    assert [item.event_type for item in events.list_events()] == [
        DeliveryEventType.HANDOFF_REJECTED,
        DeliveryEventType.HANDOFF_REQUESTED,
    ]


def test_os_error_records_rejected_event_and_propagates(tmp_path) -> None:
    client = FakeMailClient(error=OSError("mail handler failed"))
    services, _case, approved = create_approved_request(tmp_path, client)
    _database, _identity, _targets, _cases, _approvals, _audit, events, _client, delivery = services

    with pytest.raises(OSError, match="mail handler failed"):
        delivery.handoff_approved_request(approved.id, approved_by_user=True)

    assert [item.event_type for item in events.list_events()] == [
        DeliveryEventType.HANDOFF_REJECTED,
        DeliveryEventType.HANDOFF_REQUESTED,
    ]


def test_non_draft_case_cannot_handoff_approved_payload(tmp_path) -> None:
    services, case, approved = create_approved_request(tmp_path)
    _database, _identity, _targets, cases, _approvals, audit, events, client, delivery = services
    cases.transition_case(case.id, CaseStatus.CANCELLED)

    with pytest.raises(ValueError, match="Only a draft case"):
        delivery.handoff_approved_request(approved.id, approved_by_user=True)

    assert client.calls == []
    assert events.list_events() == []
    assert audit.list_entries() == []


def test_delivery_event_table_is_append_only_and_schema_v8(tmp_path) -> None:
    services, _case, approved = create_approved_request(tmp_path)
    database, _identity, _targets, _cases, _approvals, _audit, events, _client, _delivery = services
    recorded = events.record(
        "attempt-test",
        approved.id,
        DeliveryEventType.HANDOFF_REQUESTED,
        "2026-09-01T12:00:00Z",
    )
    assert recorded.id is not None

    with database.connection_scope() as connection:
        version = connection.execute(
            "SELECT schema_version FROM schema_meta WHERE id = 1"
        ).fetchone()[0]
    assert version == 8

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute(
            "UPDATE outbound_delivery_events SET event_type = 'HANDOFF_ACCEPTED' WHERE id = ?",
            (recorded.id,),
        )
    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute("DELETE FROM outbound_delivery_events WHERE id = ?", (recorded.id,))


def test_mailto_url_preserves_approved_recipient_subject_and_body() -> None:
    subject = "GDPR request — Alice + Example"
    body = "Line one\nLine two & more? yes=1"
    url = build_mailto_url("privacy@example.test", subject, body)
    query = QUrlQuery(url)

    assert url.scheme() == "mailto"
    assert url.path() == "privacy@example.test"
    assert query.queryItemValue("subject") == subject
    assert query.queryItemValue("body") == body


def test_frontend_handoff_can_supply_only_approved_request_id_and_approval() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    bridge = (root / "ui" / "bridge.py").read_text(encoding="utf-8")
    javascript = (root / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")

    handoff_slot = bridge.split("def handoffApprovedRequest", 1)[1].split("def submitCase", 1)[0]
    assert "approved_request_id: int" in handoff_slot
    assert "approved_by_user: bool" in handoff_slot
    assert "subject" not in handoff_slot
    assert "body" not in handoff_slot
    assert "recipient" not in handoff_slot

    handoff_call = javascript.split("backend.handoffApprovedRequest(", 1)[1].split(");", 1)[0]
    assert "approvedRequestId" in handoff_call
    assert "approved" in handoff_call
    assert "requestPreviewSubjectNode.value" not in handoff_call
    assert "requestPreviewBodyNode.value" not in handoff_call
    assert "Opening the mail client is not proof that the message was sent." in javascript
