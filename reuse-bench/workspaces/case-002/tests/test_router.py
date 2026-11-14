"""
Router classification tests — validates that the router correctly classifies
SQL analytics queries vs. RAG document queries.
"""


def test_router_classifies_revenue_query_as_sql(router_agent):
    """Revenue-related queries should route to SQL."""
    route = router_agent.classify("What is the total revenue this quarter?")
    assert route == "sql"


def test_router_classifies_customer_count_as_sql(router_agent):
    """Customer count queries should route to SQL."""
    route = router_agent.classify("How many customers do we have?")
    assert route == "sql"


def test_router_classifies_top_products_as_sql(router_agent):
    """Top products by sales should route to SQL."""
    route = router_agent.classify("Show me the top 5 products by sales")
    assert route == "sql"


def test_router_classifies_average_order_as_sql(router_agent):
    """Average order value should route to SQL."""
    route = router_agent.classify("What is the average order value?")
    assert route == "sql"


def test_router_classifies_policy_question_as_rag(router_agent):
    """Policy questions should route to RAG."""
    route = router_agent.classify("What is our return policy?")
    assert route == "rag"


def test_router_classifies_document_question_as_rag(router_agent):
    """Document-based questions should route to RAG."""
    route = router_agent.classify("Explain the onboarding process from the handbook")
    assert route == "rag"


def test_router_classifies_concept_question_as_rag(router_agent):
    """Conceptual questions should route to RAG."""
    route = router_agent.classify("How does our product warranty work?")
    assert route == "rag"


def test_router_returns_valid_route_values(router_agent):
    """Router should only return 'sql' or 'rag'."""
    route = router_agent.classify("Some random query")
    assert route in ("sql", "rag")
