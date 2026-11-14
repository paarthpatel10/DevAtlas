"""
Test configuration and fixtures for the Data Assistant test suite.
Provides stub classes to avoid AWS/3rd-party calls during testing.
Extended from Milestone 2 conftest with assistant-specific stubs.
"""

import os
import sys
import types

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on sys.path so `import app` works during tests
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)


# ── Stub Factory ──────────────────────────────────────────────────────────────


def _make_module(name: str, attrs: dict):
    """Creates a stub module and registers it in sys.modules."""
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


# ── Stub Classes ──────────────────────────────────────────────────────────────


class _BedrockEmbedder:
    def generate_embeddings(self, texts, batch_size=25):
        return [[0.0] * 3 for _ in texts]

    def generate_embedding(self, text):
        return [0.0] * 3


class _RecursiveChunker:
    def chunk_documents(self, pages):
        return []


class _OpenSearchClient:
    def create_index_if_not_exists(self):
        pass

    def index_chunks(self, chunks, embeddings):
        return True

    def search_knn(self, query_embedding, k=5):
        return [
            {
                "_id": "1",
                "_source": {
                    "text": "Test document content about policies.",
                    "metadata": {"source": "doc.pdf", "page_number": 1},
                },
            }
        ]

    def search_bm25(self, query_text, k=5):
        return [
            {
                "_id": "2",
                "_source": {
                    "text": "Another test document about procedures.",
                    "metadata": {"source": "doc.pdf", "page_number": 2},
                },
            }
        ]


class _HybridRetriever:
    def retrieve(self, query, top_k=5):
        return [
            {
                "score": 0.95,
                "source": {
                    "text": "Test document content",
                    "metadata": {"source": "doc.pdf", "page_number": 1},
                },
            }
        ]

    def retrieve_and_build_context(self, query, top_k=5):
        return {
            "context": "[Source 1 - doc.pdf, Page 1]:\nTest document content\n",
            "sources": [
                {"id": 1, "file": "doc.pdf", "page": "1", "snippet": "Test document content..."}
            ],
            "documents": self.retrieve(query, top_k),
        }


class _ContextBuilder:
    @staticmethod
    def build_context(documents):
        """Real implementation for testing."""
        context_parts = []
        for i, doc in enumerate(documents):
            source = doc["source"]["metadata"].get("source", "Unknown")
            page = doc["source"]["metadata"].get("page_number", "Unknown")
            text = doc["source"]["text"]
            context_part = f"[Source {i + 1} - {source}, Page {page}]:\n{text}\n"
            context_parts.append(context_part)
        return "\n".join(context_parts)

    @staticmethod
    def get_sources(documents):
        """Real implementation for testing."""
        sources = []
        for i, doc in enumerate(documents):
            source_info = {
                "id": i + 1,
                "file": str(doc["source"]["metadata"].get("source", "Unknown")),
                "page": str(doc["source"]["metadata"].get("page_number", "Unknown")),
                "snippet": str(doc["source"]["text"][:200]) + "...",
            }
            sources.append(source_info)
        return sources


class _LLMGenerator:
    def __init__(self):
        pass

    def generate_response(self, query, context, chat_history):
        if "needsource" in query:
            return "This is an answer. [Source 1]"
        if "greeting" in query:
            return "Hi there!"
        return "Generic answer"

    def invoke_with_prompt(self, prompt):
        # Router classification — extract user query from prompt
        if "query classifier" in prompt.lower() or "classification" in prompt.lower():
            # Extract the actual user query (after "User Query:" line)
            user_query = ""
            if "User Query:" in prompt:
                user_query = prompt.split("User Query:")[-1].split("\n")[0].strip().lower()

            # SQL keywords in the USER's query (not in the system prompt examples)
            sql_keywords = ["revenue", "sales", "orders", "average", "total", "count",
                           "how many", "top 5", "top 10", "sum", "list all products"]
            if any(kw in user_query for kw in sql_keywords):
                return "sql"
            return "rag"

        # SQL generation
        if "sql query generator" in prompt.lower():
            return "```sql\nSELECT * FROM customers LIMIT 10;\n```"

        # Response synthesis
        if "data assistant" in prompt.lower():
            return "Based on the data, here are the results."

        return "Generated response"


