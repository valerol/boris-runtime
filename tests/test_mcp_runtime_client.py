import json

import httpx
import pytest

from mcp_server.runtime_client import RuntimeAPIClient, RuntimeAPIError


def test_ask_posts_to_runtime_ask_with_expected_body():
    captured = {}

    def handler(request):
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "session_id": "test",
                "type": "ANSWER",
                "content": "ok",
                "metadata": {},
            },
        )

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    response = client.ask(
        input="Explain BOIS Runtime",
        session_id="test",
        mode="default",
        context={"source": "pytest"},
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/runtime/ask"
    assert captured["body"] == {
        "input": "Explain BOIS Runtime",
        "session_id": "test",
        "mode": "default",
        "context": {"source": "pytest"},
    }
    assert response == {
        "session_id": "test",
        "type": "ANSWER",
        "content": "ok",
        "metadata": {},
    }


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
        client.ask(input="hello", session_id="test")

    assert exc_info.value.status_code == 500
    assert exc_info.value.payload == error_payload


def test_frame_posts_to_runtime_frame_with_expected_body():
    captured = {}
    packet = {
        "packet_version": "boris-context/1.0",
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
        "retrieved_core": [],
        "retrieval_metadata": {
            "returned_chunks": 0,
            "total_characters": 0,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": [],
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
        mode="default",
        context={"source": "pytest"},
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/runtime/frame"
    assert captured["body"] == {
        "input": "Explain BOIS Runtime",
        "session_id": "test",
        "mode": "default",
        "context": {"source": "pytest"},
    }
    assert response == packet


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
        client.ask(input="hello")

    assert "Runtime API request failed" in str(exc_info.value)


def test_timeout_becomes_runtime_api_error():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.ask(input="hello")

    assert str(exc_info.value) == "Runtime API request timed out"


def test_invalid_json_becomes_runtime_api_error():
    client = RuntimeAPIClient(
        "http://runtime.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"not json")),
    )

    with pytest.raises(RuntimeAPIError) as exc_info:
        client.ask(input="hello")

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
