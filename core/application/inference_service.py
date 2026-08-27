from __future__ import annotations

import json
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Any

from core.application.inference_endpoint import InferenceEndpoint


class InferenceProtocolError(RuntimeError):
    pass


class InferenceService:
    """Call one configured OpenAI-compatible endpoint with bounded JSON-only responses."""

    def __init__(
        self,
        endpoint: InferenceEndpoint,
        *,
        timeout_seconds: float = 120.0,
        max_response_bytes: int = 1_048_576,
    ) -> None:
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("Inference bounds must be positive")
        self._endpoint = endpoint
        self._parsed = endpoint.validate()
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes

    @property
    def destination(self) -> str:
        return self._endpoint.url

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        if not model.strip():
            raise ValueError("Inference model is required")
        if not system_prompt.strip() or not user_prompt.strip():
            raise ValueError("Inference prompts must not be empty")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        response = self._post_json("/v1/chat/completions", payload)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceProtocolError("Inference response is missing assistant content") from exc
        if not isinstance(content, str):
            raise InferenceProtocolError("Inference assistant content must be text")
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InferenceProtocolError("Inference assistant content is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise InferenceProtocolError("Inference assistant JSON must be an object")
        return decoded

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connection_type = HTTPSConnection if self._parsed.scheme == "https" else HTTPConnection
        connection = connection_type(
            self._parsed.hostname,
            port=self._parsed.port,
            timeout=self._timeout_seconds,
        )
        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            response = connection.getresponse()
            if response.status < 200 or response.status >= 300:
                raise InferenceProtocolError(f"Inference server returned HTTP {response.status}")
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type not in {"application/json", "text/json"}:
                raise InferenceProtocolError("Inference server returned a non-JSON response")
            raw = response.read(self._max_response_bytes + 1)
            if len(raw) > self._max_response_bytes:
                raise InferenceProtocolError("Inference response exceeded the configured size limit")
        except (OSError, HTTPException) as exc:
            raise ConnectionError("Inference endpoint request failed") from exc
        finally:
            connection.close()

        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InferenceProtocolError("Inference server response is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise InferenceProtocolError("Inference server response must be a JSON object")
        return decoded
