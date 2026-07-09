from mcp_server.server import normalize_tool_result


def test_runtime_success_payload_becomes_structured_result():
    payload = {
        "session_id": "test",
        "type": "ANSWER",
        "content": "final answer",
        "metadata": {"llm_adapter": "mock"},
    }

    result = normalize_tool_result(payload)

    assert result["structuredContent"] == payload
    assert result["content"] == [{"type": "text", "text": "final answer"}]
    assert "isError" not in result


def test_runtime_question_content_appears_in_text_content():
    payload = {
        "session_id": "test",
        "type": "QUESTION",
        "content": "Which target should I analyze?",
        "metadata": {"missing_fields": ["target"]},
    }

    result = normalize_tool_result(payload)

    assert result["structuredContent"]["type"] == "QUESTION"
    assert result["structuredContent"]["metadata"] == {"missing_fields": ["target"]}
    assert result["content"] == [{"type": "text", "text": "Which target should I analyze?"}]


def test_runtime_error_payload_becomes_error_result():
    payload = {
        "error": "runtime_error",
        "detail": "failed",
        "session_id": "test",
    }

    result = normalize_tool_result(payload)

    assert result == {
        "structuredContent": payload,
        "content": [{"type": "text", "text": "Runtime error: failed"}],
        "isError": True,
    }
