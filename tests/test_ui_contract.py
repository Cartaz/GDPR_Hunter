from __future__ import annotations

from pathlib import Path

from ui.window import LocalOnlyPage, MainWindow


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
