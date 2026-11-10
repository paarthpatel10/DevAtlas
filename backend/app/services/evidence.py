"""Find source snippets that support a claim. Evidence is quoted, never paraphrased."""

from collections.abc import Sequence

from app.ai.vocabulary import phrase_pattern
from app.models import RepositoryChunk
from app.schemas.recommendation import Evidence

WINDOW = 160


def _snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - WINDOW)
    right = min(len(text), end + WINDOW)
    if left > 0:
        space = text.find(" ", left, start)
        left = space + 1 if space != -1 else left
    if right < len(text):
        space = text.rfind(" ", end, right)
        right = space if space != -1 else right
    body = " ".join(text[left:right].split())
    return ("…" if left > 0 else "") + body + ("…" if right < len(text) else "")


def find_evidence(
    chunks: Sequence[RepositoryChunk], phrases: Sequence[str], max_items: int = 2
) -> list[Evidence]:
    """First matching snippet per chunk; README chunks before GitHub metadata."""
    ordered = sorted(chunks, key=lambda c: (c.source_type == "metadata", c.position))
    found: list[Evidence] = []
    for chunk in ordered:
        best: tuple[int, int] | None = None
        for phrase in phrases:
            match = phrase_pattern(phrase).search(chunk.content)
            if match and (best is None or match.start() < best[0]):
                best = (match.start(), match.end())
        if best is None:
            continue
        found.append(
            Evidence(
                snippet=_snippet(chunk.content, *best),
                source_url=chunk.source_url,
                section_title=chunk.section_title,
                source_type=chunk.source_type,
            )
        )
        if len(found) >= max_items:
            break
    return found
