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
        "BORIS returned HOLD."
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


def test_developer_execute_moves_trace_to_component_only_metadata():
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
    assert text.startswith("BORIS returned HOLD.")
    assert "developer_trace" not in text
    assert "developer_trace" not in response["structuredContent"]
    assert response["_meta"]["developer_trace"] == packet[
        "developer_trace"
    ]
    assert response["_meta"]["developer_surface_version"] == "2.0"


def test_boris_execute_forwards_resume_to_runtime():
    client = FakeRuntimeClient(response=_execution_packet())
    resume = {
        "continuation_token": "v1.payload.signature",
        "operator_input": "Conditional analysis is allowed.",
    }

    run_boris_execute(
        session_id="test",
        resume=resume,
        client=client,
    )

    assert client.calls == [
        {
            "input": None,
            "session_id": "test",
            "context": {},
            "resume": resume,
        }
    ]


def test_non_operator_hold_is_presented_without_inventing_a_question():
    packet = _execution_packet()
    packet["hold"] = {
        "handoff_version": "boris-hold-handoff/1.2",
        "status": "resolution_not_operator_owned",
        "reason": "The remaining uncertainty is future-contingent.",
        "required_operator_input": None,
        "resolution_summary": {
            "FUTURE_CONTINGENT": [{
                "uncertainty_id": "future-event",
            }],
        },
        "resume_count": 0,
    }

    response = run_boris_execute(
        input="Evaluate a conditional route.",
        client=FakeRuntimeClient(response=packet),
    )
    text = response["content"][0]["text"]

    assert text.startswith(
        "BORIS returned HOLD without an operator-owned resolution target."
    )
    assert "Do not ask the operator" in text
    assert "resume.continuation_token" not in text
    assert response["structuredContent"] == packet


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
        "hold": {
            "handoff_version": "boris-hold-handoff/1.1",
            "status": "operator_input_required",
            "reason": "Material information remains unresolved.",
            "required_operator_input": {
                "question": "Provide the missing information.",
                "semantic_unknowns": [{
                    "unknown_id": "unknown-001",
                    "description": "Independent review is absent.",
                    "target_path": None,
                    "resolution_kind": "operator_statement",
                    "expected_type": "text",
                    "norm_refs": [],
                    "question": "Resolve: Independent review is absent.",
                }],
                "predicate_inputs": [],
                "response_contract": {},
            },
            "continuation_token": "v1.payload.signature",
            "expires_at": "2026-07-25T12:00:00+00:00",
            "resume_count": 0,
        },
    }
