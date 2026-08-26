from __future__ import annotations

import json

import pytest

from core.application.artifact_analyzer import ArtifactAnalyzer
from core.application.egress_policy import EgressPolicy
from core.application.identity_service import IdentityService
from core.application.investigation_service import InvestigationService
from core.application.network_policy import NetworkPolicy, NetworkPolicyError
from core.application.research_service import (
    ResearchError,
    ResearchService,
    TransportResponse,
)
from core.domain.investigation import ArtifactKind, ArtifactRole, EvidenceProvenance
from core.storage.artifact_store import ArtifactStore
from core.storage.database import Database
from core.storage.identity_repository import IdentityRepository
from core.storage.investigation_repository import InvestigationRepository
from core.storage.sensitive_store import SensitiveStore

TEST_KEY = b"r" * 32
PUBLIC_IP = "93.184.216.34"


def resolver_for(*addresses):
    def resolve(_host, port, _family, _socktype):
        return [(2, 1, 6, "", (address, port)) for address in addresses]

    return resolve


def test_network_policy_rejects_non_public_destinations_and_unsafe_urls():
    private_policy = NetworkPolicy(resolver_for("127.0.0.1"))
    with pytest.raises(NetworkPolicyError, match="non-public"):
        private_policy.validate_public_url("https://example.test/path")

    public_policy = NetworkPolicy(resolver_for(PUBLIC_IP))
    with pytest.raises(NetworkPolicyError, match="HTTP and HTTPS"):
        public_policy.validate_public_url("file:///etc/passwd")
    with pytest.raises(NetworkPolicyError, match="credentials"):
        public_policy.validate_public_url("https://user:secret@example.test/")
    with pytest.raises(NetworkPolicyError, match="disallowed port"):
        public_policy.validate_public_url("https://example.test:8443/")


def test_network_policy_rejects_host_if_any_resolved_address_is_private():
    policy = NetworkPolicy(resolver_for(PUBLIC_IP, "10.0.0.10"))
    with pytest.raises(NetworkPolicyError, match="non-public"):
        policy.validate_public_url("https://example.test/")


def test_research_revalidates_every_redirect_before_transport():
    policy = NetworkPolicy(resolver_for(PUBLIC_IP))
    calls = []

    def transport(validated, _timeout, _max_bytes):
        calls.append(validated.url)
        return TransportResponse(302, {"location": "http://127.0.0.1/private"}, b"")

    service = ResearchService(policy, transport)
    with pytest.raises(ResearchError, match="non-public"):
        service.fetch_public_document("https://example.test/start")
    assert calls == ["https://example.test/start"]


def test_research_enforces_content_type_and_redirect_limit():
    policy = NetworkPolicy(resolver_for(PUBLIC_IP))

    def binary_transport(_validated, _timeout, _max_bytes):
        return TransportResponse(200, {"content-type": "application/octet-stream"}, b"binary")

    with pytest.raises(ResearchError, match="content type"):
        ResearchService(policy, binary_transport).fetch_public_document("https://example.test/")

    def loop_transport(validated, _timeout, _max_bytes):
        return TransportResponse(302, {"location": validated.url}, b"")

    with pytest.raises(ResearchError, match="redirect limit"):
        ResearchService(policy, loop_transport).fetch_public_document("https://example.test/")


def test_rdap_lookup_uses_iana_bootstrap_and_selected_https_service():
    policy = NetworkPolicy(resolver_for(PUBLIC_IP))
    calls = []
    bootstrap = json.dumps(
        {"services": [[["com"], ["https://rdap.example.test/"]]]}
    ).encode()

    def transport(validated, _timeout, _max_bytes):
        calls.append(validated.url)
        if validated.url == ResearchService.IANA_RDAP_BOOTSTRAP:
            return TransportResponse(200, {"content-type": "application/json"}, bootstrap)
        if validated.url == "https://rdap.example.test/domain/example.com":
            return TransportResponse(
                200,
                {"content-type": "application/rdap+json"},
                b'{"objectClassName":"domain"}',
            )
        raise AssertionError(f"Unexpected URL: {validated.url}")

    document = ResearchService(policy, transport).lookup_domain_rdap("example.com")
    assert document.final_url == "https://rdap.example.test/domain/example.com"
    assert calls == [ResearchService.IANA_RDAP_BOOTSTRAP, document.final_url]


def build_investigation_service(tmp_path, transport):
    database = Database(tmp_path / "gdpr_hunter.sqlite3")
    database.initialize()
    sensitive = SensitiveStore(TEST_KEY)
    identity = IdentityService(IdentityRepository(database, sensitive))
    research = ResearchService(NetworkPolicy(resolver_for(PUBLIC_IP)), transport)
    service = InvestigationService(
        InvestigationRepository(database, sensitive),
        ArtifactStore(tmp_path / "artifacts", sensitive),
        identity,
        ArtifactAnalyzer(),
        research,
        EgressPolicy(),
    )
    return database, service


def test_investigation_research_requires_approval_and_records_remote_snapshot(tmp_path):
    transport_calls = []

    def transport(validated, _timeout, _max_bytes):
        transport_calls.append(validated.url)
        return TransportResponse(
            200,
            {"content-type": "text/html; charset=utf-8"},
            b"<html><body>Privacy policy https://partner.example.test/privacy</body></html>",
        )

    database, service = build_investigation_service(tmp_path, transport)
    investigation = service.create_investigation("Research")
    assert investigation.id is not None
    artifact = service.import_artifact(
        investigation.id,
        ArtifactKind.SMS,
        ArtifactRole.TRIGGER,
        "text/plain",
        b"Visit https://example.test/privacy",
    )
    assert artifact.id is not None
    service.analyze_artifact(investigation.id, artifact.id)

    with pytest.raises(PermissionError, match="approval"):
        service.research_artifact_urls(investigation.id, artifact.id, approved_by_user=False)
    assert transport_calls == []

    created = service.research_artifact_urls(investigation.id, artifact.id, approved_by_user=True)
    assert transport_calls == ["https://example.test/privacy"]
    assert any(item.provenance is EvidenceProvenance.REMOTE_DOCUMENT for item in created)
    assert any(item.value == "partner.example.test" for item in created)
    assert len(service.list_artifacts(investigation.id)) == 2
    assert b"Privacy policy" not in database.path.read_bytes()

    again = service.research_artifact_urls(investigation.id, artifact.id, approved_by_user=True)
    assert again == []
    assert transport_calls == ["https://example.test/privacy"]
