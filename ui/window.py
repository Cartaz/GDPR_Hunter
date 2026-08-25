from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from ui.bridge import Bridge


class LocalOnlyPage(QWebEnginePage):
    def acceptNavigationRequest(self, url: QUrl, navigation_type, is_main_frame: bool) -> bool:  # type: ignore[override]
        if url.isLocalFile() or url.scheme() in {"qrc", "about"}:
            return True
        if is_main_frame and url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)
        return False


class MainWindow(QMainWindow):
    def __init__(self, bridge: Bridge, web_root: Path, width: int, height: int) -> None:
        super().__init__()
        self.setWindowTitle("GDPR Hunter")
        self.setMinimumSize(1100, 720)
        self.resize(width, height)

        self._view = QWebEngineView(self)
        self._page = LocalOnlyPage(self._view)
        self._view.setPage(self._page)
        self.setCentralWidget(self._view)

        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        self._channel = QWebChannel(self._page)
        self._channel.registerObject("backend", bridge)
        self._page.setWebChannel(self._channel)

        index = (web_root / "index.html").resolve()
        self._view.setUrl(QUrl.fromLocalFile(str(index)))
