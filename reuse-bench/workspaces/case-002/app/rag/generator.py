"""
LLM Generator — generates responses using AWS Bedrock LLMs.
Refactored from Milestone 2 llm/generator.py for reuse in the RAG pipeline.
"""

from typing import Any, Dict, List

import boto3
from langchain_aws import ChatBedrock

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMGenerator:
    """Generates LLM responses using AWS Bedrock models."""

    def __init__(self) -> None:
        bedrock_runtime = boto3.client(
            "bedrock-runtime", region_name=settings.AWS_REGION
        )
        self.llm = ChatBedrock(
            client=bedrock_runtime,
            model=settings.BEDROCK_LLM_MODEL,
            model_kwargs={"temperature": 0.0, "max_tokens": 1024},
        )

    def generate_response(
        self,
        query: str,
        context: str,
        chat_history: List[Dict[str, str]],
    ) -> str:
        """
        Generates a response using the LLM given the query, context, and chat history.
        """
        logger.info("Generating LLM response")

        system_prompt = (
            "You are a helpful and knowledgeable AI assistant. "
            "If the user is just greeting you or making conversational small talk "
            "(like 'hi', 'hello'), respond naturally without referencing the context documents. "
            "For all other questions, use the provided context to answer. "
            "If the answer is not contained in the context, say "
            "'I don't have enough information to answer that based on the provided documents.' "
            "Do not make up information. Always cite your sources using the [Source X] markers "
            "provided in the context when you use them."
        )

        # Format history
        history_text = ""
        if chat_history:
            for msg in chat_history:
                history_text += f"{msg['role'].capitalize()}: {msg['content']}\n"

        full_prompt = f"""{system_prompt}

Chat History:
{history_text}

Context:
{context}

User Question: {query}
Assistant:"""

        try:
            response = self.llm.invoke(full_prompt)
            return response.content
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            raise

    def invoke_with_prompt(self, prompt: str) -> str:
        """
        Invokes the LLM with a raw prompt string.
        Used by agents that build their own prompt templates.
        """
        logger.info("Invoking LLM with custom prompt")
        try:
            response = self.llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"Error invoking LLM: {e}")
            raise
