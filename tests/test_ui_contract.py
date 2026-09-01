from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl

from ui.window import LocalOnlyPage, MainWindow, is_allowed_local_url

ROOT = Path(__file__).resolve().parents[1]
JS_ROOT = ROOT / "ui" / "web" / "js"


def frontend_javascript() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(JS_ROOT.glob("*.js"))
    )


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
    assert "innerHTML" not in frontend_javascript()


def test_case_workflow_is_owned_by_focused_frontend_module():
    app = (JS_ROOT / "app.js").read_text(encoding="utf-8")
    case_workflow = (JS_ROOT / "case_workflow.js").read_text(encoding="utf-8")

    assert 'import { createCaseWorkflow } from "./case_workflow.js";' in app
    assert "caseWorkflow.render(state)" in app
    assert "caseWorkflow.setBackend(backend)" in app
    assert 'document.getElementById("case-list")' not in app
    assert 'document.getElementById("response-form")' not in app
    assert "export function createCaseWorkflow" in case_workflow
    assert "function renderCases" in case_workflow
    assert "function loadCaseResponses" in case_workflow
    assert "selectedResponseCaseId !== requestedCaseId" in case_workflow
    assert "caseChanged" in case_workflow
    assert "resetResponseDraft()" in case_workflow


def test_frontend_cannot_assign_privileged_investigation_provenance():
    javascript = frontend_javascript()
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert "DETERMINISTIC_ANALYSIS" not in javascript
    assert "AUTHORITATIVE_SOURCE" not in javascript
    assert "provenance:" not in javascript
    assert "addUserEvidence" in bridge
    assert "createUserClaim" in bridge
    assert "def addEvidence" not in bridge
    assert "def createClaim" not in bridge


def test_model_claim_review_uses_opaque_token_not_frontend_provenance_payload():
    javascript = frontend_javascript()
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
    javascript = frontend_javascript()
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


def test_case_submission_requires_explicit_payload_jurisdiction_and_confirmation():
    html = (ROOT / "ui" / "web" / "index.html").read_text(encoding="utf-8")
    javascript = frontend_javascript()
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert 'id="case-jurisdiction"' in html
    assert "place where the controller must act" in html
    assert "selecting an immutable approved payload" in html
    assert "caseJurisdictionNode.value" in javascript
    assert "backend.submitCase(" in javascript
    assert "approvedRequestId" in javascript
    assert "actually transmitted" in javascript
    assert "navigator.geolocation" not in javascript
    submit_slot = bridge.split("def submitCase", 1)[1].split("def recordCaseExtension", 1)[0]
    assert "case_id: int" in submit_slot
    assert "approved_request_id: int" in submit_slot
    assert "received_on: str" in submit_slot
    assert "jurisdiction_code: str" in submit_slot
    assert "confirmed_by_user: bool" in submit_slot
    assert "target_domain" not in submit_slot
    assert "location" not in submit_slot
    assert "subject" not in submit_slot
    assert "body" not in submit_slot
    assert "recipient" not in submit_slot


def test_request_preview_is_read_only_python_composed_and_identifier_opt_in():
    html = (ROOT / "ui" / "web" / "index.html").read_text(encoding="utf-8")
    javascript = frontend_javascript()
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert 'id="request-preview-body"' in html
    assert 'id="case-erasure-ground"' in html
    assert 'id="request-identifier-options"' in html
    assert "Nothing from the Identity Vault is inserted automatically" in html
    assert "backend.previewCaseRequest(caseItem.id, erasureGround, identifierIds" in javascript
    preview_slot = bridge.split("def previewCaseRequest", 1)[1].split("def approveCaseRequest", 1)[0]
    assert "case_id: int" in preview_slot
    assert "erasure_ground: str" in preview_slot
    assert "identifier_ids: object" in preview_slot
    assert "subject" not in preview_slot
    assert "body" not in preview_slot
    assert "recipient" not in preview_slot
    assert "approved_by_user" not in preview_slot


def test_request_approval_cannot_supply_or_override_outbound_payload_from_javascript():
    html = (ROOT / "ui" / "web" / "index.html").read_text(encoding="utf-8")
    javascript = frontend_javascript()
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert 'id="approve-request-button"' in html
    assert "Approval stores an encrypted, immutable copy" in html
    assert "only after actual transmission" in html
    assert "backend.approveCaseRequest(" in javascript
    approval_call = javascript.split("backend.approveCaseRequest(", 1)[1].split(");", 1)[0]
    assert "context.caseId" in approval_call
    assert "context.erasureGround" in approval_call
    assert "context.identifierIds" in approval_call
    assert "approved" in approval_call
    assert "requestPreviewSubjectNode.value" not in approval_call
    assert "requestPreviewBodyNode.value" not in approval_call

    approval_slot = bridge.split("def approveCaseRequest", 1)[1].split("def handoffApprovedRequest", 1)[0]
    assert "case_id: int" in approval_slot
    assert "erasure_ground: str" in approval_slot
    assert "identifier_ids: object" in approval_slot
    assert "approved_by_user: bool" in approval_slot
    assert "subject" not in approval_slot
    assert "body" not in approval_slot
    assert "recipient" not in approval_slot
    assert "def sendCase" not in bridge
    assert "def dispatch" not in bridge


def test_research_bridge_exposes_semantic_async_action_not_network_primitive():
    javascript = frontend_javascript()
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
