"""Vocabulary for deterministic query understanding and evidence matching."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import BACKEND_DIR

VOCABULARY_PATH = BACKEND_DIR / "data" / "vocabulary.yaml"


@dataclass(frozen=True)
class StackTerm:
    name: str
    role: str
    language: str | None
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityConcept:
    key: str
    label: str
    category: str | None
    triggers: tuple[str, ...]
    expansions: tuple[str, ...]

    @property
    def evidence_phrases(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.triggers, *self.expansions)))


@dataclass(frozen=True)
class Vocabulary:
    stack_terms: tuple[StackTerm, ...]
    capabilities: tuple[CapabilityConcept, ...]
    licenses: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Vocabulary":
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        stack = tuple(
            StackTerm(
                name=name,
                role=spec["role"],
                language=spec.get("language"),
                aliases=tuple(dict.fromkeys([name.lower(), *spec.get("aliases", [])])),
            )
            for name, spec in raw.get("stack_terms", {}).items()
        )
        capabilities = tuple(
            CapabilityConcept(
                key=key,
                label=spec["label"],
                category=spec.get("category"),
                triggers=tuple(spec.get("triggers", [])),
                expansions=tuple(spec.get("expansions", [])),
            )
            for key, spec in raw.get("capabilities", {}).items()
        )
        licenses = {str(k).lower(): v for k, v in raw.get("licenses", {}).items()}
        return cls(stack_terms=stack, capabilities=capabilities, licenses=licenses)

    def capability_by_label(self, label: str) -> CapabilityConcept | None:
        return next((c for c in self.capabilities if c.label == label), None)

    def stack_term(self, name: str) -> StackTerm | None:
        return next((t for t in self.stack_terms if t.name == name), None)


@lru_cache
def get_vocabulary() -> Vocabulary:
    return Vocabulary.load(VOCABULARY_PATH)


@lru_cache(maxsize=4096)
def phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Case-insensitive match that does not start/end inside a word (handles `next.js`)."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", re.I)


def match_phrases(text: str, phrases: Sequence[str]) -> list[str]:
    return [p for p in phrases if phrase_pattern(p).search(text)]
