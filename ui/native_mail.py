from __future__ import annotations

from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

_MAILBOX_SAFE = "@!$&'()*+,;=:-._~"


def _normalize_body_line_endings(body: str) -> str:
    """Normalize composed-message line breaks to the CRLF required by RFC 6068."""
    return body.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")


def build_mailto_url(recipient_email: str, subject: str, body: str) -> QUrl:
    """Build an RFC 6068 mailto URI from an already-approved message."""
    recipient = quote(recipient_email, safe=_MAILBOX_SAFE)
    encoded_subject = quote(subject, safe="")
    encoded_body = quote(_normalize_body_line_endings(body), safe="")
    encoded = f"mailto:{recipient}?subject={encoded_subject}&body={encoded_body}"
    return QUrl.fromEncoded(encoded.encode("ascii"))


class SystemMailClientHandoff:
    """Native adapter that asks the operating system to open its default mail client."""

    def open_message(self, recipient_email: str, subject: str, body: str) -> bool:
        return bool(QDesktopServices.openUrl(build_mailto_url(recipient_email, subject, body)))
