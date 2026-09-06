from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from urllib.parse import urlsplit

from core.domain.investigation import (
    ArtifactKind,
    EvidenceCandidate,
    EvidenceKind,
    EvidenceProvenance,
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?[0-9][0-9 .()\-/]{5,}[0-9])(?!\w)")
_DKIM_DOMAIN_RE = re.compile(r"(?:^|;)\s*d=([^;\s]+)", re.IGNORECASE)
_EMAIL_DOMAIN_RE = re.compile(r"@([^>\s,;]+)")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


class _VisibleHTML(HTMLParser):
    """Read inert text and HTTP links; never execute or fetch HTML content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "head", "template"}:
            self._ignored.append(tag)
        if not self._ignored and tag == "a":
            self.chunks.extend(value for key, value in attrs if key == "href" and value)

    def handle_endtag(self, tag: str) -> None:
        if self._ignored and tag == self._ignored[-1]:
            self._ignored.pop()

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.chunks.append(data)


class ArtifactAnalyzer:
    """Extract bounded, deterministic observations from immutable artifacts."""

    MAX_FINDINGS = 2000

    def analyze(self, kind: ArtifactKind, payload: bytes) -> tuple[EvidenceCandidate, ...]:
        if kind is ArtifactKind.EMAIL:
            findings = self._analyze_email(payload)
        elif kind is ArtifactKind.URL:
            findings = self._analyze_url(payload)
        elif kind in {ArtifactKind.SMS, ArtifactKind.TEXT, ArtifactKind.COMPANY_RESPONSE}:
            findings = self._analyze_text(payload)
        else:
            findings = ()
        result = self._deduplicate(findings)
        if len(result) > self.MAX_FINDINGS:
            raise ValueError(f"Artifact analysis exceeds the {self.MAX_FINDINGS} finding limit; split the input")
        return result

    def _analyze_text(self, payload: bytes) -> tuple[EvidenceCandidate, ...]:
        text = self._decode_text(payload)
        findings: list[EvidenceCandidate] = []
        for index, url in enumerate(self._extract_urls(text)):
            findings.extend(self._url_findings(url, f"text.url[{index}]"))
        for index, phone in enumerate(self._extract_phones(text)):
            findings.append(
                EvidenceCandidate(
                    EvidenceKind.EXTRACTED_FIELD,
                    EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                    phone,
                    f"text.phone[{index}]",
                )
            )
        return tuple(findings)

    def _analyze_url(self, payload: bytes) -> tuple[EvidenceCandidate, ...]:
        value = self._decode_text(payload).strip()
        if not value:
            return ()
        return self._url_findings(value, "url")

    def _analyze_email(self, payload: bytes) -> tuple[EvidenceCandidate, ...]:
        message = BytesParser(policy=policy.default).parsebytes(payload)
        findings: list[EvidenceCandidate] = []

        for header in ("From", "Reply-To", "Return-Path"):
            for index, value in enumerate(message.get_all(header, [])):
                normalized = str(value).strip()
                if not normalized:
                    continue
                findings.append(
                    EvidenceCandidate(
                        EvidenceKind.EXTRACTED_FIELD,
                        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                        normalized,
                        f"email.header.{header.lower()}[{index}]",
                    )
                )
                for domain_index, domain in enumerate(self._extract_email_domains(normalized)):
                    findings.append(
                        EvidenceCandidate(
                            EvidenceKind.EXTRACTED_FIELD,
                            EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                            domain,
                            f"email.header.{header.lower()}[{index}].domain[{domain_index}]",
                        )
                    )

        for index, value in enumerate(message.get_all("DKIM-Signature", [])):
            match = _DKIM_DOMAIN_RE.search(str(value))
            if match:
                findings.append(
                    EvidenceCandidate(
                        EvidenceKind.EXTRACTED_FIELD,
                        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                        self._normalize_host(match.group(1)),
                        f"email.header.dkim-signature[{index}].d",
                    )
                )

        for index, value in enumerate(message.get_all("Message-ID", [])):
            for domain_index, domain in enumerate(self._extract_email_domains(str(value))):
                findings.append(
                    EvidenceCandidate(
                        EvidenceKind.EXTRACTED_FIELD,
                        EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                        domain,
                        f"email.header.message-id[{index}].domain[{domain_index}]",
                    )
                )

        for part_index, part in enumerate(self._email_body_parts(message)):
            media_type = part.get_content_type()
            if media_type not in {"text/plain", "text/html"}:
                continue
            try:
                body = part.get_content()
            except (LookupError, UnicodeError):
                continue
            if media_type == "text/html":
                parser = _VisibleHTML()
                parser.feed(body)
                body = "\n".join(parser.chunks)
            for index, url in enumerate(self._extract_urls(body)):
                findings.extend(self._url_findings(url, f"email.body.part[{part_index}].url[{index}]"))
        return tuple(findings)

    @classmethod
    def _email_body_parts(cls, message):
        if message.get_content_disposition() == "attachment":
            return
        if message.is_multipart():
            for part in message.iter_parts():
                yield from cls._email_body_parts(part)
        else:
            yield message

    @staticmethod
    def _decode_text(payload: bytes) -> str:
        return payload.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_urls(text: str) -> tuple[str, ...]:
        return tuple(
            match.group(0).rstrip(_TRAILING_URL_PUNCTUATION) for match in _URL_RE.finditer(text)
        )

    @staticmethod
    def _extract_phones(text: str) -> tuple[str, ...]:
        values: list[str] = []
        for match in _PHONE_RE.finditer(text):
            raw = match.group(0).strip()
            digits = re.sub(r"\D", "", raw)
            if 9 <= len(digits) <= 15:
                values.append(raw)
        return tuple(values)

    @classmethod
    def _url_findings(cls, value: str, locator: str) -> tuple[EvidenceCandidate, ...]:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ()
        normalized_host = cls._normalize_host(parsed.hostname)
        normalized_url = parsed.geturl()
        return (
            EvidenceCandidate(
                EvidenceKind.EXTRACTED_FIELD,
                EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                normalized_url,
                locator,
            ),
            EvidenceCandidate(
                EvidenceKind.EXTRACTED_FIELD,
                EvidenceProvenance.DETERMINISTIC_ANALYSIS,
                normalized_host,
                f"{locator}.host",
            ),
        )

    @staticmethod
    def _normalize_host(host: str) -> str:
        return host.strip().strip(".").lower()

    @classmethod
    def _extract_email_domains(cls, value: str) -> tuple[str, ...]:
        return tuple(
            cls._normalize_host(match.group(1).rstrip(">")) for match in _EMAIL_DOMAIN_RE.finditer(value)
        )

    @staticmethod
    def _deduplicate(findings: tuple[EvidenceCandidate, ...]) -> tuple[EvidenceCandidate, ...]:
        seen: set[tuple[str, str, str, str]] = set()
        result: list[EvidenceCandidate] = []
        for finding in findings:
            key = (
                finding.kind.value,
                finding.provenance.value,
                finding.value,
                finding.source_locator,
            )
            if key not in seen:
                seen.add(key)
                result.append(finding)
        return tuple(result)
