def test_health_reports_demo_mode_without_database(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "app_env": "test",
        "ai_provider": "mock",
        "llm_model": None,
        "demo_mode": True,
        "database": "not_configured",
    }
    assert "x-request-id" in r.headers
