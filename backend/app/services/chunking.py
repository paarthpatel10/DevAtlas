"""README cleaning, sectioning, and chunking (Markdown and reStructuredText).

README text is untrusted third-party content: it is cleaned for retrieval, stored as plain
text, and never interpreted as instructions.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.schemas.snapshot import RepoSnapshot

ReadmeFormat = Literal["markdown", "rst"]
MIN_CHUNK_CHARS = 40

_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_ATX = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_RST_UNDERLINE = re.compile(r"^([=\-~^*+#\"'`:.])\1{2,}\s*$")
_MD_UNDERLINE = re.compile(r"^\s{0,3}(=+|-+)\s*$")  # Markdown setext: only = and -


@dataclass(frozen=True)
class Chunk:
    position: int
    section_title: str | None
    content: str
    content_hash: str
    source_url: str | None
    source_type: Literal["readme", "metadata"]


@dataclass(frozen=True)
class Section:
    title: str | None
    text: str


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_format(source_url: str | None) -> ReadmeFormat:
    return "rst" if source_url and source_url.lower().endswith(".rst") else "markdown"


def clean_inline(text: str) -> str:
    """Remove inline emphasis/code markers for display names."""
    return re.sub(r"(\*\*|__|`)", "", text).strip()


def _normalise(text: str) -> str:
    text = "\n".join(line.rstrip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def clean_markdown(md: str) -> str:
    s = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)  # images (incl. badges)
    s = re.sub(r"\[\s*\]\([^)]*\)", "", s)  # links left empty after image removal
    s = re.sub(r"\[([^\]]+)\]\(\s*[^)\s]+(?:\s+\"[^\"]*\")?\s*\)", r"\1", s)  # links -> text
    s = re.sub(r"</?[a-zA-Z][^>\n]*>", "", s)  # HTML tags (content kept)
    s = re.sub(r"^(\s*(?:```|~~~))[\w+.-]+\s*$", r"\1", s, flags=re.M)  # fence language
    return _normalise(s)


def clean_rst(rst: str) -> str:
    lines = rst.splitlines()
    kept: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith(".. "):  # directive, comment, or substitution definition
            i += 1
            while i < len(lines) and (
                lines[i].startswith((" ", "\t"))
                or (not lines[i].strip() and i + 1 < len(lines) and lines[i + 1][:1] in (" ", "\t"))
            ):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    s = "\n".join(kept)
    s = re.sub(r"\|[\w\- ]+\|_{0,2}", "", s)  # substitution references (badges)
    s = re.sub(r"`([^`<]+?)\s*<[^>]+>`_{1,2}", r"\1", s)  # `text <url>`_
    s = re.sub(r":[\w-]+:`([^`]+)`", r"\1", s)  # :role:`text`
    s = re.sub(r"`([^`]+)`_{1,2}", r"\1", s)  # `ref`_
    return _normalise(s)


def clean_readme(text: str, fmt: ReadmeFormat) -> str:
    return clean_rst(text) if fmt == "rst" else clean_markdown(text)


def split_sections(text: str, fmt: ReadmeFormat) -> list[Section]:
    """Split cleaned README text into titled sections. Headings inside code fences ignored."""
    underline = _RST_UNDERLINE if fmt == "rst" else _MD_UNDERLINE
    lines = text.splitlines()
    sections: list[Section] = []
    title: str | None = None
    buf: list[str] = []
    in_fence = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append(Section(title, body))
        buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        if fmt == "markdown" and _FENCE.match(line):
            in_fence = not in_fence
            buf.append(line)
            i += 1
            continue
        if not in_fence:
            atx = _ATX.match(line) if fmt == "markdown" else None
            if atx:
                flush()
                title = clean_inline(atx.group(2)) or None
                i += 1
                continue
            if (
                underline.match(line)
                and i + 2 < len(lines)
                and lines[i + 1].strip()
                and not lines[i + 1][0].isspace()
                and underline.match(lines[i + 2])
            ):  # RST overline + title + underline
                flush()
                title = clean_inline(lines[i + 1])
                i += 3
                continue
            if (
                line.strip()
                and not line[0].isspace()
                and not underline.match(line)
                and i + 1 < len(lines)
                and underline.match(lines[i + 1])
                and (i == 0 or not lines[i - 1].strip())
            ):  # title + underline (RST, Markdown setext)
                flush()
                title = clean_inline(line)
                i += 2
                continue
        buf.append(line)
        i += 1
    flush()
    return sections


def _tail(text: str, size: int) -> str:
    if size <= 0 or len(text) <= size:
        return ""
    tail = text[-size:]
    space = tail.find(" ")
    return tail[space + 1 :].strip() if space != -1 else tail.strip()


def _hard_split(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    while len(text) > max_chars:
        cut = text.rfind(" ", 0, max_chars)
        cut = cut if cut > 0 else max_chars
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def _split_body(text: str, max_chars: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if paragraph:
            pieces.extend(_hard_split(paragraph, max_chars))
    chunks: list[str] = []
    current = ""
    for piece in pieces:
        candidate = f"{current}\n\n{piece}" if current else piece
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        tail = _tail(current, overlap)
        current = (
            f"{tail}\n\n{piece}" if tail and len(tail) + 2 + len(piece) <= max_chars else piece
        )
    if current:
        chunks.append(current)
    return chunks


def chunk_readme(
    text: str | None,
    source_url: str | None,
    *,
    max_chars: int = 1200,
    overlap: int = 150,
    max_chunks: int = 40,
) -> list[Chunk]:
    if not text or not text.strip():
        return []
    fmt = detect_format(source_url)
    chunks: list[Chunk] = []
    for section in split_sections(clean_readme(text, fmt), fmt):
        for body in _split_body(section.text, max_chars, overlap):
            if len(body) < MIN_CHUNK_CHARS:
                continue
            chunks.append(
                Chunk(
                    position=len(chunks),
                    section_title=section.title,
                    content=body,
                    content_hash=sha256(body),
                    source_url=source_url,
                    source_type="readme",
                )
            )
            if len(chunks) >= max_chunks:
                return chunks
    return chunks


def metadata_chunk(snap: "RepoSnapshot") -> Chunk:
    topics = ", ".join(t.replace("-", " ") for t in snap.topics)
    parts = [f"{snap.full_name}: {snap.description or 'No description provided.'}"]
    if topics:
        parts.append(f"Topics: {topics}.")
    if snap.primary_language:
        parts.append(f"Primary language: {snap.primary_language}.")
    content = " ".join(parts)
    return Chunk(
        position=-1,
        section_title="GitHub metadata",
        content=content,
        content_hash=sha256(content),
        source_url=snap.html_url,
        source_type="metadata",
    )
