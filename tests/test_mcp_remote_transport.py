import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server.config import MCPServerConfig
from mcp_server.server import (
    DEVELOPER_SURFACE_MIME_TYPE,
    DEVELOPER_SURFACE_URI,
    TOOL_ANNOTATIONS,
    create_mcp_server,
    create_remote_app,
    main,
)


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
    execute_tool = next(item for item in tools if item.name == "boris.execute")

    assert server._mcp_server.name == "BORIS"
    assert server._mcp_server.instructions.startswith("BORIS exposes one public tool")
    assert len(server._mcp_server.instructions) <= 512
    assert tool_names == {"boris.execute"}
    assert "boris.frame" not in tool_names
    assert "boris.ask" not in tool_names
    assert "boris.validate" not in tool_names
    assert "ExecutionCandidate" in execute_tool.description
    assert "not independently reviewed" in execute_tool.description
    assert "mode" not in execute_tool.inputSchema["properties"]
    assert "operation" not in execute_tool.inputSchema["properties"]
    assert "work_order_id" in execute_tool.inputSchema["properties"]
    assert "semantic_result" in execute_tool.inputSchema["properties"]
    assert "resume" in execute_tool.inputSchema["properties"]
    assert execute_tool.annotations.readOnlyHint is True
    assert execute_tool.annotations.openWorldHint is False
    assert execute_tool.annotations.destructiveHint is False
    assert TOOL_ANNOTATIONS == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def test_developer_mode_links_one_ui_resource_to_execute_tool():
    server = create_mcp_server(
        MCPServerConfig(developer_surface=True)
    )

    tools = asyncio.run(server.list_tools())
    resources = asyncio.run(server.list_resources())
    contents = asyncio.run(
        server.read_resource(DEVELOPER_SURFACE_URI)
    )
    execute_tool = next(
        item for item in tools
        if item.name == "boris.execute"
    )

    assert execute_tool.meta["ui"]["resourceUri"] == (
        DEVELOPER_SURFACE_URI
    )
    assert execute_tool.meta["ui"]["visibility"] == [
        "model",
        "app",
    ]
    assert execute_tool.meta["openai/outputTemplate"] == (
        DEVELOPER_SURFACE_URI
    )
    assert len(resources) == 1
    assert str(resources[0].uri) == DEVELOPER_SURFACE_URI
    assert contents[0].mime_type == DEVELOPER_SURFACE_MIME_TYPE
    assert "BORIS Developer Surface" in contents[0].content
    assert "tools/call" in contents[0].content
    assert contents[0].meta["ui"]["csp"] == {
        "connectDomains": [],
        "resourceDomains": [],
    }


def test_production_mode_does_not_publish_developer_surface():
    server = create_mcp_server(
        MCPServerConfig(developer_surface=False)
    )

    tools = asyncio.run(server.list_tools())
    resources = asyncio.run(server.list_resources())

    assert tools[0].meta is None
    assert resources == []


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

                    execution_result = await session.call_tool(
                        "boris.execute",
                        {
                            "input": "Explain BOIS Runtime",
                            "session_id": "mcp-native-execution",
                        },
                    )
    assert tool_names == ["boris.execute"]
    assert execution_result.isError is False
    assert execution_result.structuredContent is not None
    assert execution_result.structuredContent["execution_version"] == (
        "boris-execution/1.0"
    )
    assert execution_result.structuredContent["status"] == "semantic_candidate"
    assert execution_result.structuredContent["gate"] == "HOLD"
    result_text = execution_result.content[0].text
    assert result_text.startswith("BORIS returned HOLD.")
    assert "Do not replace it with an independently generated answer" in result_text
    assert '"structuredContent"' not in result_text


@pytest.mark.asyncio
async def test_cached_legacy_execute_argument_is_forced_to_host_prepare(
    monkeypatch,
):
    import mcp_server.server as server_module

    monkeypatch.setattr(
        server_module,
        "RuntimeAPIClient",
        FakeRuntimeAPIClient,
    )
    app = create_remote_app(MCPServerConfig(path="/mcp"))
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:9000",
        ) as http_client:
            async with streamable_http_client(
                "http://127.0.0.1:9000/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "boris.execute",
                        {
                            "input": "Cached legacy invocation",
                            "operation": "execute",
                        },
                    )

    assert result.isError is False
    assert result.structuredContent["status"] == "semantic_candidate"


