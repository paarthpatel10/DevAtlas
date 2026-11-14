"""
Graph Nodes — individual node functions for the LangGraph workflow.
Each node reads from and writes to the GraphState.

Nodes are async to prevent blocking the FastAPI event loop.
Agents are instantiated per-node-call (no global singletons) for thread safety.
"""

import asyncio
from typing import Any, Dict

from app.graph.state import GraphState
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# ── Node Functions ────────────────────────────────────────────────────────────


async def router_node(state: GraphState) -> Dict[str, Any]:
    """
    Classifies the user query to determine the processing path.
    Uses SemanticRouter to set state['route'] to 'sql', 'rag', 'general', or 'unknown'.
    """
    logger.info("=== Router Node ===")

    from app.agents.execution_limits import ExecutionLimits
    safety = ExecutionLimits()
    steps = state.get("steps_taken", 0)

    if not safety.check_step_limit(steps):
        logger.warning("Step limit exceeded in router")
        return {"error": "Maximum graph steps exceeded", "route": "error"}

    from app.agents.semantic_router import SemanticRouter
    router = SemanticRouter()
    query = state["query"]
    chat_history = state.get("chat_history", [])

    # Route using SemanticRouter
    routing_result = await asyncio.to_thread(router.route, query, chat_history)
    route = routing_result["route"]

    logger.info(f"Router decided route: {route} (explanation: {routing_result.get('explanation')})")
    return {"route": route, "steps_taken": steps + 1}


async def sql_node(state: GraphState) -> Dict[str, Any]:
    """
    Processes the query through the SQL agent.
    Sets state['sql_result'] and state['sql_query'].
    On retry (self-correction), passes the previous error to the agent.
    """
    logger.info("=== SQL Agent Node ===")

    from app.agents.sql_agent import SQLAgent

    sql_agent = SQLAgent()
    query = state["query"]
    chat_history = state.get("chat_history", [])
    previous_error = state.get("previous_sql_error", "")

    result = await asyncio.to_thread(
        sql_agent.run, query, chat_history, previous_error
    )

    steps = state.get("steps_taken", 0)
    sql_retries = state.get("sql_retries", 0)

    return {
        "sql_query": result.get("sql_query", ""),
        "sql_result": result.get("formatted_result", ""),
        "error": result.get("error", ""),
        "previous_sql_error": result.get("error", "") if not result.get("success") else "",
        "steps_taken": steps + 1,
        "sql_retries": sql_retries + 1,
    }


async def rag_node(state: GraphState) -> Dict[str, Any]:
    """
    Processes the query through the RAG agent.
    Sets state['rag_result'] and state['rag_sources'].
    """
    logger.info("=== RAG Agent Node ===")

    from app.agents.rag_agent import RAGAgent

    rag_agent = RAGAgent()
    query = state["query"]
    chat_history = state.get("chat_history", [])

    result = await asyncio.to_thread(rag_agent.run, query, chat_history)

    steps = state.get("steps_taken", 0)
    return {
        "rag_result": result.get("answer", ""),
        "rag_sources": result.get("sources", []),
        "error": result.get("error", ""),
        "steps_taken": steps + 1,
    }


async def general_node(state: GraphState) -> Dict[str, Any]:
    """
    Processes casual chit-chat, greetings, weather, and general conversational questions.
    Sets state['rag_result'] with the conversational answer.
    """
    logger.info("=== General Agent Node ===")

    from app.agents.general_agent import GeneralAgent
    general_agent = GeneralAgent()
    query = state["query"]
    chat_history = state.get("chat_history", [])

    result = await asyncio.to_thread(general_agent.run, query, chat_history)

    steps = state.get("steps_taken", 0)
    return {
        "rag_result": result.get("answer", ""),
        "error": result.get("error", ""),
        "steps_taken": steps + 1,
    }


async def unknown_node(state: GraphState) -> Dict[str, Any]:
    """
    Handles ambiguous or low confidence requests.
    Sets state['rag_result'] with clarification prompt.
    """
    logger.info("=== Unknown Agent Node ===")

    from app.agents.unknown_handler import UnknownHandler
    unknown_handler = UnknownHandler()
    query = state["query"]
    chat_history = state.get("chat_history", [])

    result = await asyncio.to_thread(unknown_handler.run, query, chat_history)

    steps = state.get("steps_taken", 0)
    return {
        "rag_result": result.get("answer", ""),
        "error": result.get("error", ""),
        "steps_taken": steps + 1,
    }


async def error_node(state: GraphState) -> Dict[str, Any]:
    """
    Error handling node to capture maximum steps exceeded or routing failures.
    Sets state['error'].
    """
    logger.info("=== Error Node ===")
    steps = state.get("steps_taken", 0)
    return {
        "error": state.get("error", "An internal error or limit occurred during query routing."),
        "steps_taken": steps + 1,
    }


async def response_node(state: GraphState) -> Dict[str, Any]:
    """
    Aggregates results from the active agent path and applies the Response Formatter
    for professional presentation. Sets state['final_response'].
    """
    logger.info("=== Response Aggregator Node ===")

    from app.agents.response_agent import ResponseAgent
    from app.agents.response_formatter import ResponseFormatter

    response_agent = ResponseAgent()
    response_formatter = ResponseFormatter()

    query = state["query"]
    route = state.get("route", "rag")
    sql_result = state.get("sql_result")
    rag_result = state.get("rag_result")
    error = state.get("error")

    # Don't pass error to response agent if it's empty string
    error_msg = error if error else None

    # Step 1: Synthesize standard response
    raw_response = await asyncio.to_thread(
        response_agent.synthesize,
        query=query,
        route=route,
        sql_result=sql_result,
        rag_result=rag_result,
        error=error_msg,
    )

    # Step 2: Format final response via ResponseFormatter
    if "I don't know based on the uploaded documents" in raw_response:
        formatted_response = "I don't know based on the uploaded documents."
    else:
        formatted_response = await asyncio.to_thread(
            response_formatter.format,
            query=query,
            raw_response=raw_response,
        )

    steps = state.get("steps_taken", 0)
    return {"final_response": formatted_response, "steps_taken": steps + 1}
