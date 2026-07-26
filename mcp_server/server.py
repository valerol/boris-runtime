import json
from pathlib import Path

from pydantic import ValidationError

from llm.config import PROJECT_ROOT, load_env_file
from mcp_server.config import MCPServerConfig, load_config
from mcp_server.models import BorisExecuteRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


SERVER_INSTRUCTIONS = (
    "BORIS exposes one public tool: boris.execute. Use it for the Runtime's "
    "semantic evaluation route. Present its ExecutionCandidate without replacing "
    "it with an independent answer or weakening HOLD, STOP, or REPAIR. "
    "For HOLD, ask for required_operator_input and resume only through the signed "
    "continuation. Developer trace is component-only. The result is not independently "
    "reviewed, policy-admitted, state-mutating, or executed."
)

TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "openWorldHint": False,
    "destructiveHint": False,
}
DEVELOPER_SURFACE_URI = "ui://boris/developer-surface-v1.html"
DEVELOPER_SURFACE_MIME_TYPE = "text/html;profile=mcp-app"
DEVELOPER_SURFACE_PATH = (
    Path(__file__).resolve().parent
    / "ui"
    / "developer_surface_v1.html"
)
DEVELOPER_TOOL_META = {
    "ui": {
        "resourceUri": DEVELOPER_SURFACE_URI,
        "visibility": ["model", "app"],
    },
    "openai/outputTemplate": DEVELOPER_SURFACE_URI,
    "openai/widgetAccessible": True,
    "openai/toolInvocation/invoking": "Calculating BORIS route…",
    "openai/toolInvocation/invoked": "BORIS route ready",
}
DEVELOPER_RESOURCE_META = {
    "ui": {
        "prefersBorder": True,
        "csp": {
            "connectDomains": [],
            "resourceDomains": [],
        },
    },
    "openai/widgetDescription": (
        "BORIS Developer Surface showing the constrained gate, HOLD handoff, "
        "candidate, and complete safe developer trace."
    ),
    "openai/widgetPrefersBorder": True,
    "openai/widgetCSP": {
        "connect_domains": [],
        "resource_domains": [],
    },
}


def boris_execute(
    input: str | None = None,
    session_id: str | None = None,
    context: dict | None = None,
    resume: dict | None = None,
):
    config = load_config()
    with RuntimeAPIClient(
        config.runtime_api_url,
        timeout=config.timeout_seconds,
    ) as client:
        return run_boris_execute(
            input=input,
            session_id=session_id,
            context=context,
            resume=resume,
            client=client,
        )


def run_boris_execute(
    input: str | None = None,
    session_id: str | None = None,
    context: dict | None = None,
    resume: dict | None = None,
    client=None,
):
    request = BorisExecuteRequest(
        input=input,
        session_id=session_id,
        context=context or {},
        resume=resume,
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
        execution_arguments = {
            "input": request.input,
            "session_id": request.session_id,
            "context": request.context,
        }
        if request.resume is not None:
            execution_arguments["resume"] = (
                request.resume.model_dump()
            )
        runtime_payload = runtime_client.execute(
            **execution_arguments,
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
    result = {
        "structuredContent": candidate_payload,
        "content": [
            {
                "type": "text",
                "text": _candidate_instruction(
                    candidate_payload,
                    candidate_json,
                ),
            }
        ],
    }
    if developer_trace is not None:
        result["_meta"] = {
            "developer_surface_version": "1.0",
            "developer_trace": developer_trace,
        }
    return result


def _candidate_instruction(payload, candidate_json):
    if payload.get("gate") == "HOLD":
        hold = payload.get("hold")
        required = (
            hold.get("required_operator_input", {})
            if isinstance(hold, dict)
            else {}
        )
        question = required.get(
            "question",
            "Operator input is required before this route can continue.",
        )
        return (
            "BORIS returned HOLD. Do not replace it with an independently "
            "generated answer and do not weaken the gate. Present the operator "
            f"question exactly: {question} Continue only by calling the same "
            "boris.execute tool with resume.continuation_token and "
            "resume.operator_input from the operator.\n\n"
            "ExecutionCandidate:\n"
            f"{candidate_json}"
        )
    return (
        "Present the Runtime ExecutionCandidate below as the result. "
        "Do not replace it with an independently generated answer, do "
        "not weaken its gate, and do not claim review, policy admission, "
        "state mutation, tool use, or external action.\n\n"
        "ExecutionCandidate:\n"
        f"{candidate_json}"
    )


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
        _meta=envelope.get("_meta"),
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

    if resolved_config.developer_surface:
        @mcp.resource(
            DEVELOPER_SURFACE_URI,
            name="BORIS Developer Surface",
            title="BORIS Developer Surface",
            description=(
                "Interactive developer-only projection for boris.execute."
            ),
            mime_type=DEVELOPER_SURFACE_MIME_TYPE,
            meta=DEVELOPER_RESOURCE_META,
        )
        def developer_surface() -> str:
            return DEVELOPER_SURFACE_PATH.read_text(encoding="utf-8")

    @mcp.tool(
        name="boris.execute",
        title="Execute BORIS semantic route",
        annotations=ToolAnnotations(**TOOL_ANNOTATIONS),
        meta=(
            DEVELOPER_TOOL_META
            if resolved_config.developer_surface
            else None
        ),
    )
    def tool_boris_execute(
        input: str | None = None,
        session_id: str | None = None,
        context: dict | None = None,
        resume: dict | None = None,
    ) -> CallToolResult:
        """Run the read-only BORIS semantic route.

        Provide input for an initial calculation or resume for a signed HOLD
        continuation. Returns an ExecutionCandidate. Server developer mode adds
        a visual safe projection and semantic trace. It is not independently reviewed.
        The candidate is not policy-admitted, state-mutating, or executed.
        """
        try:
            envelope = boris_execute(
                input=input,
                session_id=session_id,
                context=context,
                resume=resume,
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
