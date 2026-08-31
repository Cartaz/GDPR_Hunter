from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit


class InferenceLocation(StrEnum):
    LOCAL_PROCESS = "LOCAL_PROCESS"
    USER_APPROVED_LAN = "USER_APPROVED_LAN"
    REMOTE = "REMOTE"


_LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


@dataclass(frozen=True, slots=True)
class InferenceEndpoint:
    url: str
    location: InferenceLocation

    def validate(self) -> SplitResult:
        parsed = urlsplit(self.url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Inference endpoint must be an absolute HTTP(S) URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Inference endpoint must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("Inference endpoint must not contain query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("Inference endpoint must not include an API path")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Inference endpoint contains an invalid port") from exc

        hostname = parsed.hostname.rstrip(".").lower()
        if self.location is InferenceLocation.LOCAL_PROCESS:
            if hostname not in {"127.0.0.1", "::1", "localhost"}:
                raise ValueError("LOCAL_PROCESS inference must use a loopback endpoint")
        elif self.location is InferenceLocation.USER_APPROVED_LAN:
            self._require_verifiable_lan_address(hostname)
        elif self.location is InferenceLocation.REMOTE:
            if scheme != "https":
                raise ValueError("REMOTE inference must use HTTPS")
            self._reject_non_remote_literal(hostname)
        else:  # pragma: no cover - enum construction prevents this in normal use
            raise ValueError("Unsupported inference location")
        return parsed

    @staticmethod
    def _require_verifiable_lan_address(hostname: str) -> None:
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise ValueError(
                "USER_APPROVED_LAN inference must use a literal private LAN address"
            ) from exc
        if not any(address in network for network in _LAN_NETWORKS):
            raise ValueError("USER_APPROVED_LAN inference must use a private LAN address")

    @staticmethod
    def _reject_non_remote_literal(hostname: str) -> None:
        if hostname == "localhost":
            raise ValueError("REMOTE inference must not use a local endpoint")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return
        if not address.is_global:
            raise ValueError("REMOTE inference must not use a non-public IP address")
