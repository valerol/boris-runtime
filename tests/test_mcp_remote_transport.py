import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server.config import MCPServerConfig
from mcp_server.runtime_client import RuntimeAPIError
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
    tool_names = {item.name for item in tools}
    frame_tool = next(item for item in tools if item.name == "boris.frame")

    assert server._mcp_server.name == "BORIS"
    assert server._mcp_server.instructions.startswith("BORIS exposes one public tool")
    assert len(server._mcp_server.instructions) <= 512
    assert tool_names == {"boris.frame"}
    assert "boris.ask" not in tool_names
    assert "boris.validate" not in tool_names
    assert "Context-only" in frame_tool.description
    assert "does not generate a final answer or call an external LLM" in frame_tool.description
    assert frame_tool.annotations.readOnlyHint is True
    assert frame_tool.annotations.openWorldHint is False
    assert frame_tool.annotations.destructiveHint is False
    assert TOOL_ANNOTATIONS == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def test_unsupported_transport_fails_clearly(monkeypatch):
    monkeypatch.setenv("BORIS_MCP_TRANSPORT", "websocket")

    with pytest.raises(RuntimeError, match="Unsupported BORIS_MCP_TRANSPORT"):
        main()


@pytest.mark.asyncio
async def test_streamable_http_client_receives_native_structured_content(monkeypatch):
    import mcp_server.server as server_module

    monkeypatch.setattr(server_module, "RuntimeAPIClient", FakeRuntimeAPIClient)
    app = create_remote_app(MCPServerConfig(path="/mcp"))
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:9000") as http_client:
            async with streamable_http_client(
                "http://127.0.0.1:9000/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    tool_names = [tool.name for tool in tools.tools]

                    frame_result = await session.call_tool(
                        "boris.frame",
                        {
                            "input": "Explain BOIS Runtime",
                            "session_id": "mcp-native-frame",
                        },
                    )
    assert tool_names == ["boris.frame"]
    assert frame_result.isError is False
    assert frame_result.structuredContent is not None
    assert frame_result.structuredContent["packet_version"] == "boris-context/1.0"
    assert frame_result.structuredContent["runtime_mode"] == "context_provider"
    assert frame_result.structuredContent["llm_called"] is False
    assert frame_result.structuredContent["runtime_generated_prompt"]
    frame_text = frame_result.content[0].text
    assert frame_text.startswith("Show the user the complete runtime_generated_prompt")
    assert "Do not hide, shorten, or omit the Runtime-generated prompt." in frame_text
    assert frame_result.structuredContent["runtime_generated_prompt"] in frame_text
    assert '"structuredContent"' not in frame_text


class FakeRuntimeAPIClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def ask(self, input, session_id=None, mode="default", context=None):
        if input == "trigger error":
            raise RuntimeAPIError(
                "HTTP 500",
                status_code=500,
                payload={
                    "error": "runtime_error",
                    "detail": "failed",
                    "session_id": session_id,
                },
            )
        return {
            "session_id": session_id or "generated",
            "type": "ANSWER",
            "content": "ok",
            "metadata": {},
        }

    def frame(self, input, session_id=None, mode="default", context=None):
        packet = frame_packet()
        packet["session_id"] = session_id or packet["session_id"]
        packet["input"] = input
        return packet

    def validate(self, answer, context_packet, validation_mode="deterministic"):
        return validation_report(context_packet.get("frame_id"))


def frame_packet():
    return {
        "packet_version": "boris-context/1.0",
        "frame_id": "00000000-0000-4000-8000-000000000000",
        "session_id": "mcp-native-frame",
        "input": "Explain BOIS Runtime",
        "runtime_mode": "context_provider",
        "llm_called": False,
        "bois_frame": {},
        "sima": {
            "risk": 0.2,
            "uncertainty": 0.2,
            "missing_fields": [],
            "ambiguity_score": 0.1,
        },
        "boris_context": {},
        "retrieved_core": [],
        "retrieval_metadata": {
            "returned_chunks": 0,
            "total_characters": 0,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": [],
        "runtime_generated_prompt": "## User input\nExplain BOIS Runtime",
    }


def validation_report(frame_id):
    return {
        "validation_version": "boris-validation/1.0",
        "frame_id": frame_id,
        "validation_mode": "deterministic",
        "verdict": "PASS",
        "llm_called": False,
        "preflight": {"status": "completed", "issues": []},
        "deterministic": {
            "status": "completed",
            "verdict": "PASS",
            "checks": [],
            "issues": [],
            "recommendations": [],
        },
        "semantic": {
            "status": "not_run",
            "verdict": "INDETERMINATE",
            "issues": [],
            "recommendations": [],
        },
        "issues": [],
        "recommendations": [],
    }
