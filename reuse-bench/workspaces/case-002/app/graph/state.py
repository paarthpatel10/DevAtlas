"""
Graph State — typed state object for the LangGraph workflow.
All nodes read from and write to this shared state.
"""

from typing import Any, Dict, List, TypedDict


class GraphState(TypedDict, total=False):
    """
    Typed state object passed through the LangGraph workflow.

    Fields:
        query: The user's original natural language query.
        session_id: Session identifier for conversation continuity.
        route: The classified route — 'sql' or 'rag'.
        sql_query: The generated SQL query (if SQL path).
        sql_result: Formatted SQL execution results (if SQL path).
        rag_result: Generated RAG response (if RAG path).
        rag_sources: Document sources from RAG retrieval.
        final_response: The aggregated final response for the user.
        chat_history: Conversation history for multi-turn support.
        error: Error message if any step failed.
        steps_taken: Counter for safety step limits.
        previous_sql_error: Error from last SQL attempt (for self-correction).
        sql_retries: Number of SQL generation retries so far.
    """

    query: str
    session_id: str
    route: str
    sql_query: str
    sql_result: str
    rag_result: str
    rag_sources: List[Dict[str, Any]]
    final_response: str
    chat_history: List[Dict[str, str]]
    error: str
    steps_taken: int
    previous_sql_error: str
    sql_retries: int
