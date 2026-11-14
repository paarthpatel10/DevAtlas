"""
API endpoint tests — preserves Milestone 2 tests and adds Milestone 3 assistant tests.
"""


# ══════════════════════════════════════════════════════════════════════════════
# MILESTONE 2 TESTS (Preserved)
# ══════════════════════════════════════════════════════════════════════════════


def test_health_check(client):
    """Test that the health endpoint returns ok."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ask_returns_sources_when_llm_includes_source_marker(client):
    """Test that sources are returned when the LLM response includes [Source] markers."""
    payload = {"query": "please needsource", "session_id": "sess1"}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert len(data["sources"]) >= 1


def test_ask_greeting_removes_sources(client):
    """Test that greeting responses have empty sources list."""
    payload = {"query": "simple greeting", "session_id": "sess2"}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["sources"] == []


def test_upload_pdf_success(client):
    """Test that uploading a valid PDF file succeeds."""
    fake_pdf_content = b"%PDF-1.4 fake content for testing"
    resp = client.post(
        "/upload",
        files={"file": ("test.pdf", fake_pdf_content, "application/pdf")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "chunks" in data


def test_upload_non_pdf_rejected(client):
    """Test that non-PDF files are rejected with 400."""
    resp = client.post(
        "/upload",
        files={"file": ("test.txt", b"hello world", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]


def test_upload_oversized_file_rejected(client, monkeypatch):
    """Test that files exceeding the size limit are rejected with 413."""
    from app.api import main

    monkeypatch.setattr(main, "MAX_UPLOAD_SIZE_BYTES", 10)

    resp = client.post(
        "/upload",
        files={"file": ("big.pdf", b"x" * 100, "application/pdf")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_get_history_empty_session(client):
    """Test that fetching history for an unknown session returns empty list."""
    resp = client.get("/history/nonexistent-session-id")
    assert resp.status_code == 200
    assert resp.json()["history"] == []


def test_ask_stores_history(client):
    """Test that asking a question stores messages in memory."""
    session = "test-history-session"

    client.post("/ask", json={"query": "greeting hello", "session_id": session})

    resp = client.get(f"/history/{session}")
    assert resp.status_code == 200
    history = resp.json()["history"]
    assert len(history) >= 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_ask_missing_query_returns_422(client):
    """Test that missing required fields return a validation error."""
    resp = client.post("/ask", json={"session_id": "sess"})
    assert resp.status_code == 422


def test_ask_missing_session_id_returns_422(client):
    """Test that missing session_id returns a validation error."""
    resp = client.post("/ask", json={"query": "hello"})
    assert resp.status_code == 422


def test_error_messages_are_sanitized(client):
    """Test that error responses don't leak internal implementation details."""
    resp = client.post(
        "/upload",
        files={"file": ("test.docx", b"fake", "application/octet-stream")},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Traceback" not in detail


# ══════════════════════════════════════════════════════════════════════════════
# MILESTONE 3 TESTS (New)
# ══════════════════════════════════════════════════════════════════════════════


def test_assistant_endpoint_exists(client):
    """Test that the /assistant endpoint exists and accepts POST requests."""
    payload = {"query": "How many customers do we have?", "session_id": "assistant-test"}
    resp = client.post("/assistant", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "route" in data


def test_assistant_returns_route(client):
    """Test that the assistant response includes the routing decision."""
    payload = {"query": "What is total revenue?", "session_id": "assistant-route-test"}
    resp = client.post("/assistant", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["route"] in ("sql", "rag", "general", "unknown")


def test_assistant_missing_query_returns_422(client):
    """Test that missing query field returns validation error."""
    resp = client.post("/assistant", json={"session_id": "sess"})
    assert resp.status_code == 422


def test_assistant_missing_session_id_returns_422(client):
    """Test that missing session_id returns validation error."""
    resp = client.post("/assistant", json={"query": "hello"})
    assert resp.status_code == 422


def test_assistant_health_endpoint(client):
    """Test the assistant-specific health endpoint."""
    resp = client.get("/assistant/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "max_graph_steps" in data
