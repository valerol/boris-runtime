from mcp_server.server import (
    normalize_error_result,
    normalize_execution_tool_result,
)
from tests.review_fixtures import independent_review_packet


def test_runtime_error_payload_becomes_error_result():
    payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }

    result = normalize_error_result(payload)

    assert result["structuredContent"] == payload
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert text.startswith("BORIS Runtime failed closed.")
    assert "Do not answer the user's underlying request" in text
    assert "reuse or summarize any earlier candidate/HOLD" in text
    assert "start a new COMPILATION route" in text
    assert "Runtime error runtime_error: failed" in text


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
        "independent_review": independent_review_packet(),
        "limitations": ["not_policy_admitted"],
        "hold": {
            "required_operator_input": {
                "question": "Provide the missing information.",
            },
            "continuation_token": "v1.payload.signature",
        },
    }

    result = normalize_execution_tool_result(payload)

    assert result["structuredContent"] == payload
    assert result["content"][0]["text"].startswith(
        "BORIS returned HOLD."
    )
    assert "Do not replace it with an independently generated answer" in (
        result["content"][0]["text"]
    )
    assert '"gate": "HOLD"' in result["content"][0]["text"]
    assert "isError" not in result
