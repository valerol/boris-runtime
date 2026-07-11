import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

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


def test_bois_frame_public_projection_uses_top_level_allowlist():
    with active_runtime_imports():
        from runtime.context_packet import project_public_bois_frame

        projected = project_public_bois_frame({
            "framework": "BOIS",
            "core": {"principle": "do_not_invent_facts"},
            "input": "Explain BOIS",
            "constraints": ["do_not_invent_facts"],
            "raw_prompt": "internal prompt",
            "api_key": "secret",
            "debug_context": {"path": "/opt/private"},
            "internal_path": "/opt/private",
        })

    assert projected == {
        "framework": "BOIS",
        "core": {"principle": "do_not_invent_facts"},
        "input": "Explain BOIS",
        "constraints": ["do_not_invent_facts"],
    }


def test_boris_context_public_projection_uses_top_level_and_session_allowlists():
    with active_runtime_imports():
        from runtime.context_packet import project_public_boris_context

        projected = project_public_boris_context({
            "name": "BORIS",
            "role": "operator/domain specialization",
            "context": {"safe": "preserve"},
            "definition": "public definition",
            "session": {
                "session_id": "session",
                "clarification_cycles": 1,
                "max_clarification_cycles": 3,
                "last_decision": {"content": "remove"},
                "processed_inputs": ["remove"],
                "asked_questions": ["remove"],
                "memory": {"remove": True},
            },
            "authorization": "remove",
            "environment": {"OPENAI_API_KEY": "remove"},
            "traceback": "remove",
            "runtime_internal": {"remove": True},
        })

    assert set(projected) == {"name", "role", "context", "definition", "session"}
    assert projected["session"] == {
        "session_id": "session",
        "clarification_cycles": 1,
        "max_clarification_cycles": 3,
    }


def test_recursive_forbidden_key_removal_preserves_safe_nested_values():
    with active_runtime_imports():
        from runtime.context_packet import project_public_boris_context

        projected = project_public_boris_context({
            "context": {
                "safe_rule": "preserve",
                "nested": {
                    "system_prompt": "remove",
                    "apiKey": "remove",
                    "safe_value": 42,
                },
                "items": [
                    {
                        "authorization": "remove",
                        "rule": "preserve",
                    }
                ],
                "token_budget": 4096,
                "risk_vector": "conceptual field",
            }
        })

    assert projected["context"] == {
        "safe_rule": "preserve",
        "nested": {"safe_value": 42},
        "items": [{"rule": "preserve"}],
        "token_budget": 4096,
        "risk_vector": "conceptual field",
    }


def test_known_secret_values_are_redacted_without_mutating_source(monkeypatch):
    with active_runtime_imports():
        from runtime.context_packet import project_public_boris_context

        monkeypatch.setenv("OPENAI_API_KEY", "super-secret-test-value")
        source = {
            "context": {
                "safe_rule": "uses super-secret-test-value here",
                "nested": {"safe": "super-secret-test-value"},
            }
        }
        original = copy.deepcopy(source)

        projected = project_public_boris_context(source)

    assert source == original
    serialized = json.dumps(projected)
    assert "super-secret-test-value" not in serialized
    assert serialized.count("[redacted]") == 2


def test_sima_projection_omits_unexpected_keys():
    with active_runtime_imports():
        from runtime.context_packet import build_context_packet

        packet = build_context_packet(
            _session_stub(),
            _frame_context_stub(
                sima={
                    "risk": 0.2,
                    "uncertainty": 0.3,
                    "missing_fields": [],
                    "ambiguity_score": 0.1,
                    "raw_prompt": "secret",
                },
            ),
        )

    assert packet["sima"] == {
        "risk": 0.2,
        "uncertainty": 0.3,
        "missing_fields": [],
        "ambiguity_score": 0.1,
    }


