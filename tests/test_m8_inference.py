from __future__ import annotations

import json

import pytest

import core.application.inference_service as inference_module
from core.application.inference_endpoint import InferenceEndpoint, InferenceLocation
from core.application.inference_service import InferenceProtocolError, InferenceService


class FakeResponse:
    def __init__(self, payload: object, *, status: int = 200, content_type: str = "application/json") -> None:
        self.status = status
        self._content_type = content_type
        self._raw = json.dumps(payload).encode("utf-8")

    def getheader(self, name: str, default: str = "") -> str:
        return self._content_type if name == "Content-Type" else default

    def read(self, amount: int) -> bytes:
        return self._raw[:amount]


class FakeConnection:
    response_payload: object = {
        "choices": [{"message": {"content": '{"summary":"ok"}'}}]
    }
    last_request: tuple[str, str, bytes, dict[str, str]] | None = None

    def __init__(self, host: str, *, port: int | None, timeout: float) -> None:
        assert host == "127.0.0.1"
        assert port == 8080
        assert timeout == 120.0

    def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]) -> None:
        self.__class__.last_request = (method, path, body, headers)

    def getresponse(self) -> FakeResponse:
        return FakeResponse(self.__class__.response_payload)

    def close(self) -> None:
        return None


def test_local_process_endpoint_rejects_non_loopback_host() -> None:
    endpoint = InferenceEndpoint("http://192.168.1.20:8080", InferenceLocation.LOCAL_PROCESS)
    with pytest.raises(ValueError, match="loopback"):
        endpoint.validate()


def test_lan_endpoint_accepts_configured_http_endpoint() -> None:
    parsed = InferenceEndpoint(
        "http://192.168.1.20:8080",
        InferenceLocation.USER_APPROVED_LAN,
    ).validate()
    assert parsed.hostname == "192.168.1.20"
    assert parsed.port == 8080


def test_complete_json_uses_openai_compatible_json_only_request(monkeypatch) -> None:
    monkeypatch.setattr(inference_module, "HTTPConnection", FakeConnection)
    service = InferenceService(
        InferenceEndpoint("http://127.0.0.1:8080", InferenceLocation.LOCAL_PROCESS)
    )

    result = service.complete_json(
        model="local-model",
        system_prompt="Return structured analysis only.",
        user_prompt="Analyse this evidence.",
    )

    assert result == {"summary": "ok"}
    assert FakeConnection.last_request is not None
    method, path, body, headers = FakeConnection.last_request
    assert method == "POST"
    assert path == "/v1/chat/completions"
    assert headers["Content-Type"] == "application/json"
    payload = json.loads(body)
    assert payload["stream"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert "tools" not in payload


def test_complete_json_rejects_non_json_assistant_content(monkeypatch) -> None:
    monkeypatch.setattr(inference_module, "HTTPConnection", FakeConnection)
    FakeConnection.response_payload = {"choices": [{"message": {"content": "not json"}}]}
    service = InferenceService(
        InferenceEndpoint("http://127.0.0.1:8080", InferenceLocation.LOCAL_PROCESS)
    )
    try:
        with pytest.raises(InferenceProtocolError, match="valid JSON"):
            service.complete_json(model="m", system_prompt="system", user_prompt="user")
    finally:
        FakeConnection.response_payload = {
            "choices": [{"message": {"content": '{"summary":"ok"}'}}]
        }
