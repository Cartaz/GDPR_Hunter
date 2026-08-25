from __future__ import annotations

import re
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from urllib.parse import urlsplit

from core.domain.investigation import ArtifactKind, EvidenceKind, EvidenceProvenance

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?[0-9][0-9 .()\-/]{5,}[0-9])(?!\w)")
_DKIM_DOMAIN_RE = re.compile(r"(?:^|;)\s*d=([^;\s]+)", re.IGNORECASE)
_EMAIL_DOMAIN_RE = re.compile(r"@([^>\s,;]+)")
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}"


@dataclass(frozen=True, slots=True)
class EvidenceCandidate:
    kind: EvidenceKind
    provenance: EvidenceProvenance
    value: str
    source_locator: str


class ArtifactAnalyzer:
    """Extract bounded, deterministic observations from immutable artifacts."""

    def analyze(self, kind: ArtifactKind, payload: bytes) -> tuple[EvidenceCandidate, ...]:
        if kind is ArtifactKind.EMAIL:
            findings = self._analyze_email(payload)
        elif kind is ArtifactKind.URL:
            findings = self._analyze_url(payload)
        elif kind in {ArtifactKind.SMS, ArtifactKind.TEXT, ArtifactKind.COMPANY_RESPONSE}:
            findings = self._analyze_text(payload)
        else:
            findings = ()
        return self._deduplicate(findings)

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

        body = self._email_text_body(message)
        for index, url in enumerate(self._extract_urls(body)):
            findings.extend(self._url_findings(url, f"email.body.url[{index}]"))
        return tuple(findings)

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
    def _email_text_body(message) -> str:
        if message.is_multipart():
            chunks: list[str] = []
            for part in message.walk():
                if (
                    part.get_content_type() != "text/plain"
                    or part.get_content_disposition() == "attachment"
                ):
                    continue
                try:
                    chunks.append(part.get_content())
                except (LookupError, UnicodeError):
                    continue
            return "\n".join(chunks)
        if message.get_content_type() == "text/plain":
            try:
                return message.get_content()
            except (LookupError, UnicodeError):
                return ""
        return ""

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
