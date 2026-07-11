import sys
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = PROJECT_ROOT / "archive" / "v0-runtime"
MAX_CHUNKS = 6
MAX_CHUNK_CHARACTERS = 3000
MAX_TOTAL_CHARACTERS = 12000


class ForbiddenLLMAdapter:
    adapter_name = "forbidden"

    def call(self, *args, **kwargs):
        raise AssertionError("LLM adapter must not be called by frame()")


def test_runtime_frame_does_not_call_injected_llm(monkeypatch):
    with active_runtime_imports():
        from runtime.runtime import BOISRuntime

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
        runtime = BOISRuntime(session_id="frame-unit", llm_adapter=ForbiddenLLMAdapter())

        packet = runtime.frame("Explain BOIS")

    assert packet["packet_version"] == "boris-context/1.0"
    assert packet["session_id"] == "frame-unit"
    assert packet["runtime_mode"] == "context_provider"
    assert packet["llm_called"] is False
    assert packet["input"] == "Explain BOIS"
    assert set(packet) == {
        "packet_version",
        "frame_id",
        "session_id",
        "input",
        "runtime_mode",
        "llm_called",
        "bois_frame",
        "sima",
        "boris_context",
        "retrieved_core",
        "retrieval_metadata",
        "answer_instructions",
    }


def test_runtime_frame_does_not_mutate_protocol_session_state(monkeypatch):
    with active_runtime_imports():
        from runtime.runtime import BOISRuntime

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
        runtime = BOISRuntime(session_id="frame-readonly", llm_adapter=ForbiddenLLMAdapter())
        runtime.session.state.last_output_type = "QUESTION"
        runtime.session.state.last_decision = {
            "type": "QUESTION",
            "content": "Which target?",
            "metadata": {"gap_key": "target"},
        }
        runtime.session.state.asked_questions.append({
            "field": "target",
            "gap_key": "target",
            "question": "Which target?",
        })
        before = (
            runtime.session.state.snapshot(),
            runtime.session.state.current_input,
            dict(runtime.session.state.processed_inputs),
        )

        runtime.frame("The runtime target")

        after = (
            runtime.session.state.snapshot(),
            runtime.session.state.current_input,
            dict(runtime.session.state.processed_inputs),
        )
    assert after == before


def test_frame_context_reuses_ask_pre_llm_framing(monkeypatch):
    with active_runtime_imports():
        from runtime.runtime import BOISRuntime

        chunks = [{
            "id": "core:one",
            "section": "core",
            "title": "Core One",
            "text": "SIMA mechanism chunk",
            "score": 0.9,
        }]

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "true")
        monkeypatch.setattr(
            "prompt.prompt_builder.retrieve_core_context",
            lambda query: {
                "mode": "external",
                "chunks": chunks,
                "manifest": {"source_sha256": "abc123", "chunks_count": 1},
                "rendered": "SIMA mechanism chunk",
            },
        )
        runtime = BOISRuntime(session_id="frame-parity", llm_adapter=ForbiddenLLMAdapter())

        shared_context = runtime.engine.build_frame_context(
            runtime.session,
            "Explain SIMA",
            mutate_state=False,
        )
        packet = runtime.frame("Explain SIMA")

    assert packet["sima"] == shared_context.sima
    assert packet["bois_frame"] == shared_context.bois_frame
    assert packet["boris_context"] == shared_context.boris_context
    assert packet["retrieved_core"][0]["chunk_id"] == chunks[0]["id"]


def test_bound_retrieved_core_limits_count_dedupes_and_preserves_rank():
    with active_runtime_imports():
        from runtime.context_packet import bound_retrieved_core

    chunks = [
        _chunk("a", 0.9, "A"),
        _chunk("a", 0.8, "duplicate"),
        _chunk("b", 0.7, "B"),
        _chunk("c", 0.6, "C"),
        _chunk("d", 0.5, "D"),
        _chunk("e", 0.4, "E"),
        _chunk("f", 0.3, "F"),
        _chunk("g", 0.2, "G"),
    ]

    returned, metadata = bound_retrieved_core(chunks)

    assert [chunk["chunk_id"] for chunk in returned] == ["a", "b", "c", "d", "e", "f"]
    assert metadata["returned_chunks"] == MAX_CHUNKS
    assert metadata["total_characters"] == 6
    assert metadata["truncated"] is True


def test_bound_retrieved_core_truncates_chunk_and_total_budget():
    with active_runtime_imports():
        from runtime.context_packet import bound_retrieved_core

    chunks = [
        _chunk("one", 1.0, "x" * (MAX_CHUNK_CHARACTERS + 20)),
        _chunk("two", 0.9, "y" * MAX_CHUNK_CHARACTERS),
        _chunk("three", 0.8, "z" * MAX_CHUNK_CHARACTERS),
        _chunk("four", 0.7, "q" * MAX_CHUNK_CHARACTERS),
        _chunk("five", 0.6, "r" * MAX_CHUNK_CHARACTERS),
    ]

    returned, metadata = bound_retrieved_core(chunks)

    assert len(returned[0]["text"]) == MAX_CHUNK_CHARACTERS
    assert metadata["total_characters"] == MAX_TOTAL_CHARACTERS
    assert metadata["returned_chunks"] == 4
    assert metadata["truncated"] is True


def test_bound_retrieved_core_mandatory_chunks_do_not_bypass_limits():
    with active_runtime_imports():
        from runtime.context_packet import bound_retrieved_core

    chunks = [
        {
            **_chunk(str(index), 1.0 - index / 10, "x" * 10),
            "mandatory": True,
        }
        for index in range(MAX_CHUNKS + 2)
    ]

    returned, metadata = bound_retrieved_core(chunks)

    assert len(returned) == MAX_CHUNKS
    assert metadata["truncated"] is True


def _chunk(chunk_id, score, text):
    return {
        "id": chunk_id,
        "section": "section",
        "title": f"Title {chunk_id}",
        "text": text,
        "score": score,
    }


@contextmanager
def active_runtime_imports():
    prefixes = ("api", "core", "llm", "prompt", "protocol", "runtime")
    saved_path = list(sys.path)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if _matches_prefix(name, prefixes)
    }

    if str(ARCHIVE_ROOT) in sys.path:
        sys.path.remove(str(ARCHIVE_ROOT))
    if str(PROJECT_ROOT) in sys.path:
        sys.path.remove(str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT))
    for name in list(saved_modules):
        sys.modules.pop(name, None)

    try:
        yield
    finally:
        for name in list(sys.modules):
            if _matches_prefix(name, prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def _matches_prefix(name, prefixes):
    return name in prefixes or name.startswith(tuple(f"{prefix}." for prefix in prefixes))
