from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit


class NetworkPolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedPublicUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    request_target: str
    addresses: tuple[str, ...]


Resolver = Callable[[str, int, int, int], list[tuple]]


class NetworkPolicy:
    """Validate outbound research destinations and resolve only public addresses."""

    ALLOWED_SCHEMES = frozenset({"http", "https"})
    ALLOWED_PORTS = frozenset({80, 443})

    def __init__(self, resolver: Resolver | None = None) -> None:
        self._resolver = resolver or socket.getaddrinfo

    def validate_public_url(self, url: str) -> ValidatedPublicUrl:
        normalized = url.strip()
        if not normalized or "\\" in normalized:
            raise NetworkPolicyError("Research URL is malformed")

        parsed = urlsplit(normalized)
        self._validate_parsed_url(parsed)
        hostname = self._normalize_hostname(parsed.hostname)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        if port not in self.ALLOWED_PORTS:
            raise NetworkPolicyError("Research URL uses a disallowed port")

        addresses = self.resolve_public_host(hostname, port)
        request_target = parsed.path or "/"
        if parsed.query:
            request_target += f"?{parsed.query}"
        return ValidatedPublicUrl(
            url=normalized,
            scheme=parsed.scheme.lower(),
            hostname=hostname,
            port=port,
            request_target=request_target,
            addresses=addresses,
        )

    def resolve_public_host(self, hostname: str, port: int = 443) -> tuple[str, ...]:
        normalized = self._normalize_hostname(hostname)
        try:
            literal = ipaddress.ip_address(normalized)
        except ValueError:
            literal = None
        if literal is not None:
            self._require_public_ip(literal)
            return (literal.compressed,)

        try:
            rows = self._resolver(normalized, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        except OSError as exc:
            raise NetworkPolicyError("Research host could not be resolved") from exc

        addresses: list[str] = []
        for row in rows:
            sockaddr = row[4]
            if not sockaddr:
                continue
            address = ipaddress.ip_address(sockaddr[0])
            self._require_public_ip(address)
            compressed = address.compressed
            if compressed not in addresses:
                addresses.append(compressed)
        if not addresses:
            raise NetworkPolicyError("Research host has no usable public addresses")
        return tuple(addresses)

    @classmethod
    def _validate_parsed_url(cls, parsed: SplitResult) -> None:
        if parsed.scheme.lower() not in cls.ALLOWED_SCHEMES:
            raise NetworkPolicyError("Only HTTP and HTTPS research URLs are allowed")
        if parsed.hostname is None:
            raise NetworkPolicyError("Research URL requires a hostname")
        if parsed.username is not None or parsed.password is not None:
            raise NetworkPolicyError("Embedded URL credentials are not allowed")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise NetworkPolicyError("Research URL contains an invalid port") from exc

    @staticmethod
    def _normalize_hostname(hostname: str | None) -> str:
        if hostname is None:
            raise NetworkPolicyError("Research hostname is required")
        value = hostname.strip().rstrip(".").lower()
        if not value or any(character.isspace() for character in value):
            raise NetworkPolicyError("Research hostname is malformed")
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise NetworkPolicyError("Research hostname is malformed") from exc

    @staticmethod
    def _require_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if not address.is_global:
            raise NetworkPolicyError("Research destination resolves to a non-public address")
