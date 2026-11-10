"""Gemini LLM provider (REST `generateContent` with JSON-schema structured output).

Only the provider knows about Gemini; business logic uses the `LLMProvider` interface.
"""

import copy
import json
import logging
import ssl
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
import truststore
from pydantic import BaseModel, ValidationError

from app.core.errors import AppError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMUnavailableError(AppError):
    status_code = 503
    code = "ai_unavailable"

    def __init__(self, message: str = "The AI provider is unavailable. Try again later.") -> None:
        super().__init__(message)


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref`/`$defs` and drop `title` keys (Gemini accepts a JSON Schema subset)."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return resolve(copy.deepcopy(defs[name]))
            return {
                k: resolve(v)
                for k, v in node.items()
                # Drop `title` annotations (strings) but keep properties that are named "title".
                if k != "$defs" and not (k == "title" and isinstance(v, str))
            }
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


class GeminiLLMProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model
        self.model_name = f"gemini:{model}"
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=base_url,
            headers={"x-goog-api-key": api_key, "content-type": "application/json"},
            timeout=timeout,
            transport=transport,
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
        )

    # Public API -------------------------------------------------------------------------

    def generate_text(self, system: str, prompt: str) -> str:
        return self._call(system, prompt, None)

    def generate_structured(self, system: str, prompt: str, schema: type[T]) -> T:
        json_schema = inline_refs(schema.model_json_schema())
        for attempt in range(2):  # one retry for output that fails validation
            text = self._call(system, prompt, json_schema)
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                logger.warning(
                    "Gemini output failed validation (attempt %s): %s",
                    attempt + 1,
                    exc.error_count(),
                )
        raise LLMUnavailableError("The AI response could not be validated.")

    # Internals --------------------------------------------------------------------------

    def _call(self, system: str, prompt: str, json_schema: dict[str, Any] | None) -> str:
        config: dict[str, Any] = {"temperature": 0.2}
        if json_schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseJsonSchema"] = json_schema
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }
        data = self._post(f"/models/{self.model}:generateContent", body)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError):
            # Empty or blocked candidates: treat like invalid output (validated by caller).
            return ""

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                response = self._client.post(path, content=json.dumps(body))
            except httpx.TransportError as exc:
                self._backoff_or_raise(attempt, f"transport error: {type(exc).__name__}")
                attempt += 1
                continue
            if response.status_code < 400:
                return response.json()
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("retry-after", "")
                if attempt < self._max_retries and retry_after.isdigit():
                    self._sleep(float(retry_after))
                    attempt += 1
                    continue
                self._backoff_or_raise(attempt, f"HTTP {response.status_code}")
                attempt += 1
                continue
            # 4xx other than 429: configuration problem (bad key/model); never log the key.
            logger.error("Gemini request rejected: HTTP %s", response.status_code)
            raise LLMUnavailableError(
                f"The AI provider rejected the request (HTTP {response.status_code})."
            )

    def _backoff_or_raise(self, attempt: int, reason: str) -> None:
        if attempt >= self._max_retries:
            raise LLMUnavailableError()
        delay = 2**attempt
        logger.warning("Gemini request failed (%s); retrying in %ss", reason, delay)
        self._sleep(delay)
