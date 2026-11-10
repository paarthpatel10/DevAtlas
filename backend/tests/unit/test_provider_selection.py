import pytest

from app.ai.provider import get_providers
from app.config import Settings
from app.core.errors import AppError


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_auto_uses_gemini_when_key_present():
    p = get_providers(settings(gemini_api_key="k"))
    assert p.llm_available and p.llm.model_name == "gemini:gemini-3.5-flash-lite"
    assert p.embeddings.model_name == "mock-hashing-v1"


def test_auto_without_key_is_mock():
    p = get_providers(settings())
    assert not p.llm_available and p.llm.model_name == "mock"


def test_explicit_mock_ignores_key():
    assert not get_providers(settings(ai_provider="mock", gemini_api_key="k")).llm_available


def test_explicit_gemini_without_key_fails():
    with pytest.raises(AppError) as e:
        get_providers(settings(ai_provider="gemini"))
    assert e.value.code == "provider_not_available"


def test_gemini_key_accepted_under_repo_env_name(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("gemini = abc123\n", encoding="utf-8")
    assert Settings(_env_file=env).gemini_api_key.get_secret_value() == "abc123"
