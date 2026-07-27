from pathlib import Path

from mcp_server.models import BorisExecuteRequest
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
            "operation": "prepare",
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
    assert response["_meta"]["developer_surface_version"] == "2.2"


def test_boris_execute_forwards_resume_to_runtime():
    client = FakeRuntimeClient(response=_execution_packet())
    resume = {
        "continuation_token": "v1.payload.signature",
        "operator_input": {
            "resolution_mode": "ALLOW_CONDITIONAL_PROCEEDING",
            "statement": "Conditional analysis is allowed.",
            "values": {},
            "resolved_unknowns": [],
        },
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
            "operation": "prepare",
            "resume": resume,
        }
    ]


def test_boris_execute_returns_host_work_order_without_prompt_duplication():
    packet = _host_work_order_packet()
    client = FakeRuntimeClient(response=packet)

    response = run_boris_execute(
        input="Explain BOIS Runtime",
        session_id="host-mcp",
        client=client,
    )

    public_contract = response["structuredContent"][
        "submission_contract"
    ]
    assert "operation" not in public_contract
    assert "operation" not in public_contract["required_arguments"]
    assert packet["submission_contract"]["operation"] == "submit"
    text = response["content"][0]["text"]
    assert text.startswith(
        "BORIS returned a signed CHATGPT_HOST_ONLY COMPILATION "
        "SemanticWorkOrder."
    )
    assert "operation=submit" not in text
    assert "semantic_input" in text
    assert packet["semantic_prompt"] not in text
    assert client.calls == [{
        "input": "Explain BOIS Runtime",
        "session_id": "host-mcp",
        "context": {},
        "operation": "prepare",
    }]


def test_boris_execute_forwards_one_host_submission():
    client = FakeRuntimeClient(response=_execution_packet())
    semantic_result = {"candidate_result": {"summary": "Host result"}}

    run_boris_execute(
        session_id="host-mcp",
        work_order_id="work-order-1",
        work_order_token="hw1.payload.signature",
        semantic_input=semantic_result,
        client=client,
    )

    assert client.calls == [{
        "input": None,
        "session_id": "host-mcp",
        "context": {},
        "operation": "submit",
        "work_order_id": "work-order-1",
        "work_order_token": "hw1.payload.signature",
        "semantic_input": semantic_result,
    }]


def test_boris_execute_forwards_calculation_submission():
    client = FakeRuntimeClient(response=_execution_packet())
    semantic_result = {"candidate_result": {"summary": "Host result"}}

    run_boris_execute(
        session_id="host-mcp",
        work_order_id="work-order-2",
        work_order_token="hw1.payload.signature",
        semantic_result=semantic_result,
        client=client,
    )

    assert client.calls == [{
        "input": None,
        "session_id": "host-mcp",
        "context": {},
        "operation": "submit",
        "work_order_id": "work-order-2",
        "work_order_token": "hw1.payload.signature",
        "semantic_result": semantic_result,
    }]


def test_public_mcp_request_has_no_legacy_operation_selector():
    schema = BorisExecuteRequest.model_json_schema()

    assert "operation" not in schema["properties"]
    assert BorisExecuteRequest(input="hello").runtime_operation == "prepare"
    assert BorisExecuteRequest(
        work_order_id="work-order-1",
        work_order_token="hw1.payload.signature",
        semantic_input={"phase": "C03"},
    ).runtime_operation == "submit"


def test_operator_terminated_hold_is_presented_as_terminal():
    packet = _execution_packet()
    packet["hold"] = {
        "handoff_version": "boris-hold-handoff/1.4",
        "status": "operator_terminated",
        "resolution_owner": "OPERATOR",
        "reason": "The operator terminated this cycle.",
        "hold_record": _hold_record(),
        "blocking_precondition": {
            **_blocking_precondition([]),
            "status": "RESOLVED",
        },
        "required_operator_input": None,
        "resolution_summary": {
            "OPERATOR_DECISION": [{
                "resolution_mode": "TERMINATE_CYCLE",
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
        "BORIS confirms that the operator terminated this cycle."
    )
    assert "do not describe the result as PASS or STOP" in text
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
            "hold_record": _hold_record(),
            "blocking_precondition": _blocking_precondition([
                "PROVIDE_INFORMATION",
                "ALLOW_CONDITIONAL_PROCEEDING",
            ]),
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


def _hold_record():
    return {
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
    }


def _blocking_precondition(options):
    return {
        "precondition_id": "hold-precondition-1",
        "condition": "RECOVERABLE_PRECONDITION_UNRESOLVED",
        "status": "UNRESOLVED",
        "owner": "OPERATOR",
        "description": "Material information remains unresolved.",
        "resolution_options": options,
    }


def _host_work_order_packet():
    return {
        "work_order_version": "boris-semantic-work-order/0.5",
        "work_order_id": "work-order-1",
        "work_order_type": "COMPILATION",
        "session_id": "host-mcp",
        "resume_count": 0,
        "status": "semantic_work_order",
        "semantic_provider": "CHATGPT_HOST_ONLY",
        "minimum_context_window_tokens": 0,
        "core_ref": {},
        "issued_at": "2026-07-26T12:00:00+00:00",
        "expires_at": "2026-07-26T12:15:00+00:00",
        "semantic_prompt": "Large semantic prompt must appear only once.",
        "response_schema": {"type": "object"},
        "bindings": {},
        "submission_contract": {
            "tool": "boris.execute",
            "operation": "submit",
            "required_arguments": [
                "operation",
                "work_order_id",
                "work_order_token",
                "semantic_input",
            ],
            "work_order_token": "hw1.payload.signature",
        },
        "limitations": ["contract_isolation_only"],
    }
