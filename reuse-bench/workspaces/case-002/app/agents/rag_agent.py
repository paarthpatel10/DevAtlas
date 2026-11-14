"""
RAG Agent — handles knowledge/document queries by delegating to the RAG pipeline.
Reuses the retriever and generator modules from the rag/ package.
"""

from typing import Any, Dict, List

from app.prompts.strict_rag_prompt import build_strict_rag_prompt
from app.rag.generator import LLMGenerator
from app.rag.retriever import HybridRetriever
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class RAGAgent:
    """Processes document/knowledge queries using the RAG pipeline."""

    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.llm = LLMGenerator()

    def run(self, query: str, chat_history: list | None = None) -> Dict[str, Any]:
        """
        Processes a knowledge query end-to-end:
        1. Retrieve relevant documents
        2. Build context
        3. Generate response via LLM

        Returns:
            dict with keys: answer, sources, success, error
        """
        logger.info(f"RAG Agent processing query: {query[:80]}...")

        try:
            # Step 1 & 2: Retrieve and build context
            retrieval_result = self.retriever.retrieve_and_build_context(
                query, top_k=5
            )
            context = retrieval_result["context"]
            sources = retrieval_result["sources"]

            # Step 3: Generate response with strict RAG prompt
            prompt = build_strict_rag_prompt(
                user_query=query,
                context=context,
                chat_history=chat_history or [],
            )
            answer = self.llm.invoke_with_prompt(prompt)

            # If the LLM didn't use sources (e.g. for greetings), clear them
            if "[Source" not in answer:
                sources = []

            logger.info("RAG Agent response generated successfully")
            return {
                "answer": answer,
                "sources": sources,
                "success": True,
                "error": None,
            }

        except Exception as e:
            logger.error(f"RAG Agent error: {e}", exc_info=True)
            return {
                "answer": f"An error occurred while searching documents: {str(e)}",
                "sources": [],
                "success": False,
                "error": str(e),
            }
