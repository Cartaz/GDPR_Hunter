from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.bridge import Bridge
from ui.research_runner import ResearchRunner
from ui.window import LocalOnlyPage


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


def wait_for_load(page: LocalOnlyPage, timeout_ms: int = 10_000) -> bool:
    loop = QEventLoop()
    loaded = {"ok": False}

    def finish(ok: bool) -> None:
        loaded["ok"] = ok
        loop.quit()

    page.loadFinished.connect(finish)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return loaded["ok"]


def wait_for_javascript_value(
    page: LocalOnlyPage,
    expression: str,
    expected: object,
    timeout_seconds: float = 5.0,
) -> bool:
    loop = QEventLoop()
    matched = {"ok": False}
    deadline = time.monotonic() + timeout_seconds

    def evaluate(value: object) -> None:
        if value == expected:
            matched["ok"] = True
            loop.quit()
            return
        if time.monotonic() >= deadline:
            loop.quit()
            return
        QTimer.singleShot(50, check)

    def check() -> None:
        page.runJavaScript(expression, evaluate)

    check()
    QTimer.singleShot(int(timeout_seconds * 1000) + 100, loop.quit)
    loop.exec()
    return matched["ok"]


def main() -> int:
    app = QApplication([])
    controller = SmokeController()
    bridge = Bridge(controller, ResearchRunner(controller))  # type: ignore[arg-type]
    web_root = (ROOT / "ui" / "web").resolve()
    page = LocalOnlyPage(web_root)
    page.settings().setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
        False,
    )
    page.settings().setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
        True,
    )
    channel = QWebChannel(page)
    channel.registerObject("backend", bridge)
    page.setWebChannel(channel)
    page.setUrl(QUrl.fromLocalFile(str(web_root / "index.html")))

    try:
        if not wait_for_load(page):
            print("WebEngine page load did not finish successfully", file=sys.stderr)
            return 1
        if not wait_for_javascript_value(
            page,
            'document.getElementById("milestone").textContent',
            "M22 module smoke",
        ):
            print("Local ES module did not complete QWebChannel bootstrap", file=sys.stderr)
            return 2
        if not wait_for_javascript_value(
            page,
            'document.getElementById("case-list") !== null',
            True,
        ):
            print("Case workflow DOM was not available", file=sys.stderr)
            return 3
        return 0
    finally:
        page.setWebChannel(None)
        page.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
