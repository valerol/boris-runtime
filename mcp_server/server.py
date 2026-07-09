from pydantic import ValidationError

from mcp_server.config import load_config
from mcp_server.models import BorisAskRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


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
        return runtime_client.ask(
            input=request.input,
            session_id=request.session_id,
            mode=request.mode,
            context=request.context,
        )
    except RuntimeAPIError as exc:
        if exc.payload:
            return exc.payload
        return {
            "error": "runtime_api_error",
            "detail": str(exc),
            "session_id": request.session_id,
        }


def create_mcp_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The MCP server requires the 'mcp' package. "
            "Install dependencies with: python -m pip install -r requirements.txt"
        ) from exc

    mcp = FastMCP("boris-runtime")

    @mcp.tool(name="boris.ask")
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
                "error": "invalid_request",
                "detail": str(exc),
                "session_id": session_id,
            }

    return mcp


def main():
    config = load_config()
    if config.transport != "stdio":
        raise RuntimeError(
            "Only stdio MCP transport is enabled in Phase 4B. "
            "Set BORIS_MCP_TRANSPORT=stdio."
        )

    create_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
