"""
Unknown Intent Handler Agent — handles ambiguous, low confidence, or unsupported queries.
Provides graceful fallback and asks for clarification.
"""

from typing import Any, Dict, List
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

UNKNOWN_SYSTEM_PROMPT = """You are an Unknown Intent Handler for the Data Assistant.
The user's query could not be reliably routed to the SQL database agent, RAG document agent, or General small talk node.
This happens if the query is too vague, ambiguous, contains nonsense, or asks for things not supported by the system.

GUIDELINES:
1. Do NOT try to answer the query or hallucinate details.
2. Politely explain that you did not quite understand the query or that it is outside your current capabilities.
3. Gracefully ask the user for clarification.
4. Give brief examples of what the user CAN ask:
   - Database analytics (e.g. "What is our total revenue?", "List our top 5 products")
   - Uploaded documents (e.g. "Explain our return policy", "How does onboarding work?")
5. Keep the response concise and helpful.

VIVA-READY COMMENTS:
- Why fallback nodes matter: Ensures that queries with low routing confidence (threshold < 0.65) or complete gibberish
  are intercepted before they reach downstream logic. This prevents database queries from crashing and avoids RAG hallucinations.
"""

class UnknownHandler:
    """Handles low confidence or ambiguous user queries with graceful clarification prompts."""

    def __init__(self) -> None:
        self.llm = LLMGenerator()

    def run(self, query: str, chat_history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
        """
        Runs the unknown handler.
        """
        logger.info(f"Unknown Handler running for query: {query[:60]}")

        history_text = ""
        if chat_history:
            for msg in chat_history:
                history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

        prompt = f"""{UNKNOWN_SYSTEM_PROMPT}

Chat History:
{history_text}

User Query: {query}
Assistant:"""

        try:
            response = self.llm.invoke_with_prompt(prompt)
            return {
                "answer": response.strip(),
                "success": True,
                "error": None
            }
        except Exception as e:
            logger.error(f"Error in Unknown Handler: {e}", exc_info=True)
            fallback_msg = (
                "I'm sorry, but I couldn't understand your question. "
                "I can help you with database analytics (e.g. sales, orders) "
                "or questions about uploaded documents. Could you please clarify or rephrase your question?"
            )
            return {
                "answer": fallback_msg,
                "success": False,
                "error": str(e)
            }
