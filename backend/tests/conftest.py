import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(app_env="test", database_url=None, _env_file=None)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture
def client_with_boom_route(settings: Settings) -> TestClient:
    app: FastAPI = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    return TestClient(app, raise_server_exceptions=False)
