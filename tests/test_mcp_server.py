from pathlib import Path

from mcp_server.server import run_boris_frame
from mcp_server.runtime_client import RuntimeAPIError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntimeClient:
    def __init__(self, response=None, error=None):
        self.response = response or _frame_packet()
        self.error = error
        self.calls = []

    def frame(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response
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
    assert response["content"][0]["type"] == "text"
    assert response["content"][0]["text"].startswith("Show the user the complete runtime_generated_prompt")
    assert "Do not hide, shorten, or omit the Runtime-generated prompt." in response["content"][0]["text"]
    assert "## User input\nExplain BOIS Runtime" in response["content"][0]["text"]
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
        "application.context_provider",
        "core_surface",
        "llm.llm_adapter",
        "OpenAIAdapter",
    )

    for path in (PROJECT_ROOT / "mcp_server").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for item in forbidden:
            assert item not in source, f"{path} must not reference {item}"


def _frame_packet():
    return {
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
