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
