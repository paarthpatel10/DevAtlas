"""
Graph Edges — conditional edge functions for the LangGraph workflow.
Determines routing between nodes based on the current state.
"""

from app.config.settings import settings
from app.graph.state import GraphState
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def route_query(state: GraphState) -> str:
    """
    Conditional edge function that routes to the appropriate agent node
    based on the classification result from the router.

    Returns:
        'sql_agent', 'rag_agent', 'general_node', 'unknown_node', or 'error_node'
    """
    route = state.get("route", "unknown")
    error = state.get("error", "")

    if error or route == "error":
        logger.warning(f"Error in state or route is error, routing to error_node: {error}")
        return "error_node"

    if route == "sql":
        logger.info("Edge routing → SQL Agent")
        return "sql_agent"
    elif route == "rag":
        logger.info("Edge routing → RAG Agent")
        return "rag_agent"
    elif route == "general":
        logger.info("Edge routing → General Node")
        return "general_node"
    elif route == "unknown":
        logger.info("Edge routing → Unknown Node")
        return "unknown_node"
    else:
        logger.warning(f"Unexpected route '{route}', routing to unknown_node")
        return "unknown_node"


def after_sql_agent(state: GraphState) -> str:
    """
    Conditional edge after SQL Agent execution.
    Implements self-correction: if the SQL query failed and we haven't
    exceeded the retry limit, route back to sql_agent for another attempt.
    Otherwise, route to response.

    Returns:
        'sql_agent' (retry) or 'response' (success or give up).
    """
    error = state.get("error", "")
    sql_retries = state.get("sql_retries", 0)
    steps = state.get("steps_taken", 0)
    success_indicators = state.get("sql_result", "")

    # If there was no error, proceed to response
    if not error:
        logger.info("SQL succeeded — routing to response")
        return "response"

    # Retryable error: check limits
    max_retries = settings.RETRY_LIMIT
    if sql_retries < max_retries and steps < settings.MAX_GRAPH_STEPS:
        logger.warning(
            f"SQL error detected (retry {sql_retries}/{max_retries}): {error[:100]}. "
            "Routing back to sql_agent for self-correction."
        )
        return "sql_agent"

    logger.warning(
        f"SQL retry limit reached ({sql_retries}/{max_retries}) or step limit hit. "
        "Routing to response with error."
    )
    return "response"
