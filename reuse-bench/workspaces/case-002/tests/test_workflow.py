"""
LangGraph workflow tests — verifies the end-to-end graph execution
with mocked agents.
"""

import pytest


def test_workflow_compiles():
    """Test that the LangGraph workflow compiles without errors."""
    from app.graph.workflow import build_workflow

    workflow = build_workflow()
    compiled = workflow.compile()
    assert compiled is not None


def test_workflow_has_all_nodes():
    """Test that the compiled workflow contains all expected nodes."""
    from app.graph.workflow import build_workflow

    workflow = build_workflow()
    # Access the nodes dict on the builder
    node_names = set(workflow.nodes.keys())
    expected = {"router", "sql_agent", "rag_agent", "general_node", "unknown_node", "error_node", "response"}
    assert expected.issubset(node_names), f"Missing nodes: {expected - node_names}"


def test_graph_state_has_required_fields():
    """Test that GraphState has all required fields."""
    from app.graph.state import GraphState

    # TypedDict fields are in __annotations__
    annotations = GraphState.__annotations__
    required_fields = [
        "query",
        "session_id",
        "route",
        "sql_result",
        "rag_result",
        "final_response",
        "chat_history",
        "error",
        "steps_taken",
    ]
    for field in required_fields:
        assert field in annotations, f"Missing field: {field}"


def test_edge_function_routes_sql():
    """Test that the edge function routes SQL queries correctly."""
    from app.graph.edges import route_query

    state = {"route": "sql", "error": ""}
    assert route_query(state) == "sql_agent"


def test_edge_function_routes_rag():
    """Test that the edge function routes RAG queries correctly."""
    from app.graph.edges import route_query

    state = {"route": "rag", "error": ""}
    assert route_query(state) == "rag_agent"


def test_edge_function_routes_error_to_response():
    """Test that errors route directly to error node."""
    from app.graph.edges import route_query

    state = {"route": "sql", "error": "Something went wrong"}
    assert route_query(state) == "error_node"


def test_edge_function_defaults_to_rag():
    """Test that missing route defaults to unknown."""
    from app.graph.edges import route_query

    state = {"error": ""}
    assert route_query(state) == "unknown_node"


def test_full_workflow_execution():
    """Test end-to-end workflow execution with stub agents."""
    import asyncio
    from app.graph.workflow import compile_workflow

    graph = compile_workflow()

    initial_state = {
        "query": "What is total revenue?",
        "session_id": "test-session",
        "chat_history": [],
        "route": "",
        "sql_query": "",
        "sql_result": "",
        "rag_result": "",
        "rag_sources": [],
        "final_response": "",
        "error": "",
        "steps_taken": 0,
        "previous_sql_error": "",
        "sql_retries": 0,
    }

    result = asyncio.run(graph.ainvoke(initial_state, config={"recursion_limit": 10}))

    # Graph should have produced a final response
    assert result.get("final_response"), "Workflow should produce a final_response"
    assert result.get("route") in ("sql", "rag", "general", "unknown"), "Route should be a valid category"
    assert result.get("steps_taken", 0) > 0, "Steps should be incremented"
