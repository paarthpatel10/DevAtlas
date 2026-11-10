"""Test doubles for AI providers (no network)."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.ai.gemini_provider import LLMUnavailableError


class FakeLLM:
    """Returns canned structured outputs; records every call."""

    model_name = "fake:llm"

    def __init__(
        self,
        responder: Callable[[str, str, type[BaseModel]], Any] | None = None,
        fail: bool = False,
    ) -> None:
        self.responder = responder
        self.fail = fail
        self.calls: list[tuple[str, str, str]] = []

    def generate_text(self, system: str, prompt: str) -> str:
        raise NotImplementedError

    def generate_structured(self, system: str, prompt: str, schema: type[BaseModel]):
        self.calls.append((system, prompt, schema.__name__))
        if self.fail:
            raise LLMUnavailableError()
        assert self.responder is not None, "FakeLLM needs a responder"
        result = self.responder(system, prompt, schema)
        return result if isinstance(result, schema) else schema.model_validate(result)


def report_citing_first_source(system: str, prompt: str, schema) -> dict:
    """A plausible model report that cites C1/C2 (present in every prompt)."""
    return {
        "what_is_it": {
            "one_line": "A background job queue for Python apps.",
            "explanation": "It runs work outside web requests.",
            "cites": ["C2"],
        },
        "problem_solved": {"text": "Moving slow work out of request handlers.", "cites": ["C2"]},
        "why_interesting": [{"point": "Retries with exponential backoff.", "cites": ["C2"]}],
        "who_should_care": [
            {"audience": "Backend developers", "reason": "Reliable jobs.", "cites": ["C2"]}
        ],
        "use_cases": [{"text": "Sending emails asynchronously.", "cites": ["C2"]}],
        "build_ideas": [
            {
                "title": "Notification worker",
                "description": "Send emails in the background.",
                "how_it_is_used": "Enqueue email jobs that retry on failure.",
                "complementary_tech": ["Redis"],
                "cites": ["C2"],
            },
            {
                "title": "Nightly report",
                "description": "Generate reports on a schedule.",
                "how_it_is_used": "Use cron-style scheduling.",
                "complementary_tech": [],
                "cites": ["C2"],
            },
        ],
        "technical": {
            "frameworks": [],
            "capabilities": [{"name": "Retries", "cites": ["C2"]}],
            "integrations": [],
            "prerequisites": [],
            "architecture": None,
        },
        "limitations": [],
        "getting_started": [],
    }
