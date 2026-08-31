from __future__ import annotations

from PySide6.QtCore import QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices


def build_mailto_url(recipient_email: str, subject: str, body: str) -> QUrl:
    """Build a mailto URL from an already-approved message without changing its content."""
    url = QUrl()
    url.setScheme("mailto")
    url.setPath(recipient_email)
    query = QUrlQuery()
    query.addQueryItem("subject", subject)
    query.addQueryItem("body", body)
    url.setQuery(query)
    return url


class SystemMailClientHandoff:
    """Native adapter that asks the operating system to open its default mail client."""

    def open_message(self, recipient_email: str, subject: str, body: str) -> bool:
        return bool(QDesktopServices.openUrl(build_mailto_url(recipient_email, subject, body)))
