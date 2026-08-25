from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CaseRight(StrEnum):
    UNSPECIFIED = "UNSPECIFIED"
    ACCESS_PROVENANCE = "ACCESS_PROVENANCE"
    ERASURE = "ERASURE"
    DIRECT_MARKETING_OBJECTION = "DIRECT_MARKETING_OBJECTION"


@dataclass(frozen=True, slots=True)
class RightPolicy:
    right: CaseRight
    article: str
    title: str
    summary: str
    request_points: tuple[str, ...]
    requires_case_specific_ground: bool = False


class RightsPolicy:
    """Deterministic policy for the GDPR rights supported by the application."""

    _POLICIES: dict[CaseRight, RightPolicy] = {
        CaseRight.ACCESS_PROVENANCE: RightPolicy(
            right=CaseRight.ACCESS_PROVENANCE,
            article="Article 15",
            title="Access and provenance",
            summary=(
                "Request access to personal data and, where the data were not collected from the data "
                "subject, available information about their source."
            ),
            request_points=(
                "confirmation whether personal data are processed",
                "access to the personal data",
                "purposes and categories of processing",
                "recipients or categories of recipients",
                "available information about the source when data were not collected from the data subject",
            ),
        ),
        CaseRight.ERASURE: RightPolicy(
            right=CaseRight.ERASURE,
            article="Article 17",
            title="Erasure",
            summary=(
                "Request erasure where at least one Article 17 ground applies; statutory exceptions may "
                "permit continued processing."
            ),
            request_points=(
                "identify the personal data to erase",
                "record the applicable erasure ground",
                "request confirmation of action taken",
            ),
            requires_case_specific_ground=True,
        ),
        CaseRight.DIRECT_MARKETING_OBJECTION: RightPolicy(
            right=CaseRight.DIRECT_MARKETING_OBJECTION,
            article="Article 21(2)-(3)",
            title="Direct marketing objection",
            summary=(
                "Object to processing for direct marketing; after such an objection, the personal data "
                "must no longer be processed for those purposes."
            ),
            request_points=(
                "object to processing for direct marketing",
                "include related profiling where applicable",
                "request confirmation that direct-marketing processing has stopped",
            ),
        ),
    }

    def get(self, right: CaseRight) -> RightPolicy:
        if right is CaseRight.UNSPECIFIED:
            raise ValueError("Legacy case has no GDPR right assigned")
        try:
            return self._POLICIES[right]
        except KeyError as exc:
            raise ValueError("Unsupported GDPR right") from exc

    def supported(self) -> tuple[RightPolicy, ...]:
        return tuple(self._POLICIES.values())
