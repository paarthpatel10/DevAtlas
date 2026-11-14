"""
Recursive text chunker — splits documents into semantically meaningful chunks.
Refactored from Milestone 2 ingestion/chunker.py for reuse in the RAG pipeline.
"""

from typing import Any, Dict, List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class RecursiveChunker:
    """Splits document pages into smaller overlapping chunks for embedding."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            separators=["\n\n", "\n", " ", ""],
        )

    def chunk_documents(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Splits pages into smaller, semantically meaningful chunks.
        Preserves metadata from the original page.
        """
        logger.info(f"Chunking {len(pages)} pages")
        all_chunks: List[Dict[str, Any]] = []

        try:
            for page in pages:
                chunks = self.text_splitter.split_text(page["text"])

                for i, chunk in enumerate(chunks):
                    chunk_metadata = page["metadata"].copy()
                    chunk_metadata["chunk_index"] = i

                    all_chunks.append({"text": chunk, "metadata": chunk_metadata})

            logger.info(f"Created {len(all_chunks)} chunks total")
            return all_chunks

        except Exception as e:
            logger.error(f"Error during chunking: {e}")
            raise
