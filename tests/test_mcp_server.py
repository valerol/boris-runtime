from pathlib import Path

from mcp_server.server import run_boris_ask, run_boris_frame
from mcp_server.runtime_client import RuntimeAPIError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntimeClient:
    def __init__(self, response=None, error=None):
        self.response = response or {
            "session_id": "test",
            "type": "ANSWER",
            "content": "ok",
            "metadata": {},
        }
        self.error = error
        self.calls = []

    def ask(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response

    def frame(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def test_boris_ask_calls_runtime_api_client():
    client = FakeRuntimeClient()

    response = run_boris_ask(
        input="Explain BOIS Runtime",
        session_id="test",
        mode="default",
        context={"source": "mcp-test"},
        client=client,
    )

    assert response["structuredContent"] == {
        "session_id": "test",
        "type": "ANSWER",
        "content": "ok",
        "metadata": {},
    }
    assert response["content"] == [{"type": "text", "text": "ok"}]
    assert client.calls == [
        {
            "input": "Explain BOIS Runtime",
            "session_id": "test",
            "mode": "default",
            "context": {"source": "mcp-test"},
        }
    ]


def test_boris_ask_surfaces_runtime_error_payload():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }
    client = FakeRuntimeClient(error=RuntimeAPIError("HTTP 500", status_code=500, payload=error_payload))

    response = run_boris_ask(input="hello", session_id="test", client=client)

    assert response == {
        "structuredContent": error_payload,
        "content": [{"type": "text", "text": "Runtime error: failed"}],
        "isError": True,
    }


def test_boris_ask_returns_structured_adapter_error_without_payload():
    client = FakeRuntimeClient(error=RuntimeAPIError("connection failed"))

    response = run_boris_ask(input="hello", session_id="test", client=client)

    assert response["structuredContent"] == {
        "error": "runtime_api_error",
        "detail": "connection failed",
        "session_id": "test",
    }
    assert response["isError"] is True
    assert response["content"] == [{"type": "text", "text": "Runtime error: connection failed"}]


def test_boris_frame_calls_runtime_api_client_and_returns_context_packet():
    packet = _frame_packet()
    client = FakeRuntimeClient(response=packet)

    response = run_boris_frame(
        input="Explain BOIS Runtime",
        session_id="test",
        mode="default",
        context={"source": "mcp-test"},
        client=client,
    )

    assert response["structuredContent"] == packet
    assert response["content"] == [
        {
            "type": "text",
            "text": (
                "BORIS Runtime returned a context frame only. Use structuredContent "
                "as the controlling BOIS/SIMA/BORIS frame and generate the final answer yourself."
            ),
        }
    ]
    assert "isError" not in response
    assert client.calls == [
        {
            "input": "Explain BOIS Runtime",
            "session_id": "test",
            "mode": "default",
            "context": {"source": "mcp-test"},
        }
    ]


def test_boris_frame_surfaces_runtime_error_payload():
    error_payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }
    client = FakeRuntimeClient(error=RuntimeAPIError("HTTP 500", status_code=500, payload=error_payload))

    response = run_boris_frame(input="hello", session_id="test", client=client)

    assert response == {
        "structuredContent": error_payload,
        "content": [{"type": "text", "text": "Runtime error: failed"}],
        "isError": True,
    }


def test_mcp_adapter_does_not_import_runtime_internals():
    forbidden = (
        "runtime.runtime",
        "BOISRuntime",
        "protocol.engine",
        "ProtocolEngine",
        "core.loader",
        "llm.llm_adapter",
        "OpenAIAdapter",
    )

    for path in (PROJECT_ROOT / "mcp_server").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in source, f"{path} must not reference {item}"


def _frame_packet():
    return {
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
