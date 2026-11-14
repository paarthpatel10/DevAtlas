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


# ── Milestone 3 Schemas (New) ─────────────────────────────────────────────────


class AssistantRequest(BaseModel):
    """Request model for the /assistant endpoint."""

    query: str = Field(..., description="User's natural language query")
    session_id: str = Field(..., description="Session ID for conversation continuity")


class AssistantResponse(BaseModel):
    """Response model for the /assistant endpoint."""

    answer: str = Field(..., description="Final response from the assistant")
    route: str = Field(..., description="Which agent path handled the query (sql/rag)")
    sql_query: Optional[str] = Field(None, description="Generated SQL query, if applicable")
    sources: List[Source] = Field(default_factory=list, description="Document sources, if RAG path was used")
    error: Optional[str] = Field(None, description="Error message, if any")


class SchemaInfo(BaseModel):
    """Represents a database table's schema information."""

    table_name: str
    columns: List[dict] = Field(default_factory=list, description="List of column metadata dicts")
