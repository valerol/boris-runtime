import os
from dataclasses import dataclass


DEFAULT_RUNTIME_API_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_TRANSPORT = "stdio"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
DEFAULT_PATH = "/mcp"


@dataclass(frozen=True)
class MCPServerConfig:
    runtime_api_url: str = DEFAULT_RUNTIME_API_URL
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    transport: str = DEFAULT_TRANSPORT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    path: str = DEFAULT_PATH


def load_config():
    return MCPServerConfig(
        runtime_api_url=os.getenv("BORIS_RUNTIME_API_URL", DEFAULT_RUNTIME_API_URL),
        timeout_seconds=_float_env("BORIS_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        transport=os.getenv("BORIS_MCP_TRANSPORT", DEFAULT_TRANSPORT).strip().lower(),
        host=os.getenv("BORIS_MCP_HOST", DEFAULT_HOST),
        port=_int_env("BORIS_MCP_PORT", DEFAULT_PORT),
        path=_path_env("BORIS_MCP_PATH", DEFAULT_PATH),
    )


def _float_env(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {name}: {raw}") from exc


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid {name}: {raw}") from exc


def _path_env(name, default):
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    path = raw.strip()
    if not path.startswith("/"):
        path = f"/{path}"
    return path
