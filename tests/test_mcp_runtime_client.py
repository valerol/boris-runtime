import json

import httpx
import pytest

from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


def test_runtime_error_json_is_available_on_runtime_api_error():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500, json=error_payload)),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.frame(input="hello", session_id="test")

    assert exc_info.value.status_code == 500
    assert exc_info.value.payload == error_payload


def test_frame_posts_to_runtime_frame_with_expected_body():
    captured = {}
    packet = {
        "packet_version": "boris-context/2.0",
        "frame_id": "frame-id",
        "session_id": "test",
        "input": "Explain BOIS Runtime",
        "runtime_mode": "context_provider",
        "llm_called": False,
        "bois_frame": {},
        "sima": {
            "risk": 0.2,
            "uncertainty": 0.2,
            "missing_fields": [],
            "ambiguity_score": 0.1,
        },
        "boris_context": {},
        "projected_core": [],
        "projection_metadata": {
            "returned_chunks": 0,
            "total_characters": 0,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": [],
        "runtime_generated_prompt": "## User input\nExplain BOIS Runtime",
    }

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=packet)

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    response = client.frame(
        input="Explain BOIS Runtime",
        session_id="test",
        context={"source": "pytest"},
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/runtime/frame"
    assert captured["body"] == {
        "input": "Explain BOIS Runtime",
        "session_id": "test",
        "context": {"source": "pytest"},
    }
    assert response == packet


def test_execute_posts_to_runtime_execute_with_expected_body():
    captured = {}
    candidate = {
        "execution_version": "boris-execution/1.0",
        "session_id": "test",
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": "HOLD",
        "candidate_result": None,
        "candidate_unavailable_reason": "No safe candidate is available.",
        "norm_results": [],
        "unknowns": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": [
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
    }

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=candidate)

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    response = client.execute(
        input="Explain BOIS Runtime",
        session_id="test",
        context={"source": "pytest"},
    )

    assert captured == {
        "method": "POST",
        "path": "/runtime/execute",
        "body": {
            "input": "Explain BOIS Runtime",
            "session_id": "test",
            "context": {"source": "pytest"},
        },
    }
    assert response == candidate


def test_execute_resume_posts_only_signed_continuation_material():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(
            request.content.decode("utf-8")
        )
        return httpx.Response(
            200,
            json={
                "execution_version": "boris-execution/1.0",
                "session_id": "test",
                "status": "semantic_candidate",
                "phase": "C03",
                "gate": "PASS",
                "candidate_result": {"summary": "Resumed candidate."},
                "norm_results": [],
                "unknowns": [],
                "conflicts": [],
                "alternatives": [],
                "limitations": [],
            },
        )

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )
    resume = {
        "continuation_token": "v1.payload.signature",
        "operator_input": {
            "resolution_mode": "ALLOW_CONDITIONAL_PROCEEDING",
            "statement": "Conditional analysis is allowed.",
            "values": {},
            "resolved_unknowns": [],
        },
    }

    client.execute(session_id="test", resume=resume)

    assert captured["body"] == {
        "session_id": "test",
        "context": {},
        "resume": resume,
    }


def test_execute_posts_host_prepare_and_submit_contracts():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"status": "ok"})

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )
    client.execute(
        operation="prepare",
        input="Explain BOIS Runtime",
        session_id="host-client",
    )
    semantic_result = {"candidate_result": {"summary": "Host"}}
    client.execute(
        operation="submit",
        session_id="host-client",
        work_order_id="work-order-1",
        work_order_token="hw1.payload.signature",
        semantic_input=semantic_result,
    )
    client.execute(
        operation="submit",
        session_id="host-client",
        work_order_id="work-order-2",
        work_order_token="hw1.payload.signature",
        semantic_result=semantic_result,
    )

    assert captured == [
        {
            "input": "Explain BOIS Runtime",
            "session_id": "host-client",
            "context": {},
            "operation": "prepare",
        },
        {
            "session_id": "host-client",
            "context": {},
            "operation": "submit",
            "work_order_id": "work-order-1",
            "work_order_token": "hw1.payload.signature",
            "semantic_input": semantic_result,
        },
        {
            "session_id": "host-client",
            "context": {},
            "operation": "submit",
            "work_order_id": "work-order-2",
            "work_order_token": "hw1.payload.signature",
            "semantic_result": semantic_result,
        },
    ]


def test_frame_runtime_error_json_is_available_on_runtime_api_error():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500, json=error_payload)),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.frame(input="hello", session_id="test")

    assert exc_info.value.status_code == 500
    assert exc_info.value.payload == error_payload


def test_connection_error_becomes_runtime_api_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.frame(input="hello")

    assert "Runtime API request failed" in str(exc_info.value)


def test_timeout_becomes_runtime_api_error():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.frame(input="hello")

    assert str(exc_info.value) == "Runtime API request timed out"


def test_invalid_json_becomes_runtime_api_error():
    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not json")),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.frame(input="hello")

    assert str(exc_info.value) == "Runtime API returned invalid JSON"
    assert exc_info.value.status_code == 200


def test_frame_connection_timeout_and_invalid_json_errors():
    def connection_handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    connection_client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(connection_handler),
    )
    with pytest.raises(RuntimeAPIError, match="Runtime API request failed"):
        connection_client.frame(input="hello")

    def timeout_handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    timeout_client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(RuntimeAPIError, match="Runtime API request timed out"):
        timeout_client.frame(input="hello")

    invalid_json_client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not json")),
    )
    with pytest.raises(RuntimeAPIError) as exc_info:
        invalid_json_client.frame(input="hello")
    assert str(exc_info.value) == "Runtime API returned invalid JSON"
    assert exc_info.value.status_code == 200
