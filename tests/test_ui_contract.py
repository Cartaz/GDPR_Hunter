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
    assert "MODEL_INFERENCE" not in javascript
    assert "addUserEvidence" in bridge
    assert "createUserClaim" in bridge
    assert "def addEvidence" not in bridge
    assert "def createClaim" not in bridge


def test_blocking_research_is_not_exposed_through_qwebchannel():
    javascript = (ROOT / "ui" / "web" / "js" / "app.js").read_text(encoding="utf-8")
    bridge = (ROOT / "ui" / "bridge.py").read_text(encoding="utf-8")

    assert "researchArtifact" not in javascript
    assert "researchArtifact" not in bridge
    assert "fetchUrl" not in bridge


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
