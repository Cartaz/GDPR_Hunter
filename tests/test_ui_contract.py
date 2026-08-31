from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl

from ui.window import LocalOnlyPage, MainWindow, is_allowed_local_url

ROOT = Path(__file__).resolve().parents[1]


def test_ui_modules_import():
    assert LocalOnlyPage is not None
    assert MainWindow is not None


def test_local_html_has_no_remote_assets():
    html = (ROOT / "ui" / "web" / "index.html").read_text(encoding="utf-8")

    assert 'src="http://' not in html
    assert 'src="https://' not in html
    assert 'href="http://' not in html
    assert 'href="https://' not in html
    assert "qrc:///qtwebchannel/qwebchannel.js" in html


def test_frontend_does_not_render_backend_data_with_inner_html():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")

    assert "innerHTML" not in javascript


def test_frontend_cannot_assign_privileged_investigation_provenance():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert "DETERMINISTIC_ANALYSIS" not in javascript
    assert "AUTHORITATIVE_SOURCE" not in javascript
    assert "provenance:" not in javascript
    assert "addUserEvidence" in bridge
    assert "createUserClaim" in bridge
    assert "def addEvidence" not in bridge
    assert "def createClaim" not in bridge


def test_model_claim_review_uses_opaque_token_not_frontend_provenance_payload():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert "backend.acceptModelClaim(token, approved" in javascript
    assert "def acceptModelClaim(self, proposal_token: str, approved_by_user: bool)" in bridge
    claim_slot = bridge.split("def acceptModelClaim", 1)[1].split(
        "def executeModelResearchProposal", 1
    )[0]
    assert "proposal_token" in claim_slot
    assert "statement" not in claim_slot
    assert "confidence" not in claim_slot
    assert "evidence_ids" not in claim_slot


def test_reviewed_model_research_uses_only_opaque_token_and_approval_from_frontend():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert "backend.executeModelResearchProposal(token, approved" in javascript
    assert "Research evidence" in javascript
    research_slot = bridge.split("def executeModelResearchProposal", 1)[1].split(
        "def discardModelProposal", 1
    )[0]
    assert "proposal_token: str" in research_slot
    assert "approved_by_user: bool" in research_slot
    assert "source_url" not in research_slot
    assert "destination" not in research_slot
    assert "rationale" not in research_slot
    assert "evidence_id:" not in research_slot


def test_case_submission_requires_explicit_jurisdiction_without_location_inference():
    html = (ROOT / "ui" / "web" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert 'id="case-jurisdiction"' in html
    assert "place where the controller must act" in html
    assert "caseJurisdictionNode.value" in javascript
    assert "backend.submitCase(caseId, receivedOn, jurisdiction" in javascript
    assert "navigator.geolocation" not in javascript
    assert "def submitCase(" in bridge
    submit_slot = bridge.split("def submitCase", 1)[1].split("def recordCaseExtension", 1)[0]
    assert "jurisdiction_code: str" in submit_slot
    assert "target_domain" not in submit_slot
    assert "location" not in submit_slot


def test_research_bridge_exposes_semantic_async_action_not_network_primitive():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")
    runner = (ROOT / "ui" / "research_runner.py").read_text(encoding="utf-8")

    assert "researchArtifactUrls" in javascript
    assert "researchArtifactUrls" in bridge
    assert "executeModelResearchProposal" in bridge
    assert "fetchUrl" not in bridge
    assert "http.client" not in bridge
    assert "QThread" not in bridge
    assert "QThread" in runner


def test_local_navigation_is_confined_to_web_root(tmp_path):
    web_root = tmp_path / "ui" / "web"
    web_root.mkdir(parents=True)
    allowed = web_root / "index.html"
    allowed.write_text("ok", encoding="utf-8")
    outside = tmp_path / "private.txt"
    outside.write_text("private", encoding="utf-8")

    assert is_allowed_local_url(QUrl.fromLocalFile(str(allowed)), web_root)
    assert not is_allowed_local_url(QUrl.fromLocalFile(str(outside)), web_root)
    assert not is_allowed_local_url(QUrl("https://example.com"), web_root)
