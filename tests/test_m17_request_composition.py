from __future__ import annotations

import pytest

from core.application.case_service import CaseService
from core.application.deadline_engine import DeadlineEngine
from core.application.identity_service import IdentityService
from core.application.target_service import TargetService
from core.domain.identity import IdentifierKind
from core.domain.rights import CaseRight, ErasureGround, RightsPolicy
from core.storage.case_repository import CaseRepository
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.sensitive_store import SensitiveStore
from core.storage.target_repository import TargetRepository

TEST_KEY = b"r" * 32


def build_case_service(tmp_path):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    targets = TargetService(TargetRepository(database))
    service = CaseService(
        CaseRepository(database),
        identity,
        targets,
        RightsPolicy(),
        DeadlineEngine(),
    )
    return service, identity, targets


def create_named_case(tmp_path, right: CaseRight):
    service, identity, targets = build_case_service(tmp_path)
    identity.set_display_name("Alice Example")
    target = targets.create_target("Example Corp", "example.test", "privacy@example.test")
    assert target.id is not None
    case = service.create_case(target.id, right)
    assert case.id is not None
    return service, identity, case


def test_access_preview_is_deterministic_complete_and_does_not_overshare_identifiers(tmp_path) -> None:
    service, identity, case = create_named_case(tmp_path, CaseRight.ACCESS_PROVENANCE)
    identity.add_identifier(IdentifierKind.EMAIL, "private-personal@example.test", "private login")

    first = service.preview_request(case.id)
    second = service.preview_request(case.id)

    assert first == second
    assert first.recipient_name == "Example Corp"
    assert first.recipient_email == "privacy@example.test"
    assert first.legal_basis == "Article 15"
    assert first.subject == "GDPR Article 15 access request — Alice Example"
    assert "copy of the personal data" in first.body
    assert "available information about their source" in first.body
    assert "automated decision-making" in first.body
    assert "appropriate safeguards" in first.body
    assert "Article 12(3)" in first.body
    assert "Article 12(4)" in first.body
    assert "Article 12(6)" in first.body
    assert "private-personal@example.test" not in first.body
    assert "private login" not in first.body
    assert service.get_case(case.id).status.value == "DRAFT"
    assert [event.event_type for event in service.list_timeline(case.id)] == ["CREATED"]


def test_erasure_preview_requires_specific_article_17_ground(tmp_path) -> None:
    service, _identity, case = create_named_case(tmp_path, CaseRight.ERASURE)

    with pytest.raises(ValueError, match="Select the Article 17 ground"):
        service.preview_request(case.id)

    preview = service.preview_request(
        case.id,
        erasure_ground=ErasureGround.NO_LONGER_NECESSARY,
    )

    assert preview.legal_basis == "Article 17"
    assert "Article 17(1)(a)" in preview.body
    assert "no longer necessary" in preview.body.lower()
    assert "Article 17(3)" in preview.body
    assert "Article 19" in preview.body


def test_all_six_article_17_grounds_are_exposed_by_policy() -> None:
    policies = RightsPolicy().erasure_grounds()

    assert {item.ground for item in policies} == set(ErasureGround)
    assert len(policies) == 6
    assert all(item.article.startswith("Article 17(1)(") for item in policies)


def test_direct_marketing_preview_is_specific_and_rejects_erasure_ground(tmp_path) -> None:
    service, _identity, case = create_named_case(tmp_path, CaseRight.DIRECT_MARKETING_OBJECTION)

    preview = service.preview_request(case.id)

    assert preview.legal_basis == "Article 21(2)-(3)"
    assert "Article 21(2)" in preview.body
    assert "Article 21(3)" in preview.body
    assert "profiling" in preview.body
    assert "stop processing my personal data for those direct-marketing purposes" in preview.body

    with pytest.raises(ValueError, match="grounds apply only to erasure cases"):
        service.preview_request(
            case.id,
            erasure_ground=ErasureGround.UNLAWFUL_PROCESSING,
        )


def test_preview_requires_display_name_but_not_a_recipient_email(tmp_path) -> None:
    service, identity, targets = build_case_service(tmp_path)
    target = targets.create_target("No Mail Corp", "nomail.test", None)
    assert target.id is not None
    case = service.create_case(target.id, CaseRight.ACCESS_PROVENANCE)
    assert case.id is not None

    with pytest.raises(ValueError, match="Set a display name"):
        service.preview_request(case.id)

    identity.set_display_name("Alice Example")
    preview = service.preview_request(case.id)

    assert preview.recipient_name == "No Mail Corp"
    assert preview.recipient_email is None
    assert preview.subject.startswith("GDPR Article 15")
