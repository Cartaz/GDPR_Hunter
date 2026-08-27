from __future__ import annotations

from core.domain.identity import Identifier, IdentifierKind, Identity
from ui.bridge import Bridge
from ui.research_runner import ResearchRunner


class FakeController:
    def get_bootstrap_state(self):
        return {"identity": {"displayName": None, "identifierCount": 0}, "milestone": "M7 — Async Research Integration"}

    def set_display_name(self, display_name):
        return {"displayName": display_name or None}

    def add_identifier(self, kind, value, label=None):
        if not value.strip():
            raise ValueError("Identifier value cannot be empty")
        return {"id": 1, "kind": kind, "label": label}


def test_sensitive_domain_repr_is_redacted():
    identity = Identity(id=1, display_name="Private Person")
    identifier = Identifier(id=1, kind=IdentifierKind.EMAIL, value="private@example.com", label="personal")

    assert "Private Person" not in repr(identity)
    assert "private@example.com" not in repr(identifier)
    assert "personal" not in repr(identifier)


def test_bridge_returns_safe_validation_error():
    controller = FakeController()
    bridge = Bridge(controller, ResearchRunner(controller))  # type: ignore[arg-type]

    result = bridge.addIdentifier("EMAIL", "   ", "")

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_bridge_rejects_research_without_explicit_user_approval():
    controller = FakeController()
    runner = ResearchRunner(controller)  # type: ignore[arg-type]
    bridge = Bridge(controller, runner)  # type: ignore[arg-type]

    result = bridge.researchArtifactUrls(1, 1, False)

    assert result["ok"] is False
    assert result["error"]["code"] == "APPROVAL_REQUIRED"
    assert runner.is_busy is False
