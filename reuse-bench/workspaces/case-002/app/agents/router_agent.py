"""
Router Agent — classifies user queries as either 'sql' or 'rag'.
Uses the LLM with a classification prompt to determine the routing path.
"""

from app.prompts.router_prompt import build_router_prompt
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


GREETING_PATTERNS = {
    "hi", "hello", "hey", "howdy", "greetings", "good morning",
    "good afternoon", "good evening", "thanks", "thank you",
    "bye", "goodbye", "see you", "how are you", "what's up",
    "sup", "yo", "hola", "namaste",
}


class RouterAgent:
    """Classifies queries to determine the appropriate processing path."""

    def __init__(self) -> None:
        self.llm = LLMGenerator()

    @staticmethod
    def _is_greeting(query: str) -> bool:
        """Fast local check for greetings/small talk — no LLM needed."""
        cleaned = query.strip().lower().rstrip("!?.,:;")
        return cleaned in GREETING_PATTERNS

    def classify(self, query: str, chat_history: list | None = None) -> str:
        """
        Classifies a user query as 'sql' or 'rag'.

        Args:
            query: The user's natural language query.
            chat_history: Optional conversation history for context.

        Returns:
            'sql' for analytics/database queries, 'rag' for document queries.
        """
        logger.info(f"Router classifying query: {query[:80]}...")

        # Fast-path: greetings always go to RAG (no LLM call needed)
        if self._is_greeting(query):
            logger.info("Query is a greeting — routing to 'rag'")
            return "rag"

        try:
            prompt = build_router_prompt(query, chat_history)
            response = self.llm.invoke_with_prompt(prompt)

            # Extract classification from response
            classification = response.strip().lower()

            # Normalize — only accept 'sql' or 'rag'
            if "sql" in classification:
                route = "sql"
            elif "rag" in classification:
                route = "rag"
            else:
                # Default to RAG if classification is unclear
                logger.warning(
                    f"Unclear classification '{classification}', defaulting to 'rag'"
                )
                route = "rag"

            logger.info(f"Query classified as: {route}")
            return route

        except Exception as e:
            logger.error(f"Router classification error: {e}", exc_info=True)
            # Default to RAG on error — safer than potentially generating SQL
            logger.info("Defaulting to 'rag' due to classification error")
            return "rag"
