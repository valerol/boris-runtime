from mcp_server.server import (
    normalize_error_result,
    normalize_execution_tool_result,
)


def test_runtime_error_payload_becomes_error_result():
    payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }

    result = normalize_error_result(payload)

    assert result == {
        "structuredContent": payload,
        "content": [{"type": "text", "text": "Runtime error: failed"}],
        "isError": True,
    }


def test_execution_payload_becomes_candidate_tool_result():
    payload = {
        "execution_version": "boris-execution/1.0",
        "session_id": "test",
        "status": "semantic_candidate",
        "phase": "C03",
        "gate": "HOLD",
        "candidate_result": {"summary": "Candidate only."},
        "norm_results": [],
        "unknowns": [],
        "conflicts": [],
        "alternatives": [],
        "limitations": ["not_independently_reviewed"],
    }

    result = normalize_execution_tool_result(payload)

    assert result["structuredContent"] == payload
    assert result["content"][0]["text"].startswith(
        "Present the Runtime ExecutionCandidate"
    )
    assert "Do not replace it with an independently generated answer" in (
        result["content"][0]["text"]
    )
    assert '"gate": "HOLD"' in result["content"][0]["text"]
    assert "isError" not in result
