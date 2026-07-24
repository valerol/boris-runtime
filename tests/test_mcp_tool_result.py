from mcp_server.server import normalize_error_result, normalize_frame_tool_result


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


def test_frame_payload_becomes_context_only_tool_result():
    payload = {
        "packet_version": "boris-context/2.0",
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
        "projected_core": [{"chunk_id": "a", "section": "s", "title": "t", "text": "chunk", "relevance": 0.5}],
        "projection_metadata": {
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
