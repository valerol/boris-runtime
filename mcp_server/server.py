import json
from pathlib import Path

from pydantic import ValidationError

from llm.config import PROJECT_ROOT, load_env_file
from mcp_server.config import MCPServerConfig, load_config
from mcp_server.models import BorisExecuteRequest
from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


SERVER_INSTRUCTIONS = (
    "BORIS exposes one public tool: boris.execute. One call performs the canonical "
    "server-side semantic route and an IND2 IndependentReview, or a fail-closed "
    "Runtime error. Never choose an operator HOLD mode or alter Core, phase, scope, "
    "formal results, gate, or review decision. Results remain candidates: they are "
    "not Policy Kernel-admitted, state-mutating, or executed."
)

TOOL_ANNOTATIONS = {
    "readOnlyHint": True,
    "openWorldHint": False,
    "destructiveHint": False,
}
DEVELOPER_SURFACE_URI = "ui://boris/developer-surface-v2-5.html"
DEVELOPER_SURFACE_MIME_TYPE = "text/html;profile=mcp-app"
DEVELOPER_SURFACE_PATH = (
    Path(__file__).resolve().parent
    / "ui"
    / "developer_surface_v2.html"
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
        "BORIS Developer Surface showing the constrained gate, IND2 review, "
        "HOLD handoff, candidate, and complete safe developer trace."
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
            "operation": "execute",
        }
        if request.resume is not None:
            execution_arguments["resume"] = (
                request.resume.model_dump(exclude_none=True)
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
    error = str(payload.get("error", "runtime_error"))
    detail = str(payload.get("detail", "Runtime API error"))
    return {
        "structuredContent": dict(payload),
        "content": [
            {
                "type": "text",
                "text": (
                    "BORIS Runtime failed closed. Do not answer the user's "
                    "underlying request, reuse or summarize any earlier "
                    "candidate/HOLD, or start a new COMPILATION route. Report "
                    "only this technical Runtime failure and await explicit "
                    f"operator action. Runtime error {error}: {detail}"
                ),
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
    if candidate_payload.get("status") == "semantic_work_order":
        return normalize_error_result({
            "error": "unexpected_semantic_work_order",
            "detail": (
                "The public boris.execute route requires the canonical "
                "SERVER_LLM provider and cannot delegate semantic work to the "
                "ChatGPT host."
            ),
            "session_id": candidate_payload.get("session_id"),
        })
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
            "developer_surface_version": "2.5",
            "developer_trace": developer_trace,
        }
    return result


def _candidate_instruction(payload, candidate_json):
    review = payload.get("independent_review")
    review_decision = (
        review.get("decision")
        if isinstance(review, dict)
        else None
    )
    review_instruction = (
        " Preserve and present the IndependentReview decision "
        f"{review_decision}; it does not alter the semantic gate."
        if review_decision
        else ""
    )
    if payload.get("gate") == "HOLD":
        hold = payload.get("hold")
        if (
            isinstance(hold, dict)
            and hold.get("status") == "operator_terminated"
        ):
            return (
                "BORIS confirms that the operator terminated this cycle. Do "
                "not call boris.execute again, do not generate a replacement "
                "answer, and do not describe the result as PASS or STOP."
                f"{review_instruction}\n\n"
                "Terminal operator decision:\n"
                f"{candidate_json}"
            )
        required = (
            hold.get("required_operator_input")
            if isinstance(hold, dict)
            else None
        )
        if not isinstance(required, dict):
            if payload.get("candidate_result") is None:
                return (
                    "BORIS preserved HOLD and did not accept a semantic "
                    "candidate. Do not generate a replacement answer and do "
                    "not call boris.execute again automatically. Present the "
                    "HOLD reason and await an explicit operator decision."
                    f"{review_instruction}\n\n"
                    "Runtime HOLD:\n"
                    f"{candidate_json}"
                )
            return (
                "BORIS returned a terminal HOLD without continuation. Present "
                "the preserved result and do not call boris.execute again."
                f"{review_instruction}\n\n"
                "ExecutionCandidate:\n"
                f"{candidate_json}"
            )
        question = required.get(
            "question",
            "Operator input is required before this route can continue.",
        )
        modes = [
            item.get("mode")
            for item in required.get("resolution_modes", [])
            if isinstance(item, dict) and item.get("available")
        ]
        return (
            "BORIS returned HOLD. Do not replace it with an independently "
            "generated answer and do not weaken the gate. Present the operator "
            f"question exactly: {question} Available signed resolution modes: "
            f"{modes}. Continue only by calling the same "
            "boris.execute tool with resume.continuation_token and "
            "resume.operator_input from the operator, including one exact "
            "resolution_mode. Never choose a mode on the operator's behalf. "
            "PROVIDE_INFORMATION and CONFIRM_ASSUMPTION require all signed "
            "formal values; ALLOW_CONDITIONAL_PROCEEDING preserves unknowns; "
            "CHANGE_SCOPE requires scope; TERMINATE_CYCLE ends the cycle.\n\n"
            f"{review_instruction}\n\n"
            "ExecutionCandidate:\n"
            f"{candidate_json}"
        )
    return (
        "Present the Runtime ExecutionCandidate and IndependentReview below. "
        "Do not replace it with an independently generated answer, do "
        "not weaken its gate or review decision, and do not claim policy admission, "
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

        Initial input and signed HOLD resume use the canonical SERVER_LLM
        SemanticProvider inside Runtime, form one ExecutionCandidate, then run
        one IND2 IndependentReview bound to that exact candidate. Server developer
        mode adds a safe visual projection and semantic trace. The result is not
        Policy Kernel-admitted, state-mutating, or executed.
        """
        try:
            envelope = boris_execute(
                input=input,
                session_id=session_id,
                context=context,
                resume=resume,
            )
        except ValidationError as exc:
            envelope = normalize_error_result({
                "error": "invalid_request",
                "detail": str(exc),
                "session_id": session_id,
            })
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