@pytest.mark.asyncio
async def test_streamable_http_hides_trace_from_model_and_sends_it_to_ui_meta(
    monkeypatch,
):
    import mcp_server.server as server_module

    monkeypatch.setattr(
        server_module,
        "RuntimeAPIClient",
        FakeDeveloperRuntimeAPIClient,
    )
    app = create_remote_app(MCPServerConfig(
        path="/mcp",
        developer_surface=True,
    ))
    transport = httpx.ASGITransport(app=app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:9000",
        ) as http_client:
            async with streamable_http_client(
                "http://127.0.0.1:9000/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "boris.execute",
                        {"input": "Explain BOIS Runtime"},
                    )

    assert "developer_trace" not in result.structuredContent
    assert "developer_trace" not in result.content[0].text
    assert result.meta["developer_trace"] == {
        "trace_version": "boris-execution-trace/1.0",
        "semantic_execution": {"constrained_gate": "HOLD"},
    }


class FakeRuntimeAPIClient:
    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(
        self,
        input,
        session_id=None,
        context=None,
        operation=None,
    ):
        assert operation == "prepare"
        packet = execution_packet()
        packet["session_id"] = session_id or packet["session_id"]
        return packet


class FakeDeveloperRuntimeAPIClient(FakeRuntimeAPIClient):
    def execute(
        self,
        input,
        session_id=None,
        context=None,
        operation=None,
    ):
        packet = super().execute(
            input,
            session_id,
            context,
            operation,
        )
        packet["developer_trace"] = {
            "trace_version": "boris-execution-trace/1.0",
            "semantic_execution": {"constrained_gate": "HOLD"},
        }
        return packet


def execution_packet():
    return {
        "execution_version": "boris-execution/1.0",
        "session_id": "mcp-native-execution",
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": "HOLD",
        "candidate_result": {"summary": "Candidate only."},
        "norm_results": [],
        "unknowns": ["Independent review is absent."],
        "uncertainties": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": [
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
        "hold": {
            "handoff_version": "boris-hold-handoff/1.4",
            "status": "operator_input_required",
            "resolution_owner": "OPERATOR",
            "reason": "Material information remains unresolved.",
            "hold_record": {
                "hold_id": "hold-1",
                "cycle_id": "cycle-1",
                "return_state": "C03",
                "return_gate": "C03",
                "hold_reason": "Material information remains unresolved.",
                "scope": ["C03"],
                "source_refs": [],
                "unknowns": ["Independent review is absent."],
                "evidence_refs": [],
                "open_debts": ["uncertainty:unknown-001"],
                "state_hash": "a" * 64,
            },
            "blocking_precondition": {
                "precondition_id": "hold-precondition-1",
                "condition": "RECOVERABLE_PRECONDITION_UNRESOLVED",
                "status": "UNRESOLVED",
                "owner": "OPERATOR",
                "description": "Material information remains unresolved.",
                "resolution_options": [
                    "PROVIDE_INFORMATION",
                    "ALLOW_CONDITIONAL_PROCEEDING",
                ],
            },
            "required_operator_input": {
                "question": "Provide the missing information.",
                "resolution_modes": [{
                    "mode": "PROVIDE_INFORMATION",
                    "available": True,
                    "effect": "Provide every signed target.",
                    "preserves_unknowns": False,
                }, {
                    "mode": "ALLOW_CONDITIONAL_PROCEEDING",
                    "available": True,
                    "effect": "Preserve unknowns and recalculate.",
                    "preserves_unknowns": True,
                }],
                "semantic_unknowns": [{
                    "unknown_id": "unknown-001",
                    "description": "Independent review is absent.",
                    "target_path": None,
                    "resolution_kind": "operator_statement",
                    "expected_type": "text",
                    "norm_refs": [],
                    "core_refs": [],
                    "source_resolution_class": "OPERATOR_INPUT",
                    "resolution_owner": "OPERATOR",
                    "question": "Resolve: Independent review is absent.",
                }],
                "predicate_inputs": [],
                "system_targets": [{
                    "target_id": "semantic_unknown:unknown-001",
                    "kind": "SEMANTIC_UNKNOWN",
                    "description": "Independent review is absent.",
                    "target_path": None,
                    "norm_refs": [],
                    "source_resolution_class": "OPERATOR_INPUT",
                    "resolution_owner": "OPERATOR",
                }],
                "response_contract": {},
            },
            "continuation_token": "v1.payload.signature",
            "expires_at": "2026-07-25T12:00:00+00:00",
            "resume_count": 0,
        },
    }
