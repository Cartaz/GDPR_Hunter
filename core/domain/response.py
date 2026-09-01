from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ResponseChannel(StrEnum):
    EMAIL = "EMAIL"
    POSTAL_MAIL = "POSTAL_MAIL"
    WEB_PORTAL = "WEB_PORTAL"
    PHONE = "PHONE"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class CaseResponse:
    id: int | None
    case_id: int
    channel: ResponseChannel
    received_on: date
    sender: str | None
    subject: str | None
    body: str
    recorded_at: str


@dataclass(frozen=True, slots=True)
class CaseResponseSummary:
    id: int
    case_id: int
    channel: ResponseChannel
    received_on: date
    recorded_at: str
