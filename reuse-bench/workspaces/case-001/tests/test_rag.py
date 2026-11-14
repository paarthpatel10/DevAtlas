"""
RAG pipeline tests — verifies retrieval, context building, and generation
with mocked OpenSearch.
"""


def test_retriever_returns_documents():
    """Test that the hybrid retriever returns documents."""
    from app.rag.retriever import HybridRetriever

    retriever = HybridRetriever()
    results = retriever.retrieve("test query", top_k=5)
    assert isinstance(results, list)
    assert len(results) > 0


def test_retriever_returns_context_and_sources():
    """Test that retrieve_and_build_context returns both context and sources."""
    from app.rag.retriever import HybridRetriever

    retriever = HybridRetriever()
    result = retriever.retrieve_and_build_context("test query", top_k=5)

    assert "context" in result
    assert "sources" in result
    assert "documents" in result
    assert isinstance(result["context"], str)
    assert isinstance(result["sources"], list)


def test_context_builder_builds_context():
    """Test that ContextBuilder formats documents into a context string."""
    from app.rag.retriever import ContextBuilder

    documents = [
        {
            "source": {
                "text": "Sample text content",
                "metadata": {"source": "test.pdf", "page_number": 1},
            }
        }
    ]

    context = ContextBuilder.build_context(documents)
    assert "Source 1" in context
    assert "test.pdf" in context
    assert "Sample text content" in context


def test_context_builder_extracts_sources():
    """Test that ContextBuilder extracts source metadata."""
    from app.rag.retriever import ContextBuilder

    documents = [
        {
            "source": {
                "text": "Sample text content for source extraction test",
                "metadata": {"source": "report.pdf", "page_number": 3},
            }
        }
    ]

    sources = ContextBuilder.get_sources(documents)
    assert len(sources) == 1
    assert sources[0]["file"] == "report.pdf"
    assert sources[0]["page"] == "3"
    assert sources[0]["id"] == 1


def test_generator_produces_response():
    """Test that the LLM generator produces a response string."""
    from app.rag.generator import LLMGenerator

    generator = LLMGenerator()
    response = generator.generate_response(
        query="What is this about?",
        context="Some context text",
        chat_history=[],
    )
    assert isinstance(response, str)
    assert len(response) > 0


def test_generator_invoke_with_prompt():
    """Test that invoke_with_prompt works with raw prompts."""
    from app.rag.generator import LLMGenerator

    generator = LLMGenerator()
    response = generator.invoke_with_prompt("Tell me something")
    assert isinstance(response, str)
    assert len(response) > 0
