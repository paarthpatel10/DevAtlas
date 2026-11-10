"""Deterministic query understanding (demo mode).

Extracts only what the query states: requirements and stack terms recognised from the
vocabulary, explicit constraint phrases, and a license preference only when licensing is
mentioned. Anything derived (category, implied language) is listed under `inferred`.
"""

import re
from collections import Counter

from app.ai.mock_providers import tokenize
from app.ai.vocabulary import Vocabulary, match_phrases
from app.schemas.recommendation import QueryIntent
from app.schemas.snapshot import CATEGORY_LABELS

_CONSTRAINT = re.compile(r"\b(?:must|should|without|no|only|prefer)\b[^.,;!?]*", re.I)
_LICENSE_MENTION = re.compile(r"\blicen[cs](?:e|ed|es|ing)\b", re.I)
CLARIFYING_QUESTION = (
    "What are you building, and what should the tool do? "
    "For example: 'a job queue for a FastAPI app'."
)


def understand_query(text: str, vocab: Vocabulary) -> QueryIntent:
    goal = " ".join(text.split())

    matched = [c for c in vocab.capabilities if match_phrases(goal, c.triggers)]
    requirements = [c.label for c in matched]

    known_stack: dict[str, list[str]] = {}
    for term in vocab.stack_terms:
        if match_phrases(goal, term.aliases):
            known_stack.setdefault(term.role, []).append(term.name)

    inferred: list[str] = []
    category: str | None = None
    categories = Counter(c.category for c in matched if c.category)
    if categories:
        top = max(categories.values())
        category = next(c.category for c in matched if categories.get(c.category) == top)
        sources = [c.label for c in matched if c.category == category]
        label = CATEGORY_LABELS.get(category or "", category)
        inferred.append(f"Category '{label}' inferred from: {', '.join(sources)}")
    for names in known_stack.values():
        for name in names:
            term = vocab.stack_term(name)
            if term and term.language and term.role != "language":
                inferred.append(f"Language {term.language} inferred from {name}")

    preferred_license = None
    if _LICENSE_MENTION.search(goal):
        for phrase in sorted(vocab.licenses, key=len, reverse=True):
            if match_phrases(goal, [phrase]):
                preferred_license = vocab.licenses[phrase]
                break

    constraints = [m.group(0).strip() for m in _CONSTRAINT.finditer(goal)]

    keywords: list[str] = []
    for concept in matched:
        keywords += [concept.label, *concept.expansions]
    for names in known_stack.values():
        keywords += names
    keywords = list(dict.fromkeys(keywords))

    clarifying = None
    if not matched and not known_stack and len(tokenize(goal)) < 3:
        clarifying = CLARIFYING_QUESTION

    return QueryIntent(
        goal=goal,
        requirements=requirements,
        constraints=constraints,
        known_stack=known_stack,
        category=category,
        preferred_license=preferred_license,
        keywords=keywords,
        inferred=inferred,
        clarifying_question=clarifying,
    )
