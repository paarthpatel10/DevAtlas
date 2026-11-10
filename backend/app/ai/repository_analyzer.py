"""Repository analysis. Demo mode uses a deterministic, extractive analyzer.

The mock analyzer never invents content: every capability is a bullet copied from the
README, and fields it cannot establish (problem solved, use cases, limitations) stay empty
so the UI can say "Not established". LLM analysis arrives with the Bedrock provider (M3).
"""

import re

from app.schemas.analysis import Capability, RepositoryAnalysisOut
from app.schemas.snapshot import RepoSnapshot
from app.services.chunking import clean_inline, clean_readme, detect_format, split_sections

_CAPABILITY_SECTION = re.compile(r"feature|highlight|capabilit|why|what", re.I)
_NOT_CAPABILITY_SECTION = re.compile(r"need|require|install|sponsor|support\b", re.I)
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.+)$")
_MAX_CAPABILITIES = 8
_SUMMARY_MAX = 300
_NAME_MAX = 80


def _truncate(text: str, limit: int, ellipsis: str = "") -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + ellipsis


def _bullets(text: str) -> list[str]:
    items: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _BULLET.match(line)
        if match:
            items.append(match.group(1).strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] = f"{items[-1]} {line.strip()}"
    return items


def _first_paragraph(text: str) -> str | None:
    for paragraph in re.split(r"\n\s*\n", text):
        flat = " ".join(paragraph.split())
        if len(flat) < 40 or flat.startswith(("```", "~~~", "|", ">", "-", "*", "+", "$")):
            continue
        return _truncate(flat, _SUMMARY_MAX, "…")
    return None


class MockRepositoryAnalyzer:
    analysis_version = "mock-extractive-v1"
    model_name = "mock"
    prompt_version = "none"

    def analyze(self, snap: RepoSnapshot) -> RepositoryAnalysisOut:
        sections = []
        if snap.readme_text:
            fmt = detect_format(snap.readme_url)
            sections = split_sections(clean_readme(snap.readme_text, fmt), fmt)

        capabilities: list[Capability] = []
        for section in sections:
            title = section.title or ""
            if not _CAPABILITY_SECTION.search(title) or _NOT_CAPABILITY_SECTION.search(title):
                continue
            for bullet in _bullets(section.text):
                description = clean_inline(bullet)
                if len(description) < 3:
                    continue
                capabilities.append(
                    Capability(
                        name=_truncate(description, _NAME_MAX),
                        description=description,
                        evidence=[bullet],
                        confidence="medium",
                    )
                )
                if len(capabilities) >= _MAX_CAPABILITIES:
                    break
            if len(capabilities) >= _MAX_CAPABILITIES:
                break

        summary = snap.description
        if not summary:
            summary = next((p for p in (_first_paragraph(s.text) for s in sections) if p), None)

        languages = sorted(snap.languages.items(), key=lambda kv: kv[1], reverse=True)
        return RepositoryAnalysisOut(
            summary=summary,
            problem_solved=None,
            category=snap.category,
            subcategory=None,
            capabilities=capabilities,
            use_cases=[],
            supported_languages=[name for name, _ in languages[:3]],
            integrations=[],
            requirements=[],
            limitations=[],
            maturity="inactive" if snap.archived else "unknown",
            target_users=[],
            keywords=[t.replace("-", " ") for t in snap.topics],
            analysis_version=self.analysis_version,
            model_name=self.model_name,
            prompt_version=self.prompt_version,
        )
