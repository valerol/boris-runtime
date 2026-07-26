import os

from llm import config


ENV_NAMES = (
    "OPENAI_API_KEY",
    "BOIS_LLM",
    "OPENAI_MODEL",
    "OPENAI_REASONING_EFFORT",
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
