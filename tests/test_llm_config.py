import os

import pytest

from llm import config
from llm.errors import LLMConfigurationError


ENV_NAMES = (
    "OPENAI_API_KEY",
    "BOIS_LLM",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
    "BORIS_SERVER_LLM_TIMEOUT_SECONDS",
    "BORIS_REVIEWER_LLM",
    "BORIS_REVIEWER_MODEL",
    "BORIS_RUNTIME_MODE",
)


def _clear_test_environment(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_default_env_files_load_local_secrets_over_tracked_settings(
    monkeypatch,
    tmp_path,
):
    _clear_test_environment(monkeypatch)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=\n"
        "BOIS_LLM=openai\n"
        "OPENAI_MODEL=gpt-5.6-terra\n"
        "OPENAI_REASONING_EFFORT=medium\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=local-secret\n",
        encoding="utf-8",
    )

    config.load_env_file()

    assert os.environ["OPENAI_API_KEY"] == "local-secret"
    assert os.environ["BOIS_LLM"] == "openai"
    assert os.environ["OPENAI_MODEL"] == "gpt-5.6-terra"
    assert os.environ["OPENAI_REASONING_EFFORT"] == "medium"


def test_process_environment_has_priority_over_both_env_files(
    monkeypatch,
    tmp_path,
):
    _clear_test_environment(monkeypatch)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "process-secret")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=local-secret\n",
        encoding="utf-8",
    )

    config.load_env_file()

    assert os.environ["OPENAI_API_KEY"] == "process-secret"


def test_explicit_env_path_loads_only_that_file(monkeypatch, tmp_path):
    _clear_test_environment(monkeypatch)
    explicit_path = tmp_path / "custom.env"
    explicit_path.write_text(
        "BOIS_LLM=mock\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.local").write_text(
        "OPENAI_API_KEY=must-not-load\n",
        encoding="utf-8",
    )

    config.load_env_file(explicit_path)

    assert os.environ["BOIS_LLM"] == "mock"
    assert "OPENAI_API_KEY" not in os.environ


def test_server_llm_timeout_has_bounded_positive_configuration(monkeypatch):
    monkeypatch.delenv("BORIS_SERVER_LLM_TIMEOUT_SECONDS", raising=False)
    assert config.server_llm_timeout_seconds() == 120.0

    monkeypatch.setenv("BORIS_SERVER_LLM_TIMEOUT_SECONDS", "45.5")
    assert config.server_llm_timeout_seconds() == 45.5

    monkeypatch.setenv("BORIS_SERVER_LLM_TIMEOUT_SECONDS", "0")
    with pytest.raises(
        LLMConfigurationError,
        match="must be a positive number",
    ):
        config.server_llm_timeout_seconds()


def test_reviewer_adapter_has_separate_configuration_and_timeout(
    monkeypatch,
):
    _clear_test_environment(monkeypatch)
    calls = []

    class FakeOpenAIAdapter:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(config, "OpenAIAdapter", FakeOpenAIAdapter)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BOIS_LLM", "mock")
    monkeypatch.setenv("BORIS_REVIEWER_LLM", "openai")
    monkeypatch.setenv("BORIS_REVIEWER_MODEL", "review-model")
    monkeypatch.setenv(
        "BORIS_SERVER_LLM_TIMEOUT_SECONDS",
        "75",
    )

    adapter = config.build_reviewer_llm_adapter()

    assert isinstance(adapter, FakeOpenAIAdapter)
    assert calls == [{
        "model": "review-model",
        "debug_prompt_enabled": False,
        "timeout": 75.0,
    }]
