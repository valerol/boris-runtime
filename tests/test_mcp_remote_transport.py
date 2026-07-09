import asyncio

import pytest
from fastapi.testclient import TestClient

from mcp_server.config import MCPServerConfig
from mcp_server.server import TOOL_ANNOTATIONS, create_mcp_server, create_remote_app, main


def test_remote_transport_builds_app_with_configured_path_and_health():
    config = MCPServerConfig(
        runtime_api_url="http://127.0.0.1:8000",
        transport="streamable-http",
        host="127.0.0.1",
        port=9000,
        path="/mcp",
    )

    app = create_remote_app(config)
    paths = {getattr(route, "path", "") for route in app.routes}
    client = TestClient(app)

    assert "/mcp" in paths
    assert "/health" in paths
    assert client.get("/health").json() == {
        "status": "ok",
        "service": "boris-mcp-server",
        "transport": "streamable-http",
        "runtime_api_url": "http://127.0.0.1:8000",
    }


def test_mcp_tool_metadata_includes_annotations_and_instructions():
    server = create_mcp_server(MCPServerConfig())

    tools = asyncio.run(server.list_tools())
    tool = next(item for item in tools if item.name == "boris.ask")

    assert server._mcp_server.instructions.startswith("BORIS Runtime exposes BOIS/SIMA/BORIS reasoning")
    assert len(server._mcp_server.instructions) <= 512
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.openWorldHint is False
    assert tool.annotations.destructiveHint is False
    assert TOOL_ANNOTATIONS == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def test_unsupported_transport_fails_clearly(monkeypatch):
    monkeypatch.setenv("BORIS_MCP_TRANSPORT", "websocket")

    with pytest.raises(RuntimeError, match="Unsupported BORIS_MCP_TRANSPORT"):
        main()
