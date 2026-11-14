"""
Semantic Router Agent — routes user queries to sql, rag, general, or unknown paths.
Uses a lightweight LLM classifier to evaluate intent and confidence score.
"""

import json
from typing import Any, Dict, List
from app.rag.generator import LLMGenerator
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

ROUTER_SYSTEM_PROMPT = """You are a highly accurate Semantic Router for an AI Data Assistant.
Your job is to classify the user's query into one of the following intent categories and provide a confidence score between 0.0 and 1.0.

Categories:
1. "sql" - Queries asking for data analytics, metrics, lists of records, totals, averages, or database stats (e.g. from tables like customers, products, sales, orders). ALSO includes conceptual queries about the database schema/metadata (e.g., "what is customer?", "describe the sales table").
2. "rag" - ANY informational, factual, technical, coding, or knowledge-based questions (e.g. "what is git?", "tell me weather of delhi", "explain RAG", "how does parent retriever work?", "what is FastAPI?", "explain return policy"). Any question seeking information or facts must be routed to "rag" to be verified against the uploaded document database.
3. "general" - Greetings, introductions, and casual social small talk ONLY (e.g., "hello", "hi", "how are you?", "good morning"). Do NOT route factual or informational queries here.
4. "unknown" - Nonsense, extremely vague queries, or ambiguous phrases (e.g., "adsfadsf", "go", "what?").

You MUST return your answer in JSON format containing the keys:
- "route": One of the string values: "sql", "rag", "general", "unknown"
- "confidence": A float value between 0.0 and 1.0 representing your routing confidence
- "explanation": A brief 1-sentence reason for this decision

Example Outputs:
- For "What is the total revenue in NY?":
  {"route": "sql", "confidence": 0.95, "explanation": "Asking for sales revenue which requires database querying."}
- For "What is customer?":
  {"route": "sql", "confidence": 0.90, "explanation": "Asking for metadata explanation of the customer table/entity."}
- For "Explain return policy":
  {"route": "rag", "confidence": 0.98, "explanation": "Asking about company documentation/policy."}
- For "What is git?":
  {"route": "rag", "confidence": 0.95, "explanation": "Factual question about Git, must be verified against the document database."}
- For "What is RAG?":
  {"route": "rag", "confidence": 0.95, "explanation": "Asking about RAG, must be verified against the document database."}
- For "hello":
  {"route": "general", "confidence": 0.99, "explanation": "Standard greeting."}
- For "how are you?":
  {"route": "general", "confidence": 0.95, "explanation": "Conversational small talk."}
- For "xyz":
  {"route": "unknown", "confidence": 0.90, "explanation": "Gibberish or highly ambiguous input."}

Do NOT output any text before or after the JSON object.
"""

class SemanticRouter:
    """Uses LLM to classify user query into sql, rag, general, or unknown routes with confidence scores."""

    def __init__(self, confidence_threshold: float = 0.65) -> None:
        self.llm = LLMGenerator()
        self.confidence_threshold = confidence_threshold

    def route(self, query: str, chat_history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
        """
        Routes the query.
        VIVA-READY COMMENTS:
        - Why semantic routing is better: Traditional keyword-based routing fails on queries like
          'tell me weather of delhi' (which might default incorrectly)
          or 'what is customer?' (which gets routed to RAG but belongs to SQL schema metadata).
          LLM-based semantic routing understands conceptual meaning and linguistic intent.
        - Why confidence thresholds improve safety: Forcing a fallback to 'unknown' when confidence is low (< 0.65)
          prevents the assistant from executing dangerous, hallucinated SQL queries or answering RAG questions incorrectly,
          protecting downstream agents and improving user trust.
        """
        logger.info(f"Semantic routing for query: {query[:60]}")

        # Format history context
        history_text = ""
        if chat_history:
            for msg in chat_history:
                history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

        prompt = f"""{ROUTER_SYSTEM_PROMPT}

Chat History:
{history_text}

User Query: {query}
JSON Output:"""

        try:
            raw_response = self.llm.invoke_with_prompt(prompt)
            cleaned_response = raw_response.strip()

            # Clean JSON markdown if present
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            data = json.loads(cleaned_response)
            route = data.get("route", "unknown").lower()
            confidence = float(data.get("confidence", 0.5))

            logger.info(f"LLM Routing Output: route={route}, confidence={confidence}")

            # Apply confidence threshold safety check
            if confidence < self.confidence_threshold:
                logger.warning(
                    f"Routing confidence {confidence} is below threshold {self.confidence_threshold}. "
                    f"Overriding route '{route}' to 'unknown'."
                )
                route = "unknown"

            # Validate route values
            if route not in ["sql", "rag", "general", "unknown"]:
                logger.warning(f"Invalid route returned: '{route}'. Defaulting to 'unknown'.")
                route = "unknown"

            return {
                "route": route,
                "confidence": confidence,
                "explanation": data.get("explanation", "Default fallback")
            }

        except Exception as e:
            logger.error(f"Error in semantic routing: {e}", exc_info=True)
            # Default fallback for extreme safety
            return {
                "route": "unknown",
                "confidence": 1.0,
                "explanation": f"Routing failed due to internal error: {e}"
            }
