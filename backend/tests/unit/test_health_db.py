from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

UNREACHABLE_DB = "postgresql+psycopg://u:p@127.0.0.1:1/nope"


def bad_db_settings() -> Settings:
    return Settings(app_env="test", _env_file=None, database_url=UNREACHABLE_DB)


def test_data_endpoint_503_when_db_down():
    r = TestClient(create_app(bad_db_settings())).get("/api/v1/repositories")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"


def test_data_endpoint_503_when_db_not_configured():
    settings = Settings(app_env="test", _env_file=None, database_url=None)
    r = TestClient(create_app(settings)).get("/api/v1/repositories")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "database_unavailable"


def test_health_degraded_when_database_unreachable():
    r = TestClient(create_app(bad_db_settings())).get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "unavailable"
    assert body["status"] == "degraded"
