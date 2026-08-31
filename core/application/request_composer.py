from __future__ import annotations

from dataclasses import dataclass

from core.domain.case import Case
from core.domain.identity import Identity
from core.domain.rights import CaseRight, RightsPolicy
from core.domain.target import Target


@dataclass(frozen=True, slots=True)
class RequestPreview:
    case_id: int
    recipient_name: str
    recipient_email: str | None
    subject: str
    body: str
    legal_basis: str


class RequestComposer:
    """Compose deterministic GDPR request text from canonical application state."""

    def __init__(self, rights_policy: RightsPolicy) -> None:
        self._rights_policy = rights_policy

    def compose(self, case: Case, identity: Identity, target: Target) -> RequestPreview:
        if case.id is None:
            raise RuntimeError("Persisted case has no id")
        display_name = identity.display_name.strip() if identity.display_name else ""
        if not display_name:
            raise ValueError("Set a display name before composing a GDPR request")
        policy = self._rights_policy.get(case.right)

        if case.right is CaseRight.ACCESS_PROVENANCE:
            subject = f"GDPR Article 15 access request — {display_name}"
            body = self._access_body(display_name, target.name)
        elif case.right is CaseRight.ERASURE:
            if case.erasure_ground is None:
                raise ValueError(
                    "This erasure case has no Article 17 ground; recreate it with a specific erasure ground"
                )
            ground = self._rights_policy.get_erasure_ground(case.erasure_ground)
            subject = f"GDPR Article 17 erasure request — {display_name}"
            body = self._erasure_body(
                display_name,
                target.name,
                ground.article,
                ground.summary,
            )
        elif case.right is CaseRight.DIRECT_MARKETING_OBJECTION:
            subject = f"GDPR Article 21 direct marketing objection — {display_name}"
            body = self._direct_marketing_body(display_name, target.name)
        else:
            raise ValueError("Legacy case has no supported GDPR request composition")

        return RequestPreview(
            case_id=case.id,
            recipient_name=target.name,
            recipient_email=target.privacy_email,
            subject=subject,
            body=body,
            legal_basis=policy.article,
        )

    @staticmethod
    def _access_body(display_name: str, target_name: str) -> str:
        return "\n".join(
            (
                f"Dear {target_name} Privacy Team,",
                "",
                f"My name is {display_name}. I am exercising my right of access under Article 15 GDPR.",
                "",
                "Please confirm whether you process personal data concerning me. If you do, please provide:",
                "- a copy of the personal data undergoing processing;",
                "- the purposes of the processing and the categories of personal data concerned;",
                "- the recipients or categories of recipients, including relevant third-country or international-organisation recipients;",
                "- the envisaged retention period, or the criteria used to determine it;",
                "- information about my rights to rectification, erasure, restriction and objection, and my right to lodge a complaint with a supervisory authority;",
                "- where the data were not collected from me, any available information about their source;",
                "- where applicable, meaningful information about automated decision-making, including relevant profiling, its logic, significance and envisaged consequences;",
                "- where applicable, information about appropriate safeguards for transfers to a third country or international organisation.",
                "",
                "Please provide the response and copy in a commonly used electronic form where applicable.",
                "",
                RequestComposer._common_closing(display_name),
            )
        )

    @staticmethod
    def _erasure_body(
        display_name: str,
        target_name: str,
        ground_article: str,
        ground_summary: str,
    ) -> str:
        return "\n".join(
            (
                f"Dear {target_name} Privacy Team,",
                "",
                f"My name is {display_name}. I am exercising my right to erasure under Article 17 GDPR.",
                "",
                f"The ground I rely on is {ground_article}: {ground_summary}",
                "",
                "Please erase the personal data concerning me without undue delay where the conditions of Article 17 are met and confirm the action taken.",
                "If you rely on an exception under Article 17(3), please identify the applicable legal basis and explain why it applies to the processing concerned.",
                "Where Article 19 applies, please also take the required steps regarding recipients of the data.",
                "",
                RequestComposer._common_closing(display_name),
            )
        )

    @staticmethod
    def _direct_marketing_body(display_name: str, target_name: str) -> str:
        return "\n".join(
            (
                f"Dear {target_name} Privacy Team,",
                "",
                f"My name is {display_name}. Pursuant to Article 21(2) GDPR, I object to the processing of personal data concerning me for direct marketing purposes, including profiling to the extent that it is related to such direct marketing.",
                "",
                "Under Article 21(3), please stop processing my personal data for those direct-marketing purposes and confirm that this objection has been recorded and applied.",
                "",
                RequestComposer._common_closing(display_name),
            )
        )

    @staticmethod
    def _common_closing(display_name: str) -> str:
        return "\n".join(
            (
                "Please respond without undue delay and in any event within one month of receipt, subject to Article 12(3) GDPR.",
                "If you decide not to act on this request, please provide the reasons and the information required by Article 12(4).",
                "If you have reasonable doubts about my identity, please request only the additional information necessary to confirm it in accordance with Article 12(6).",
                "",
                "Kind regards,",
                display_name,
            )
        )
