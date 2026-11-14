"""
Pydantic schemas for API request/response models.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


# ── Milestone 2 Schemas (Preserved) ───────────────────────────────────────────


class AskRequest(BaseModel):
    """Request model for the /ask endpoint (Milestone 2 RAG)."""

    query: str
    session_id: str


class Source(BaseModel):
    """Represents a document source citation."""

    id: int
    file: str
    page: str
    snippet: str


class AskResponse(BaseModel):
    """Response model for the /ask endpoint (Milestone 2 RAG)."""

    answer: str
    sources: List[Source]


class HistoryResponse(BaseModel):
    """Response model for the /history endpoint."""

    history: List[dict]
