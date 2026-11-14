"""
Response Agent — aggregates results from SQL or RAG agents into a final response.
Handles error cases and formats the output for the user.
"""

from typing import Any, Dict

from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


RESPONSE_SYNTHESIS_PROMPT = """You are a helpful data assistant.

Given the user's question and the data/results below, provide a clear, concise,
and well-formatted answer. If the results include numerical data, present it in a
readable format. If there was an error, explain it helpfully.

User Question: {query}

Route: {route}

Results:
{results}

Provide a helpful, natural language response:"""


class ResponseAgent:
    """Synthesizes final responses from agent results."""

    def __init__(self) -> None:
        self.llm = LLMGenerator()

    def synthesize(
        self,
        query: str,
        route: str,
        sql_result: str | None = None,
        rag_result: str | None = None,
        error: str | None = None,
    ) -> str:
        """
        Aggregates SQL or RAG results into a final user-facing response.

        Args:
            query: Original user query.
            route: Which path was taken ('sql' or 'rag').
            sql_result: Formatted SQL results (if SQL path).
            rag_result: RAG-generated response (if RAG path).
            error: Error message, if any.

        Returns:
            Final formatted response string.
        """
        logger.info(f"Response Agent synthesizing answer for route: {route}")

        # Handle error cases
        if error:
            return (
                f"I encountered an issue while processing your request: {error}\n"
                "Please try rephrasing your question or try again later."
            )

        try:
            if route == "sql" and sql_result:
                # For SQL results, use LLM to create a natural language summary
                prompt = RESPONSE_SYNTHESIS_PROMPT.format(
                    query=query,
                    route="SQL Analytics",
                    results=sql_result,
                )
                response = self.llm.invoke_with_prompt(prompt)
                return response

            elif route in ["rag", "general", "unknown"] and rag_result:
                # Natural language results — return directly
                return rag_result

            else:
                return (
                    "I was unable to generate a response for your query. "
                    "Please try rephrasing your question."
                )

        except Exception as e:
            logger.error(f"Response Agent error: {e}", exc_info=True)
            return (
                "I encountered an unexpected error while formatting the response. "
                "Please try again."
            )
