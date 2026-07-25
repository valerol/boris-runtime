from pathlib import Path

from mcp_server.server import run_boris_execute
from mcp_server.runtime_client import RuntimeAPIError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntimeClient:
    def __init__(self, response=None, error=None):
        self.response = response or _execution_packet()
        self.error = error
        self.calls = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_boris_execute_calls_runtime_api_client_and_returns_candidate():
    packet = _execution_packet()
    client = FakeRuntimeClient(response=packet)

    response = run_boris_execute(
        input="Explain BOIS Runtime",
        session_id="test",
        context={"source": "mcp-test"},
        client=client,
    )

    assert response["structuredContent"] == packet
    assert response["content"][0]["type"] == "text"
    assert response["content"][0]["text"].startswith(
        "Present the Runtime ExecutionCandidate"
    )
    assert "Do not replace it with an independently generated answer" in (
        response["content"][0]["text"]
    )
    assert '"status": "semantic_candidate"' in response["content"][0]["text"]
    assert "isError" not in response
    assert client.calls == [
        {
            "input": "Explain BOIS Runtime",
            "session_id": "test",
            "context": {"source": "mcp-test"},
        }
    ]


def test_boris_execute_surfaces_runtime_error_payload():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }
    client = FakeRuntimeClient(error=RuntimeAPIError(
        "HTTP 500",
        status_code=500,
        payload=error_payload,
    ))

    response = run_boris_execute(input="hello", session_id="test", client=client)

    assert response == {
        "structuredContent": error_payload,
        "content": [{"type": "text", "text": "Runtime error: failed"}],
        "isError": True,
    }


def test_developer_execute_instructs_chatgpt_to_show_trace_before_candidate():
    packet = _execution_packet()
    packet["developer_trace"] = {
        "trace_version": "boris-execution-trace/1.0",
        "semantic_execution": {"constrained_gate": "HOLD"},
    }
    client = FakeRuntimeClient(response=packet)

    response = run_boris_execute(
        input="Explain BOIS Runtime",
        client=client,
    )

    text = response["content"][0]["text"]
    assert text.startswith("Developer mode is active.")
    assert text.index("developer_trace:") < text.index("ExecutionCandidate:")
    assert '"trace_version": "boris-execution-trace/1.0"' in text
    assert response["structuredContent"]["developer_trace"] == packet["developer_trace"]


def test_mcp_adapter_does_not_import_runtime_internals():
    forbidden = (
        "application.context_provider",
        "core_surface",
        "llm.llm_adapter",
        "OpenAIAdapter",
    )

    for path in (PROJECT_ROOT / "mcp_server").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in source, f"{path} must not reference {item}"


def _execution_packet():
    return {
        "execution_version": "boris-execution/1.0",
        "session_id": "test",
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": "HOLD",
        "candidate_result": {"summary": "Candidate only."},
        "norm_results": [],
        "unknowns": ["Independent review is absent."],
        "conflicts": [],
        "alternatives": [],
        "limitations": [
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
    }