class _DynamoDBMemory:
    def __init__(self):
        self._store = {}

    def get_history(self, session_id, limit=5):
        return self._store.get(session_id, [])

    def add_message(self, session_id, role, content):
        self._store.setdefault(session_id, []).append(
            {"role": role, "content": content}
        )


class _SchemaIntrospector:
    def get_tables(self):
        return ["customers", "products", "orders", "sales"]

    def get_columns(self, table_name):
        schemas = {
            "customers": [
                {"column_name": "customer_id", "data_type": "integer", "is_nullable": "NO", "column_default": None},
                {"column_name": "first_name", "data_type": "character varying", "is_nullable": "NO", "column_default": None},
            ],
            "products": [
                {"column_name": "product_id", "data_type": "integer", "is_nullable": "NO", "column_default": None},
                {"column_name": "product_name", "data_type": "character varying", "is_nullable": "NO", "column_default": None},
            ],
            "orders": [
                {"column_name": "order_id", "data_type": "integer", "is_nullable": "NO", "column_default": None},
            ],
            "sales": [
                {"column_name": "sale_id", "data_type": "integer", "is_nullable": "NO", "column_default": None},
            ],
        }
        return schemas.get(table_name, [])

    def get_full_schema(self, use_cache=True):
        tables = self.get_tables()
        return [{"table_name": t, "columns": self.get_columns(t)} for t in tables]

    def format_schema_for_prompt(self, use_cache=True):
        return "TABLE customers (\n    customer_id integer NOT NULL\n)"

    @staticmethod
    def clear_cache():
        pass


class _SQLExecutor:
    def execute(self, sql_query):
        return {
            "success": True,
            "columns": ["customer_id", "first_name"],
            "rows": [{"customer_id": 1, "first_name": "Alice"}],
            "row_count": 1,
            "error": None,
        }

    def format_results_as_text(self, result):
        if not result["success"]:
            return f"Error: {result['error']}"
        return "customer_id | first_name\n-----------\n1 | Alice\n\nTotal rows: 1"


class _FakeChatBedrock:
    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, prompt):
        class R:
            content = "fake"
        return R()


class _FakeEngine:
    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        return []


# ── Stub boto3 ────────────────────────────────────────────────────────────────

import boto3


def _fake_boto3_client(service_name, region_name=None):
    return object()


boto3.client = _fake_boto3_client


# Stub pypdf to avoid PdfStreamError on fake PDF content in upload tests
class _FakePdfPage:
    def extract_text(self):
        return "Fake page content for testing."


class _FakePdfReader:
    def __init__(self, *args, **kwargs):
        self.pages = [_FakePdfPage()]


_make_module("pypdf", {"PdfReader": _FakePdfReader})


# ── Register Stub Modules ────────────────────────────────────────────────────

_make_module("langchain_aws", {"ChatBedrock": _FakeChatBedrock, "BedrockEmbeddings": lambda **kwargs: None})

# RAG stubs
_make_module("app.rag.embedder", {"BedrockEmbedder": _BedrockEmbedder})
_make_module("app.rag.chunker", {"RecursiveChunker": _RecursiveChunker})
_make_module("app.rag.opensearch_client", {"OpenSearchClient": _OpenSearchClient})
_make_module("app.rag.retriever", {
    "HybridRetriever": _HybridRetriever,
    "ContextBuilder": _ContextBuilder,
})
_make_module("app.rag.generator", {"LLMGenerator": _LLMGenerator})

# Memory stubs
_make_module("app.memory.dynamodb_memory", {"DynamoDBMemory": _DynamoDBMemory})

# Database stubs
_make_module("app.database.postgres", {
    "get_engine": lambda: _FakeEngine(),
    "get_db_session": lambda: None,
    "test_connection": lambda: True,
})
_make_module("app.database.schema_introspector", {"SchemaIntrospector": _SchemaIntrospector})
_make_module("app.database.sql_executor", {"SQLExecutor": _SQLExecutor})

# Observability stubs
_make_module("app.observability.langsmith_client", {"configure_langsmith": lambda: None, "get_langsmith_client": lambda: None})


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FastAPI test client with all external services stubbed."""
    from app.api.main import app
    return TestClient(app)


@pytest.fixture
def router_agent():
    """Pre-initialized RouterAgent using stub LLM."""
    from app.agents.router_agent import RouterAgent
    return RouterAgent()
