from mcp_server.server import normalize_frame_tool_result, normalize_tool_result


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


def test_frame_payload_becomes_context_only_tool_result():
    payload = {
        "packet_version": "boris-context/1.0",
        "frame_id": "frame-id",
        "session_id": "test",
        "input": "final answer must not appear here",
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
        "retrieved_core": [{"chunk_id": "a", "section": "s", "title": "t", "text": "chunk", "relevance": 0.5}],
        "retrieval_metadata": {
            "returned_chunks": 1,
            "total_characters": 5,
            "truncated": False,
            "max_chunks": 6,
            "max_chunk_characters": 3000,
            "max_total_characters": 12000,
        },
        "answer_instructions": ["Generate the final answer yourself."],
        "runtime_generated_prompt": "## User input\nfinal answer must not appear here",
    }

    result = normalize_frame_tool_result(payload)

    assert result["structuredContent"] == payload
    assert result["content"][0]["text"].startswith("Show the user the complete runtime_generated_prompt")
    assert "Do not hide, shorten, or omit the Runtime-generated prompt." in result["content"][0]["text"]
    assert "## User input\nfinal answer must not appear here" in result["content"][0]["text"]
    assert "isError" not in result
