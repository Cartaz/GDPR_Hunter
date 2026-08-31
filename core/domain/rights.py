from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class CaseRight(StrEnum):
    UNSPECIFIED = "UNSPECIFIED"
    ACCESS_PROVENANCE = "ACCESS_PROVENANCE"
    ERASURE = "ERASURE"
    DIRECT_MARKETING_OBJECTION = "DIRECT_MARKETING_OBJECTION"


class ErasureGround(StrEnum):
    NO_LONGER_NECESSARY = "NO_LONGER_NECESSARY"
    CONSENT_WITHDRAWN = "CONSENT_WITHDRAWN"
    OBJECTION = "OBJECTION"
    UNLAWFUL_PROCESSING = "UNLAWFUL_PROCESSING"
    LEGAL_OBLIGATION = "LEGAL_OBLIGATION"
    CHILD_INFORMATION_SOCIETY_SERVICES = "CHILD_INFORMATION_SOCIETY_SERVICES"


@dataclass(frozen=True, slots=True)
class ErasureGroundPolicy:
    ground: ErasureGround
    article: str
    title: str
    summary: str


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

    _POLICIES: ClassVar[dict[CaseRight, RightPolicy]] = {
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

    _ERASURE_GROUNDS: ClassVar[dict[ErasureGround, ErasureGroundPolicy]] = {
        ErasureGround.NO_LONGER_NECESSARY: ErasureGroundPolicy(
            ErasureGround.NO_LONGER_NECESSARY,
            "Article 17(1)(a)",
            "No longer necessary",
            "The personal data are no longer necessary for the purposes for which they were collected or otherwise processed.",
        ),
        ErasureGround.CONSENT_WITHDRAWN: ErasureGroundPolicy(
            ErasureGround.CONSENT_WITHDRAWN,
            "Article 17(1)(b)",
            "Consent withdrawn",
            "Consent is withdrawn and no other legal ground for the processing applies.",
        ),
        ErasureGround.OBJECTION: ErasureGroundPolicy(
            ErasureGround.OBJECTION,
            "Article 17(1)(c)",
            "Objection to processing",
            "An Article 21 objection applies and the conditions for erasure under Article 17(1)(c) are met.",
        ),
        ErasureGround.UNLAWFUL_PROCESSING: ErasureGroundPolicy(
            ErasureGround.UNLAWFUL_PROCESSING,
            "Article 17(1)(d)",
            "Unlawful processing",
            "The personal data have been unlawfully processed.",
        ),
        ErasureGround.LEGAL_OBLIGATION: ErasureGroundPolicy(
            ErasureGround.LEGAL_OBLIGATION,
            "Article 17(1)(e)",
            "Legal obligation to erase",
            "The personal data must be erased to comply with an applicable Union or Member State legal obligation.",
        ),
        ErasureGround.CHILD_INFORMATION_SOCIETY_SERVICES: ErasureGroundPolicy(
            ErasureGround.CHILD_INFORMATION_SOCIETY_SERVICES,
            "Article 17(1)(f)",
            "Child information-society services",
            "The personal data were collected in relation to the offer of information-society services referred to in Article 8(1).",
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

    def get_erasure_ground(self, ground: ErasureGround) -> ErasureGroundPolicy:
        try:
            return self._ERASURE_GROUNDS[ground]
        except KeyError as exc:
            raise ValueError("Unsupported Article 17 erasure ground") from exc

    def erasure_grounds(self) -> tuple[ErasureGroundPolicy, ...]:
        return tuple(self._ERASURE_GROUNDS.values())
