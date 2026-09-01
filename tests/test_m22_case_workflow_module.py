from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ui.bridge import Bridge
from ui.research_runner import ResearchRunner
from ui.window import MainWindow

ROOT = Path(__file__).resolve().parents[1]


class SmokeController:
    def get_bootstrap_state(self) -> dict[str, object]:
        return {
            "identity": {
                "displayName": None,
                "identifierCount": 0,
                "identifiers": [],
            },
            "targets": [],
            "rights": [],
            "erasureGrounds": [],
            "cases": [],
            "approvedRequests": [],
            "deliveryEvents": [],
            "submissionBindings": [],
            "investigations": [],
            "milestone": "M22 module smoke",
            "features": {},
        }


def wait_for_load(window: MainWindow, timeout_ms: int = 10_000) -> bool:
    loop = QEventLoop()
    loaded = {"ok": False}

    def finish(ok: bool) -> None:
        loaded["ok"] = ok
        loop.quit()

    window._view.loadFinished.connect(finish)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return loaded["ok"]


def read_javascript(window: MainWindow, expression: str, timeout_ms: int = 5_000):
    loop = QEventLoop()
    result: dict[str, object] = {}

    def finish(value: object) -> None:
        result["value"] = value
        loop.quit()

    window._page.runJavaScript(expression, finish)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return result.get("value")


def test_local_es_module_loads_through_production_webengine_stack() -> None:
    app = QApplication.instance() or QApplication([])
    controller = SmokeController()
    bridge = Bridge(controller, ResearchRunner(controller))  # type: ignore[arg-type]
    window = MainWindow(bridge, ROOT / "ui" / "web", 1200, 800)

    try:
        assert wait_for_load(window)
        assert read_javascript(window, 'document.getElementById("milestone").textContent') == (
            "M22 module smoke"
        )
        assert read_javascript(window, 'document.getElementById("case-list") !== null') is True
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
