from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit


class InferenceLocation(StrEnum):
    LOCAL_PROCESS = "LOCAL_PROCESS"
    USER_APPROVED_LAN = "USER_APPROVED_LAN"
    REMOTE = "REMOTE"


@dataclass(frozen=True, slots=True)
class InferenceEndpoint:
    url: str
    location: InferenceLocation

    def validate(self) -> SplitResult:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Inference endpoint must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Inference endpoint must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Inference endpoint must not contain query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("Inference endpoint must not include an API path")
        if self.location is InferenceLocation.LOCAL_PROCESS and parsed.hostname not in {
            "127.0.0.1",
            "::1",
            "localhost",
        }:
            raise ValueError("LOCAL_PROCESS inference must use a loopback endpoint")
        return parsed
