from pydantic import ValidationError

from mcp_server.config import MCPServerConfig, load_config
from mcp_server.models import BorisAskRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


SERVER_INSTRUCTIONS = (
    "BORIS Runtime exposes BOIS/SIMA/BORIS reasoning through one adapter tool. "
    "Use boris.ask for user questions that should be answered by the BORIS Runtime. "
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


def create_mcp_server(config: MCPServerConfig | None = None):
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
        from starlette.responses import JSONResponse
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    resolved_config = config or load_config()
    mcp = FastMCP(
        "boris-runtime",
        instructions=SERVER_INSTRUCTIONS,
        host=resolved_config.host,
        port=resolved_config.port,
        streamable_http_path=resolved_config.path,
    )

    @mcp.tool(
        name="boris.ask",
        annotations=ToolAnnotations(**TOOL_ANNOTATIONS),
    )
    def tool_boris_ask(
        input: str,
        session_id: str | None = None,
        mode: str = "default",
        context: dict | None = None,
    ) -> dict:
        try:
            return boris_ask(input=input, session_id=session_id, mode=mode, context=context)
        except ValidationError as exc:
            return {
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
