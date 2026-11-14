"""
Response Formatter Agent — refines and formats user responses.
Ensures consistency, correct markdown tables, concise styling, and token limits.
"""

from typing import Dict, Any, List
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

FORMATTER_SYSTEM_PROMPT = """You are a professional Response Formatter for an AI Data Assistant.
Your job is to refine and format the assistant's final response to be extremely professional, clean, concise, and structured.

RULES:
1. Ensure all tabular data is formatted as clean Markdown tables.
2. Ensure bulleted lists are properly indented and use clear bullet characters (- or *).
3. Make the response highly readable, highlighting key metrics or numbers in **bold**.
4. Remove unnecessary wordiness or conversational filler. Keep the response direct and focused.
5. Do NOT change the facts, numbers, or sources in the response.
6. The maximum output length should be concise and fit within a professional dashboard (under 300 words).
7. If the answer is an error, present it in a clean error format block.

VIVA-READY COMMENTS:
- Why formatting layer is critical: In enterprise assistant applications, response presentation is as vital
  as accuracy. Raw agent responses are often verbose or contain malformed tables. A separate post-processing formatter
  normalizes the output into clean, structured Markdown, enhancing readability and ensuring consistent UI/UX.
"""

class ResponseFormatter:
    """Formats and styles the final agent output for consistent presentation and readability."""

    def __init__(self) -> None:
        self.llm = LLMGenerator()

    def format(self, query: str, raw_response: str) -> str:
        """
        Formats the response.
        """
        logger.info("Formatting response...")

        prompt = f"""{FORMATTER_SYSTEM_PROMPT}

User Question: {query}
Raw Agent Response: {raw_response}

Clean Formatted Response:"""

        try:
            response = self.llm.invoke_with_prompt(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Error in Response Formatter: {e}", exc_info=True)
            # If formatting fails, fallback to the raw response to avoid data loss
            return raw_response
