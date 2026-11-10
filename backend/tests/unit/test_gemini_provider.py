import json

import httpx
import pytest
from pydantic import BaseModel

from app.ai.gemini_provider import GeminiLLMProvider, LLMUnavailableError, inline_refs


class Inner(BaseModel):
    name: str


class Outer(BaseModel):
    title: str
    items: list[Inner]


def gemini_body(payload: dict | str) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}}]}


def make_provider(responses):
    queue = list(responses)
    requests: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return queue.pop(0)

    provider = GeminiLLMProvider(
        "secret-key",
        "gemini-3.5-flash",
        "https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
    )
    return provider, requests, sleeps


GOOD = {"title": "t", "items": [{"name": "a"}]}


def test_structured_request_shape_and_parsing():
    provider, requests, _ = make_provider([httpx.Response(200, json=gemini_body(GOOD))])
    result = provider.generate_structured("SYSTEM RULES", "user prompt", Outer)
    assert result == Outer(**GOOD)
    req = requests[0]
    assert req.url.path.endswith("/models/gemini-3.5-flash:generateContent")
    assert req.headers["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYSTEM RULES"
    assert body["contents"][0]["parts"][0]["text"] == "user prompt"
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert "$ref" not in json.dumps(config["responseJsonSchema"])
    assert provider.model_name == "gemini:gemini-3.5-flash"


def test_invalid_output_retried_once_then_succeeds():
    provider, requests, _ = make_provider(
        [
            httpx.Response(200, json=gemini_body("not json")),
            httpx.Response(200, json=gemini_body(GOOD)),
        ]
    )
    assert provider.generate_structured("s", "p", Outer).title == "t"
    assert len(requests) == 2


def test_invalid_output_twice_raises():
    provider, _, _ = make_provider(
        [
            httpx.Response(200, json=gemini_body({"title": 1})),
            httpx.Response(200, json=gemini_body({"wrong": True})),
        ]
    )
    with pytest.raises(LLMUnavailableError):
        provider.generate_structured("s", "p", Outer)


def test_rate_limited_response_honours_retry_after():
    provider, _, sleeps = make_provider(
        [
            httpx.Response(429, headers={"retry-after": "2"}, json={}),
            httpx.Response(200, json=gemini_body(GOOD)),
        ]
    )
    provider.generate_structured("s", "p", Outer)
    assert sleeps == [2.0]


def test_persistent_server_errors_raise_unavailable():
    provider, _, sleeps = make_provider([httpx.Response(503, json={})] * 4)
    with pytest.raises(LLMUnavailableError) as e:
        provider.generate_structured("s", "p", Outer)
    assert sleeps == [1, 2, 4]
    assert e.value.code == "ai_unavailable" and e.value.status_code == 503


def test_blocked_or_empty_candidates_raise_unavailable():
    provider, _, _ = make_provider([httpx.Response(200, json={"candidates": []})] * 2)
    with pytest.raises(LLMUnavailableError):
        provider.generate_structured("s", "p", Outer)


def test_generate_text():
    provider, _, _ = make_provider([httpx.Response(200, json=gemini_body("hello"))])
    assert provider.generate_text("s", "p") == "hello"


def test_inline_refs_resolves_nested_models():
    schema = inline_refs(Outer.model_json_schema())
    dumped = json.dumps(schema)
    assert "$ref" not in dumped and "$defs" not in dumped
    assert "title" not in schema  # annotation removed
    assert schema["properties"]["title"]["type"] == "string"  # property named "title" kept
    assert schema["properties"]["items"]["items"]["properties"]["name"]["type"] == "string"
