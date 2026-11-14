"""
General Agent — handles greetings, casual small talk, weather queries, and general conversation.
"""

from typing import Any, Dict, List
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

GENERAL_SYSTEM_PROMPT = """You are a polite, warm, and helpful conversational assistant for the Data Assistant.
You handle general greetings, introductions, and casual social small talk (e.g. "hello", "hi", "how are you?").

GUIDELINES:
1. Be extremely concise, warm, and helpful.
2. Direct the user to ask about database analytics (metrics, revenue, customer orders) or uploaded documents (handbooks, return policies).
3. Do NOT attempt to answer factual, technical, coding, or informational queries. (If the query is informational, tell the user you are here for greetings and database/document search).
4. Keep the tone friendly and direct.

VIVA-READY COMMENTS:
- Why general conversation handling is key: Prevents casual greetings or social small talk from triggering RAG searches or SQL operations, improving efficiency and responsiveness. Factual questions are routed to RAG/SQL for strict grounding.
"""

class GeneralAgent:
    """Handles general conversational small talk, greetings, and weather queries."""

    def __init__(self) -> None:
        self.llm = LLMGenerator()

    def run(self, query: str, chat_history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
        """
        Runs the general agent.
        """
        logger.info(f"General Agent running for query: {query[:60]}")

        history_text = ""
        if chat_history:
            for msg in chat_history:
                history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

        prompt = f"""{GENERAL_SYSTEM_PROMPT}

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
            logger.error(f"Error in General Agent: {e}", exc_info=True)
            return {
                "answer": "Hello! I am here to help. How can I assist you today?",
                "success": False,
                "error": str(e)
            }
