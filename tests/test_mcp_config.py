import pytest

from mcp_server.config import load_config


def test_mcp_config_defaults(monkeypatch):
    for name in (
        "BORIS_RUNTIME_API_URL",
        "BORIS_MCP_TIMEOUT_SECONDS",
        "BORIS_MCP_TRANSPORT",
        "BORIS_MCP_HOST",
        "BORIS_MCP_PORT",
        "BORIS_MCP_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    config = load_config()

    assert config.runtime_api_url == "http://127.0.0.1:8000"
    assert config.timeout_seconds == 30.0
    assert config.transport == "stdio"
    assert config.host == "127.0.0.1"
    assert config.port == 9000
    assert config.path == "/mcp"


def test_mcp_config_env_overrides(monkeypatch):
    monkeypatch.setenv("BORIS_RUNTIME_API_URL", "http://runtime.local:8123")
    monkeypatch.setenv("BORIS_MCP_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("BORIS_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("BORIS_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("BORIS_MCP_PORT", "9100")
    monkeypatch.setenv("BORIS_MCP_PATH", "custom-mcp")

    config = load_config()

    assert config.runtime_api_url == "http://runtime.local:8123"
    assert config.timeout_seconds == 7.5
    assert config.transport == "streamable-http"
    assert config.host == "0.0.0.0"
    assert config.port == 9100
    assert config.path == "/custom-mcp"


def test_mcp_config_invalid_timeout_fails_clearly(monkeypatch):
    monkeypatch.setenv("BORIS_MCP_TIMEOUT_SECONDS", "slow")

    with pytest.raises(ValueError, match="Invalid BORIS_MCP_TIMEOUT_SECONDS: slow"):
        load_config()


def test_mcp_config_invalid_port_fails_clearly(monkeypatch):
    monkeypatch.setenv("BORIS_MCP_PORT", "nine-thousand")

    with pytest.raises(ValueError, match="Invalid BORIS_MCP_PORT: nine-thousand"):
        load_config()
