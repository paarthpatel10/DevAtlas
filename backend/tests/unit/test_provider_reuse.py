from fastapi.testclient import TestClient

import app.api.deps as deps
from app.config import Settings
from app.main import create_app


def test_health_reuses_cached_providers(monkeypatch):
    """Building providers per request would leak an HTTP client per call (Gemini)."""
    calls: list[int] = []
    real = deps.get_providers

    def counting(settings):
        calls.append(1)
        return real(settings)

    monkeypatch.setattr(deps, "get_providers", counting)
    client = TestClient(create_app(Settings(app_env="test", _env_file=None)))
    for _ in range(3):
        assert client.get("/api/v1/health").status_code == 200
    assert len(calls) == 1
