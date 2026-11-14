"""
Bedrock Embedder — generates text embeddings using AWS Bedrock.
Refactored from Milestone 2 ingestion/embedder.py for reuse in the RAG pipeline.
"""

from typing import List

import boto3
from langchain_aws import BedrockEmbeddings

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class BedrockEmbedder:
    """Generates embeddings via AWS Bedrock embedding models."""

    def __init__(self) -> None:
        bedrock_client = boto3.client(
            "bedrock-runtime", region_name=settings.AWS_REGION
        )
        self.embeddings = BedrockEmbeddings(
            client=bedrock_client,
            model_id=settings.BEDROCK_EMBEDDING_MODEL,
        )

    def generate_embeddings(
        self, texts: List[str], batch_size: int = 25
    ) -> List[List[float]]:
        """Generates embeddings for a list of texts using AWS Bedrock in batches."""
        logger.info(
            f"Generating embeddings for {len(texts)} chunks in batches of {batch_size}"
        )
        try:
            all_embeddings: List[List[float]] = []
            total_batches = (len(texts) + batch_size - 1) // batch_size

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                batch_num = i // batch_size + 1
                logger.info(f"Processing embedding batch {batch_num}/{total_batches}")
                batch_embeddings = self.embeddings.embed_documents(batch)
                all_embeddings.extend(batch_embeddings)

            return all_embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise

    def generate_embedding(self, text: str) -> List[float]:
        """Generates embedding for a single text query."""
        try:
            return self.embeddings.embed_query(text)
        except Exception as e:
            logger.error(f"Error generating embedding for query: {e}")
            raise
