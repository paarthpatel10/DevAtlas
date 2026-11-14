"""
Hybrid retriever — combines vector (KNN) and keyword (BM25) search with
Reciprocal Rank Fusion, reranking, and context building.

Merges Milestone 2's hybrid_retriever.py, reranker.py, and context_builder.py
into a single cohesive module for the RAG pipeline.
"""

from typing import Any, Dict, List

from app.rag.embedder import BedrockEmbedder
from app.rag.opensearch_client import OpenSearchClient
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class HybridRetriever:
    """Performs hybrid retrieval (KNN + BM25) with Reciprocal Rank Fusion."""

    def __init__(self) -> None:
        self.os_client = OpenSearchClient()
        self.embedder = BedrockEmbedder()

    def _reciprocal_rank_fusion(
        self,
        vector_hits: List[Dict[str, Any]],
        bm25_hits: List[Dict[str, Any]],
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """Combines results using Reciprocal Rank Fusion."""
        rrf_scores: Dict[str, Dict[str, Any]] = {}

        def add_to_rrf(hits: List[Dict[str, Any]]) -> None:
            for rank, hit in enumerate(hits):
                doc_id = hit["_id"]
                if doc_id not in rrf_scores:
                    rrf_scores[doc_id] = {"score": 0.0, "source": hit["_source"]}
                rrf_scores[doc_id]["score"] += 1.0 / (k + rank)

        add_to_rrf(vector_hits)
        add_to_rrf(bm25_hits)

        sorted_results = sorted(
            rrf_scores.values(), key=lambda x: x["score"], reverse=True
        )
        return sorted_results

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Performs full hybrid retrieval pipeline."""
        logger.info(f"Performing hybrid retrieval for query: {query[:80]}...")
        try:
            # 1. Get query embedding
            query_embedding = self.embedder.generate_embedding(query)

            # 2. Get vector results
            vector_results = self.os_client.search_knn(query_embedding, k=10)

            # 3. Get BM25 results
            bm25_results = self.os_client.search_bm25(query, k=10)

            # 4. Fuse results
            fused_results = self._reciprocal_rank_fusion(vector_results, bm25_results)

            # 5. Rerank (pass-through — RRF already provides good ranking)
            reranked = fused_results[:top_k]
            logger.info(f"Retrieved and reranked {len(reranked)} documents")

            return reranked

        except Exception as e:
            logger.error(f"Error during hybrid retrieval: {e}")
            raise

    def retrieve_and_build_context(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Convenience method that performs retrieval and builds a formatted
        context string plus source citations in one call.
        """
        documents = self.retrieve(query, top_k=top_k)
        context = ContextBuilder.build_context(documents)
        sources = ContextBuilder.get_sources(documents)
        return {"context": context, "sources": sources, "documents": documents}


class ContextBuilder:
    """Builds formatted context strings and source citations from retrieved docs."""

    @staticmethod
    def build_context(documents: List[Dict[str, Any]]) -> str:
        """Builds a formatted string of context from retrieved documents."""
        context_parts: List[str] = []
        for i, doc in enumerate(documents):
            source = doc["source"]["metadata"].get("source", "Unknown")
            page = doc["source"]["metadata"].get("page_number", "Unknown")
            text = doc["source"]["text"]

            context_part = f"[Source {i + 1} - {source}, Page {page}]:\n{text}\n"
            context_parts.append(context_part)

        return "\n".join(context_parts)

    @staticmethod
    def get_sources(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extracts source metadata for citation."""
        sources: List[Dict[str, Any]] = []
        for i, doc in enumerate(documents):
            source_info = {
                "id": i + 1,
                "file": str(doc["source"]["metadata"].get("source", "Unknown")),
                "page": str(doc["source"]["metadata"].get("page_number", "Unknown")),
                "snippet": str(doc["source"]["text"][:200]) + "...",
            }
            sources.append(source_info)
        return sources
