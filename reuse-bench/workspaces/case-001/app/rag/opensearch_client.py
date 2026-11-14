"""
OpenSearch client — manages connection, index creation, and document indexing.
Refactored from Milestone 2 ingestion/opensearch_indexer.py.
Combines connection management and indexing into a single reusable client.
"""

from typing import Any, Dict, List

from opensearchpy import OpenSearch, helpers

from app.config.settings import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class OpenSearchClient:
    """Manages OpenSearch connection, index lifecycle, and bulk indexing."""

    def __init__(self) -> None:
        self.client = OpenSearch(
            hosts=[
                {"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}
            ],
            http_compress=True,
            http_auth=(settings.OPENSEARCH_USERNAME, settings.OPENSEARCH_PASSWORD),
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
            ssl_assert_hostname=False,
            ssl_show_warn=False,
        )
        self.index_name = settings.OPENSEARCH_INDEX_NAME

    def create_index_if_not_exists(self) -> None:
        """Creates the OpenSearch index with KNN vector support if it doesn't exist."""
        if not self.client.indices.exists(index=self.index_name):
            logger.info(f"Creating OpenSearch index: {self.index_name}")

            index_body = {
                "settings": {
                    "index": {
                        "knn": True,
                        "knn.algo_param.ef_search": 100,
                    }
                },
                "mappings": {
                    "properties": {
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": settings.EMBEDDING_DIMENSION,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "lucene",
                            },
                        },
                        "text": {"type": "text"},
                        "metadata": {
                            "properties": {
                                "source": {"type": "keyword"},
                                "page_number": {"type": "integer"},
                                "chunk_index": {"type": "integer"},
                            }
                        },
                    }
                },
            }

            self.client.indices.create(index=self.index_name, body=index_body)
            logger.info(f"Index {self.index_name} created successfully.")
        else:
            logger.info(f"Index {self.index_name} already exists.")

    def index_chunks(
        self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]
    ) -> None:
        """Indexes text chunks and their embeddings into OpenSearch."""
        self.create_index_if_not_exists()

        logger.info(f"Indexing {len(chunks)} chunks to OpenSearch")

        actions = []
        for i, chunk in enumerate(chunks):
            action = {
                "_index": self.index_name,
                "_source": {
                    "text": chunk["text"],
                    "embedding": embeddings[i],
                    "metadata": chunk["metadata"],
                },
            }
            actions.append(action)

        try:
            success, failed = helpers.bulk(self.client, actions)
            logger.info(f"Successfully indexed {success} documents. Failed: {failed}")
        except Exception as e:
            logger.error(f"Error indexing to OpenSearch: {e}")
            raise

    def search_knn(
        self, query_embedding: List[float], k: int = 5
    ) -> List[Dict[str, Any]]:
        """Performs KNN vector search."""
        query = {
            "size": k,
            "query": {"knn": {"embedding": {"vector": query_embedding, "k": k}}},
        }
        response = self.client.search(index=self.index_name, body=query)
        return response["hits"]["hits"]

    def search_bm25(self, query_text: str, k: int = 5) -> List[Dict[str, Any]]:
        """Performs BM25 text search."""
        query = {
            "size": k,
            "query": {"match": {"text": query_text}},
        }
        response = self.client.search(index=self.index_name, body=query)
        return response["hits"]["hits"]
