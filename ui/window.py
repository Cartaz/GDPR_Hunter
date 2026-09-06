from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from ui.bridge import Bridge


def is_allowed_local_url(url: QUrl, allowed_root: Path) -> bool:
    if not url.isLocalFile():
        return False
    try:
        candidate = Path(url.toLocalFile()).resolve()
        return candidate.is_relative_to(allowed_root.resolve())
    except (OSError, RuntimeError):
        return False


class LocalOnlyPage(QWebEnginePage):
    def __init__(self, allowed_root: Path, parent=None) -> None:
        super().__init__(parent)
        self._allowed_root = allowed_root.resolve()

    def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.scheme() in {"qrc", "about"}:
            return True
        if url.isLocalFile():
            return is_allowed_local_url(url, self._allowed_root)
        if is_main_frame and url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)
        return False


class MainWindow(QMainWindow):
    geometrySaved = Signal(int, int)

    def __init__(self, bridge: Bridge, web_root: Path, width: int, height: int, *, runners=()) -> None:
        super().__init__()
        self.setWindowTitle("GDPR Hunter")
        self.setMinimumSize(1100, 720)
        self.resize(width, height)
        self._runners = tuple(runners)
        self._closing = False
        self._close_timer = QTimer(self)
        self._close_timer.setInterval(50)
        self._close_timer.timeout.connect(self._finish_close)

        resolved_web_root = web_root.resolve()
        self._view = QWebEngineView(self)
        self._page = LocalOnlyPage(resolved_web_root, self._view)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self._channel = QWebChannel(self._page)
        self._channel.registerObject("backend", bridge)
        self._page.setWebChannel(self._channel)

        index = (resolved_web_root / "index.html").resolve()
        self._view.setUrl(QUrl.fromLocalFile(str(index)))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if any(runner.is_busy for runner in self._runners):
            event.ignore()
            self._closing = True
            self._view.setEnabled(False)
            self.setWindowTitle("GDPR Hunter — cancelling background work…")
            for runner in self._runners:
                runner.request_stop()
            self._close_timer.start()
            return
        self.geometrySaved.emit(self.width(), self.height())
        super().closeEvent(event)

    def _finish_close(self) -> None:
        if self._closing and not any(runner.is_busy for runner in self._runners):
            self._close_timer.stop()
            self.close()
