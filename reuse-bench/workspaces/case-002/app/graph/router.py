"""
Router Node wrapper for LangGraph.
Calls the SemanticRouter and returns routing decision.
"""

from typing import Any, Dict
from app.agents.semantic_router import SemanticRouter
from app.graph.state import GraphState
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

async def run_semantic_router(state: GraphState) -> Dict[str, Any]:
    """
    Executes the semantic router to classify the query.
    Sets state['route'] to 'sql', 'rag', 'general', or 'unknown'.
    """
    logger.info("=== Executing Semantic Router ===")
    
    query = state["query"]
    chat_history = state.get("chat_history", [])
    
    router = SemanticRouter()
    routing_result = router.route(query, chat_history)
    
    logger.info(f"Semantic Routing Decision: {routing_result}")
    
    return {
        "route": routing_result["route"],
        "error": ""
    }