def test_retrieved_chunk_allowlist_and_secret_redaction(monkeypatch):
    with active_runtime_imports():
        from runtime.context_packet import bound_retrieved_core

        monkeypatch.setenv("OPENAI_API_KEY", "super-secret-test-value")
        chunks = [{
            "id": "chunk",
            "section": "section",
            "title": "title",
            "text": "before super-secret-test-value after",
            "score": 0.8,
            "embedding": [1, 2, 3],
            "source_path": "/opt/private",
            "raw_query": "remove",
            "headers": {"authorization": "remove"},
            "debug_context": {"remove": True},
        }]

        returned, metadata = bound_retrieved_core(chunks)

    assert returned == [{
        "chunk_id": "chunk",
        "section": "section",
        "title": "title",
        "text": "before [redacted] after",
        "relevance": 0.8,
    }]
    assert metadata["total_characters"] == len("before [redacted] after")
    assert metadata["returned_chunks"] == 1
    assert metadata["truncated"] is False
    assert set(returned[0]) == {"chunk_id", "section", "title", "text", "relevance"}


def test_packet_wide_leakage_assertion(monkeypatch):
    with active_runtime_imports():
        from runtime.context_packet import build_context_packet

        monkeypatch.setenv("OPENAI_API_KEY", "super-secret-test-value")
        packet = build_context_packet(
            _session_stub(),
            _frame_context_stub(
                bois_frame={
                    "framework": "BOIS",
                    "core": {
                        "safe": "preserve",
                        "system_prompt": "remove",
                        "nested": {"openaiApiKey": "super-secret-test-value"},
                    },
                    "input": "intentional user input remains",
                    "constraints": ["safe"],
                    "raw_prompt": "remove",
                    "internal_path": "/opt/private",
                },
                boris_context={
                    "name": "BORIS",
                    "role": "role",
                    "context": {
                        "safe": "mentions super-secret-test-value",
                        "traceback": "remove",
                    },
                    "session": {
                        "session_id": "session",
                        "clarification_cycles": 0,
                        "max_clarification_cycles": 3,
                        "authorization": "remove",
                    },
                    "environment": {"OPENAI_API_KEY": "remove"},
                    "runtime_internal": {"path": "/opt/private"},
                },
                core_context={
                    "chunks": [{
                        "id": "chunk",
                        "section": "section",
                        "title": "title",
                        "text": "chunk super-secret-test-value",
                        "score": 0.5,
                        "authorization": "remove",
                    }]
                },
            ),
        )

    serialized = json.dumps(packet)
    for forbidden in (
        "raw_prompt",
        "system_prompt",
        "OPENAI_API_KEY",
        "authorization",
        "traceback",
        "/opt/private",
        "super-secret-test-value",
    ):
        assert forbidden not in serialized
    assert "[redacted]" in serialized
    assert packet["input"] == "intentional user input remains"
    assert packet["packet_version"] == "boris-context/1.0"


def test_normal_packet_still_contains_expected_public_fields():
    with active_runtime_imports():
        from runtime.context_packet import build_context_packet

        packet = build_context_packet(_session_stub(), _frame_context_stub())

    assert packet["bois_frame"]["framework"] == "BOIS"
    assert "core" in packet["bois_frame"]
    assert "input" in packet["bois_frame"]
    assert "constraints" in packet["bois_frame"]
    assert packet["boris_context"]["name"] == "BORIS"
    assert "role" in packet["boris_context"]
    assert "context" in packet["boris_context"]
    assert "session" in packet["boris_context"]
    assert "sima" in packet
    assert "retrieved_core" in packet
    assert "retrieval_metadata" in packet
    assert "answer_instructions" in packet


def _chunk(chunk_id, score, text):
    return {
        "id": chunk_id,
        "section": "section",
        "title": f"Title {chunk_id}",
        "text": text,
        "score": score,
    }


def _session_stub():
    return SimpleNamespace(session_id="session")


def _frame_context_stub(
    bois_frame=None,
    sima=None,
    boris_context=None,
    core_context=None,
):
    return SimpleNamespace(
        user_input="intentional user input remains",
        bois_frame=bois_frame or {
            "framework": "BOIS",
            "core": {"principle": "do_not_invent_facts"},
            "input": "intentional user input remains",
            "constraints": ["do_not_invent_facts"],
        },
        sima=sima or {
            "risk": 0.2,
            "uncertainty": 0.2,
            "missing_fields": [],
            "ambiguity_score": 0.1,
        },
        boris_context=boris_context or {
            "name": "BORIS",
            "role": "operator/domain specialization",
            "context": {"definition": "public"},
            "session": {
                "session_id": "session",
                "clarification_cycles": 0,
                "max_clarification_cycles": 3,
            },
        },
        core_context=core_context or {"chunks": []},
    )


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
