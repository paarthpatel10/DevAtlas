"""
LangGraph Workflow — builds and compiles the Data Assistant state graph.

"""

from langgraph.graph import END, StateGraph

from app.config.settings import settings
from app.graph.edges import after_sql_agent, route_query
from app.graph.nodes import (
    rag_node,
    response_node,
    router_node,
    sql_node,
    general_node,
    unknown_node,
    error_node,
)
from app.graph.state import GraphState
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def build_workflow() -> StateGraph:
    """
    Constructs the LangGraph StateGraph for the Data Assistant.

    """
    logger.info("Building LangGraph workflow with new routing architecture")

    workflow = StateGraph(GraphState)

    # ── Add Nodes ─────────────────────────────────────────────────────────
    workflow.add_node("router", router_node)
    workflow.add_node("sql_agent", sql_node)
    workflow.add_node("rag_agent", rag_node)
    workflow.add_node("general_node", general_node)
    workflow.add_node("unknown_node", unknown_node)
    workflow.add_node("error_node", error_node)
    workflow.add_node("response", response_node)

    # ── Set Entry Point ───────────────────────────────────────────────────
    workflow.set_entry_point("router")

    # ── Add Edges ─────────────────────────────────────────────────────────

    # Router → conditional routing to agents or error
    workflow.add_conditional_edges(
        "router",
        route_query,
        {
            "sql_agent": "sql_agent",
            "rag_agent": "rag_agent",
            "general_node": "general_node",
            "unknown_node": "unknown_node",
            "error_node": "error_node",
        },
    )

    # sql_agent → conditional: retry on error OR proceed to response
    workflow.add_conditional_edges(
        "sql_agent",
        after_sql_agent,
        {
            "sql_agent": "sql_agent",  # Self-correction loop
            "response": "response",
        },
    )

    # All other agents lead to response node
    workflow.add_edge("rag_agent", "response")
    workflow.add_edge("general_node", "response")
    workflow.add_edge("unknown_node", "response")
    workflow.add_edge("error_node", "response")

    # response → END
    workflow.add_edge("response", END)

    logger.info("LangGraph workflow built successfully with General/Unknown/Error fallback architecture")
    return workflow


def compile_workflow():
    """Compiles the workflow into a runnable graph with recursion limit."""
    workflow = build_workflow()
    compiled = workflow.compile()
    logger.info(
        f"Workflow compiled with max_steps={settings.MAX_GRAPH_STEPS}"
    )
    return compiled


# Module-level compiled graph (lazy singleton)
_compiled_graph = None


def get_compiled_graph():
    """Returns the compiled graph, creating it on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_workflow()
    return _compiled_graph
