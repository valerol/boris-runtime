import json
from typing import Literal

from pydantic import ValidationError

from llm.config import PROJECT_ROOT, load_env_file
from mcp_server.config import MCPServerConfig, load_config
from mcp_server.models import BorisExecuteRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


SERVER_INSTRUCTIONS = (
    "BORIS exposes one public tool: boris.execute. Use it for the Runtime's "
    "semantic evaluation route. Present its ExecutionCandidate without replacing "
    "it with an independent answer or weakening HOLD, STOP, or REPAIR. "
    "mode=developer adds the safe projection and semantic trace. The result is "
    "not independently reviewed, policy-admitted, state-mutating, or executed."
)

TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "openWorldHint": False,
    "destructiveHint": False,
}


def boris_execute(
    input: str,
    session_id: str | None = None,
    mode: str = "default",
    context: dict | None = None,
):
    config = load_config()
    with RuntimeAPIClient(
        config.runtime_api_url,
        timeout=config.timeout_seconds,
    ) as client:
        return run_boris_execute(
            input=input,
            session_id=session_id,
            mode=mode,
            context=context,
            client=client,
        )


def run_boris_execute(
    input: str,
    session_id: str | None = None,
    mode: str = "default",
    context: dict | None = None,
    client=None,
):
    request = BorisExecuteRequest(
        input=input,
        session_id=session_id,
        mode=mode,
        context=context or {},
    )
    if client is not None:
        return _execute_runtime(request, client)

    config = load_config()
    with RuntimeAPIClient(
        config.runtime_api_url,
        timeout=config.timeout_seconds,
    ) as runtime_client:
        return _execute_runtime(request, runtime_client)


def _execute_runtime(request, runtime_client):
    try:
        runtime_payload = runtime_client.execute(
            input=request.input,
            session_id=request.session_id,
            mode=request.mode,
            context=request.context,
        )
        return normalize_execution_tool_result(runtime_payload)
    except RuntimeAPIError as exc:
        if exc.payload:
            return normalize_error_result(exc.payload)
        return normalize_error_result({
            "error": "runtime_api_error",
            "detail": str(exc),
            "session_id": request.session_id,
        })


def normalize_error_result(payload):
    detail = str(payload.get("detail", "Runtime API error"))
    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": f"Runtime error: {detail}",
            }
        ],
        "isError": True,
    }


def normalize_execution_tool_result(payload):
    if "error" in payload:
        return normalize_error_result(payload)

    developer_trace = payload.get("developer_trace")
    candidate_payload = {
        key: value
        for key, value in payload.items()
        if key != "developer_trace"
    }
    candidate_json = json.dumps(
        candidate_payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
    developer_instruction = ""
    if developer_trace is not None:
        developer_json = json.dumps(
            developer_trace,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        developer_instruction = (
            "Developer mode is active. Present the complete safe developer_trace "
            "as formatted JSON before the Runtime candidate; do not hide, shorten, "
            "or omit its projection or semantic diagnostics.\n\n"
            "developer_trace:\n"
            f"{developer_json}"
            "\n\n"
        )
    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": (
                    developer_instruction
                    + "Present the Runtime ExecutionCandidate below as the result. "
                    "Do not replace it with an independently generated answer, do "
                    "not weaken its gate, and do not claim review, policy admission, "
                    "state mutation, tool use, or external action.\n\n"
                    "ExecutionCandidate:\n"
                    f"{candidate_json}"
                ),
            }
        ],
    }


def to_call_tool_result(envelope, call_tool_result_cls, text_content_cls):
    return call_tool_result_cls(
        content=[
            text_content_cls(
                type=item.get("type", "text"),
                text=str(item.get("text", "")),
            )
            for item in envelope.get("content", [])
        ],
        structuredContent=envelope.get("structuredContent"),
        isError=bool(envelope.get("isError", False)),
    )


def create_mcp_server(config: MCPServerConfig | None = None):
    try:
        from fastapi.responses import JSONResponse
        from mcp.server.fastmcp import FastMCP
        from mcp.server.transport_security import TransportSecuritySettings
        from mcp.types import CallToolResult, TextContent, ToolAnnotations
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    resolved_config = config or load_config()
    transport_security = _transport_security_settings(resolved_config, TransportSecuritySettings)
    mcp = FastMCP(
        "BORIS",
        instructions=SERVER_INSTRUCTIONS,
        host=resolved_config.host,
        port=resolved_config.port,
        streamable_http_path=resolved_config.path,
        transport_security=transport_security,
    )

    @mcp.tool(
        name="boris.execute",
        annotations=ToolAnnotations(**TOOL_ANNOTATIONS),
    )
    def tool_boris_execute(
        input: str,
        session_id: str | None = None,
        mode: Literal["default", "production", "developer"] = "default",
        context: dict | None = None,
    ) -> CallToolResult:
        """Run the read-only BORIS semantic route.

        Returns an ExecutionCandidate. Developer mode adds the safe projection
        and semantic trace. The candidate is not independently reviewed,
        policy-admitted, state-mutating, or executed.
        """
        try:
            envelope = boris_execute(
                input=input,
                session_id=session_id,
                mode=mode,
                context=context,
            )
        except ValidationError as exc:
            envelope = {
                "structuredContent": {
                    "error": "invalid_request",
                    "detail": str(exc),
                    "session_id": session_id,
                },
                "content": [
                    {
                        "type": "text",
                        "text": f"Runtime error: {exc}",
                    }
                ],
                "isError": True,
            }
        return to_call_tool_result(envelope, CallToolResult, TextContent)

    @mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request):
        return JSONResponse(
            {
                "status": "ok",
                "service": "boris-mcp-server",
                "transport": resolved_config.transport,
                "runtime_api_url": resolved_config.runtime_api_url,
            }
        )

    return mcp


def _transport_security_settings(config, settings_cls):
    if not config.allowed_hosts and not config.allowed_origins:
        return None

    allowed_hosts = list(config.allowed_hosts)
    for host in ("127.0.0.1:*", "localhost:*", "[::1]:*"):
        if host not in allowed_hosts:
            allowed_hosts.append(host)

    return settings_cls(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=list(config.allowed_origins),
    )


def create_remote_app(config: MCPServerConfig | None = None):
    return create_mcp_server(config).streamable_http_app()


def main():
    load_env_file(PROJECT_ROOT / ".env")
    config = load_config()
    if config.transport not in {"stdio", "streamable-http"}:
        raise RuntimeError(
            "Unsupported BORIS_MCP_TRANSPORT. Use 'stdio' or 'streamable-http'."
        )

    try:
        create_mcp_server(config).run(transport=config.transport)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
