from pydantic import ValidationError

from mcp_server.config import MCPServerConfig, load_config
from mcp_server.models import BorisAskRequest, BorisFrameRequest, BorisValidateRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


SERVER_INSTRUCTIONS = (
    "BORIS exposes one public tool: boris.frame. Use it to obtain a bounded "
    "BOIS/SIMA/BORIS context frame and the complete Runtime-generated prompt "
    "that ChatGPT must show to the user before generating its own answer. "
    "The MCP server is an adapter and does not store memory or call LLMs directly."
)

TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "openWorldHint": False,
    "destructiveHint": False,
}


def boris_ask(input: str, session_id: str | None = None, mode: str = "default", context: dict | None = None):
    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as client:
        return run_boris_ask(
            input=input,
            session_id=session_id,
            mode=mode,
            context=context,
            client=client,
        )


def boris_frame(input: str, session_id: str | None = None, mode: str = "default", context: dict | None = None):
    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as client:
        return run_boris_frame(
            input=input,
            session_id=session_id,
            mode=mode,
            context=context,
            client=client,
        )


def boris_validate(answer: str, context_packet: dict, validation_mode: str = "deterministic"):
    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as client:
        return run_boris_validate(
            answer=answer,
            context_packet=context_packet,
            validation_mode=validation_mode,
            client=client,
        )


def run_boris_ask(
    input: str,
    session_id: str | None = None,
    mode: str = "default",
    context: dict | None = None,
    client=None,
):
    request = BorisAskRequest(
        input=input,
        session_id=session_id,
        mode=mode,
        context=context or {},
    )
    if client is not None:
        return _ask_runtime(request, client)

    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as runtime_client:
        return _ask_runtime(request, runtime_client)


def run_boris_frame(
    input: str,
    session_id: str | None = None,
    mode: str = "default",
    context: dict | None = None,
    client=None,
):
    request = BorisFrameRequest(
        input=input,
        session_id=session_id,
        mode=mode,
        context=context or {},
    )
    if client is not None:
        return _frame_runtime(request, client)

    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as runtime_client:
        return _frame_runtime(request, runtime_client)


def run_boris_validate(
    answer: str,
    context_packet: dict,
    validation_mode: str = "deterministic",
    client=None,
):
    request = BorisValidateRequest(
        answer=answer,
        context_packet=context_packet,
        validation_mode=validation_mode,
    )
    if client is not None:
        return _validate_runtime(request, client)

    config = load_config()
    with RuntimeAPIClient(config.runtime_api_url, timeout=config.timeout_seconds) as runtime_client:
        return _validate_runtime(request, runtime_client)


def _ask_runtime(request, runtime_client):
    try:
        runtime_payload = runtime_client.ask(
            input=request.input,
            session_id=request.session_id,
            mode=request.mode,
            context=request.context,
        )
        return normalize_tool_result(runtime_payload)
    except RuntimeAPIError as exc:
        if exc.payload:
            return normalize_tool_result(exc.payload)
        return normalize_tool_result({
            "error": "runtime_api_error",
            "detail": str(exc),
            "session_id": request.session_id,
        })


def _frame_runtime(request, runtime_client):
    try:
        runtime_payload = runtime_client.frame(
            input=request.input,
            session_id=request.session_id,
            mode=request.mode,
            context=request.context,
        )
        return normalize_frame_tool_result(runtime_payload)
    except RuntimeAPIError as exc:
        if exc.payload:
            return normalize_tool_result(exc.payload)
        return normalize_tool_result({
            "error": "runtime_api_error",
            "detail": str(exc),
            "session_id": request.session_id,
        })


def _validate_runtime(request, runtime_client):
    try:
        runtime_payload = runtime_client.validate(
            answer=request.answer,
            context_packet=request.context_packet,
            validation_mode=request.validation_mode,
        )
        return normalize_validation_tool_result(runtime_payload)
    except RuntimeAPIError as exc:
        if exc.payload:
            return normalize_tool_result(exc.payload)
        return normalize_tool_result({
            "error": "runtime_api_error",
            "detail": str(exc),
            "session_id": request.context_packet.get("session_id"),
        })


def normalize_tool_result(payload):
    if "error" in payload:
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

    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": str(payload.get("content", "")),
            }
        ],
    }


def normalize_frame_tool_result(payload):
    if "error" in payload:
        return normalize_tool_result(payload)

    runtime_prompt = str(payload.get("runtime_generated_prompt", ""))
    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": (
                    "Show the user the complete runtime_generated_prompt below, then "
                    "generate your own answer from it. Do not hide, shorten, or omit "
                    "the Runtime-generated prompt.\n\n"
                    f"{runtime_prompt}"
                ),
            }
        ],
    }


def normalize_validation_tool_result(payload):
    if "error" in payload:
        return normalize_tool_result(payload)

    verdict = str(payload.get("verdict", "INDETERMINATE"))
    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": (
                    f"BORIS validation verdict: {verdict}. "
                    "Review structuredContent for issues and recommendations."
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
        from mcp.server.fastmcp import FastMCP
        from mcp.types import CallToolResult, TextContent, ToolAnnotations
        from starlette.responses import JSONResponse
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    resolved_config = config or load_config()
    mcp = FastMCP(
        "BORIS",
        instructions=SERVER_INSTRUCTIONS,
        host=resolved_config.host,
        port=resolved_config.port,
        streamable_http_path=resolved_config.path,
    )

    @mcp.tool(
        name="boris.frame",
        annotations=ToolAnnotations(**TOOL_ANNOTATIONS),
    )
    def tool_boris_frame(
        input: str,
        session_id: str | None = None,
        mode: str = "default",
        context: dict | None = None,
    ) -> CallToolResult:
        """Context-only BOIS/SIMA/BORIS frame. BORIS does not generate a final answer or call an external LLM; ChatGPT must show runtime_generated_prompt and then answer itself."""
        try:
            envelope = boris_frame(input=input, session_id=session_id, mode=mode, context=context)
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


def create_remote_app(config: MCPServerConfig | None = None):
    return create_mcp_server(config).streamable_http_app()


def main():
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
