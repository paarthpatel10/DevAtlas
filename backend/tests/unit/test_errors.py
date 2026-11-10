def test_unknown_route_uses_error_schema(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"


def test_unhandled_exception_hides_internals(client_with_boom_route):
    r = client_with_boom_route.get("/boom")
    assert r.status_code == 500
    assert r.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": None,
        }
    }
    assert "secret detail" not in r.text


def test_oversized_body_rejected(client):
    r = client.post(
        "/api/v1/health",
        content=b"x" * 70000,
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
