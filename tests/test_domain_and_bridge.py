from __future__ import annotations

import sqlite3

from core.domain.identity import Identifier, IdentifierKind, Identity
from ui.bridge import Bridge
from ui.research_runner import ResearchRunner


class FakeController:
    def get_bootstrap_state(self):
        return {
            "identity": {"displayName": None, "identifierCount": 0},
            "milestone": "M14 — Python-owned Proposal Review",
        }

    def set_display_name(self, display_name):
        if display_name == "db-error":
            raise sqlite3.OperationalError("simulated database failure")
        return {"displayName": display_name or None}


def test_sensitive_domain_repr_is_redacted():
    identity = Identity(id=1, display_name="Private Person")
    identifier = Identifier(id=1, kind=IdentifierKind.EMAIL, value="private@example.com", label="personal")

    assert "Private Person" not in repr(identity)
    assert "private@example.com" not in repr(identifier)
    assert "personal" not in repr(identifier)


def test_bridge_returns_safe_operational_error_without_leaking_backend_details():
    controller = FakeController()
    bridge = Bridge(controller, ResearchRunner(controller))  # type: ignore[arg-type]

    result = bridge.setDisplayName("db-error")

    assert result["ok"] is False
    assert result["error"] == {
        "code": "OPERATION_FAILED",
        "message": "Operation failed. Check the logs for details.",
    }
    assert "simulated" not in result["error"]["message"]


def test_bridge_rejects_research_without_explicit_user_approval():
    controller = FakeController()
    runner = ResearchRunner(controller)  # type: ignore[arg-type]
    bridge = Bridge(controller, runner)  # type: ignore[arg-type]

    result = bridge.researchArtifactUrls(1, 1, False)

    assert result["ok"] is False
    assert result["error"]["code"] == "APPROVAL_REQUIRED"
    assert runner.is_busy is False
