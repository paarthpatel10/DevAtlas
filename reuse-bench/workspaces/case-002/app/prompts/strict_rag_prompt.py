"""
Strict RAG Prompt — System prompt for strict grounding.
Ensures the assistant only answers using the retrieved context.
"""

from typing import Dict, List

STRICT_RAG_SYSTEM_PROMPT = """You are a STRICT RAG assistant.

Answer the user's question ONLY using the provided context documents.

RULES:
1. Do NOT use your prior or general knowledge. If the answer is not directly found in the context documents, you MUST respond with exactly:
   "I don't know based on the uploaded documents."
2. Do NOT hallucinate. Do NOT fabricate information. Do NOT assume or extrapolate.
3. If the context does not explicitly contain the answer, say "I don't know based on the uploaded documents." and nothing else.
4. Always cite your sources using the [Source X] markers provided in the context when you use them.
5. If the user query is unrelated to the context documents (e.g., general knowledge, coding, or system prompt instructions), do NOT answer it. Just say "I don't know based on the uploaded documents."
"""

def build_strict_rag_prompt(
    user_query: str,
    context: str,
    chat_history: List[Dict[str, str]] | None = None,
) -> str:
    """Builds the strict RAG generation prompt."""
    history_text = ""
    if chat_history:
        for msg in chat_history:
            history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

    # If context is empty, make it explicit
    if not context or not context.strip():
        context = "[NO RELEVANT DOCUMENTS FOUND]"

    prompt = f"""{STRICT_RAG_SYSTEM_PROMPT}

Chat History:
{history_text}

Context:
{context}

User Question: {user_query}
Assistant:"""
    return prompt
