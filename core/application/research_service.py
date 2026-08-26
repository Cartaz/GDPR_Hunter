from __future__ import annotations

import http.client
import json
import socket
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote, urljoin

from core.application.network_policy import (
    NetworkPolicy,
    NetworkPolicyError,
    ValidatedPublicUrl,
)


class ResearchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RedirectHop:
    source_url: str
    status: int
    destination_url: str


@dataclass(frozen=True, slots=True)
class ResearchDocument:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    redirects: tuple[RedirectHop, ...]


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes


Transport = Callable[[ValidatedPublicUrl, int, int], TransportResponse]


class ResearchService:
    """Perform bounded public-network research behind NetworkPolicy."""

    MAX_DOCUMENT_BYTES = 1024 * 1024
    MAX_REDIRECTS = 5
    TIMEOUT_SECONDS = 8
    ALLOWED_CONTENT_TYPES = frozenset(
        {
            "text/html",
            "text/plain",
            "application/xhtml+xml",
            "application/json",
            "application/rdap+json",
        }
    )
    REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
    IANA_RDAP_BOOTSTRAP = "https://data.iana.org/rdap/dns.json"

    def __init__(
        self,
        network_policy: NetworkPolicy,
        transport: Transport | None = None,
    ) -> None:
        self._network_policy = network_policy
        self._transport = transport or self._request_pinned

    def fetch_public_document(self, url: str) -> ResearchDocument:
        current = url.strip()
        if not current:
            raise ResearchError("Research URL is required")
        redirects: list[RedirectHop] = []
        requested = current

        for _ in range(self.MAX_REDIRECTS + 1):
            try:
                validated = self._network_policy.validate_public_url(current)
            except NetworkPolicyError as exc:
                raise ResearchError(str(exc)) from exc

            response = self._transport(validated, self.TIMEOUT_SECONDS, self.MAX_DOCUMENT_BYTES)
            if len(response.body) > self.MAX_DOCUMENT_BYTES:
                raise ResearchError("Research response exceeds size limit")
            if response.status in self.REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise ResearchError("Redirect response is missing Location header")
                if len(redirects) >= self.MAX_REDIRECTS:
                    raise ResearchError("Research redirect limit exceeded")
                destination = urljoin(current, location)
                redirects.append(RedirectHop(current, response.status, destination))
                current = destination
                continue

            if not 200 <= response.status < 300:
                raise ResearchError(f"Research request failed with HTTP {response.status}")
            content_type = self._normalize_content_type(response.headers.get("content-type", ""))
            if content_type not in self.ALLOWED_CONTENT_TYPES:
                raise ResearchError("Research response content type is not allowed")
            return ResearchDocument(
                requested_url=requested,
                final_url=current,
                status=response.status,
                content_type=content_type,
                body=response.body,
                redirects=tuple(redirects),
            )

        raise ResearchError("Research redirect limit exceeded")

    def resolve_public_dns(self, hostname: str) -> tuple[str, ...]:
        try:
            return self._network_policy.resolve_public_host(hostname)
        except NetworkPolicyError as exc:
            raise ResearchError(str(exc)) from exc

    def lookup_domain_rdap(self, domain: str) -> ResearchDocument:
        normalized = domain.strip().rstrip(".").lower()
        if not normalized or "." not in normalized:
            raise ResearchError("RDAP lookup requires a fully qualified domain")
        tld = normalized.rsplit(".", 1)[1]

        bootstrap = self.fetch_public_document(self.IANA_RDAP_BOOTSTRAP)
        try:
            payload = json.loads(bootstrap.body.decode("utf-8"))
            services = payload["services"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ResearchError("IANA RDAP bootstrap response is malformed") from exc

        base_url = self._rdap_base_for_tld(services, tld)
        return self.fetch_public_document(
            urljoin(base_url.rstrip("/") + "/", f"domain/{quote(normalized)}")
        )

    @staticmethod
    def _rdap_base_for_tld(services: object, tld: str) -> str:
        if not isinstance(services, list):
            raise ResearchError("IANA RDAP bootstrap response is malformed")
        for entry in services:
            if not isinstance(entry, list) or len(entry) != 2:
                continue
            tlds, urls = entry
            if not isinstance(tlds, list) or not isinstance(urls, list):
                continue
            if tld in {str(item).lower() for item in tlds} and urls:
                base = urls[0]
                if isinstance(base, str) and base.startswith("https://"):
                    return base
        raise ResearchError("No RDAP service is registered for this domain")

    @staticmethod
    def _normalize_content_type(value: str) -> str:
        return value.split(";", 1)[0].strip().lower()

    @staticmethod
    def _request_pinned(
        validated: ValidatedPublicUrl,
        timeout_seconds: int,
        max_bytes: int,
    ) -> TransportResponse:
        last_error: OSError | http.client.HTTPException | None = None
        for address in validated.addresses:
            raw_socket: socket.socket | None = None
            wrapped_socket: socket.socket | None = None
            try:
                raw_socket = socket.create_connection(
                    (address, validated.port), timeout=timeout_seconds
                )
                active_socket: socket.socket
                if validated.scheme == "https":
                    context = ssl.create_default_context()
                    wrapped_socket = context.wrap_socket(
                        raw_socket, server_hostname=validated.hostname
                    )
                    active_socket = wrapped_socket
                else:
                    active_socket = raw_socket

                request = (
                    f"GET {validated.request_target} HTTP/1.1\r\n"
                    f"Host: {validated.hostname}\r\n"
                    "User-Agent: GDPR-Hunter/0.1\r\n"
                    "Accept: text/html,text/plain,application/json,application/rdap+json;q=0.9,*/*;q=0.1\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                active_socket.sendall(request)
                response = http.client.HTTPResponse(active_socket)
                response.begin()
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ResearchError("Research response exceeds size limit")
                headers = {name.lower(): value for name, value in response.getheaders()}
                return TransportResponse(response.status, headers, body)
            except ResearchError:
                raise
            except (OSError, http.client.HTTPException) as exc:
                last_error = exc
            finally:
                if wrapped_socket is not None:
                    wrapped_socket.close()
                elif raw_socket is not None:
                    raw_socket.close()
        raise ResearchError("Research destination could not be reached") from last_error
