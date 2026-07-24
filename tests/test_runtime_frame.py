import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_CHUNKS = 6
MAX_CHUNK_CHARACTERS = 3000
MAX_TOTAL_CHARACTERS = 12000


def test_context_provider_projects_verified_surface_without_llm():
    with active_runtime_imports():
        from application.context_provider import ContextProvider

        provider = ContextProvider(surface_provider=_StaticSurfaceProvider())
        packet = provider.frame("Explain BOIS", session_id="frame-unit")

    assert packet["packet_version"] == "boris-context/2.0"
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
        "projected_core",
        "projection_metadata",
        "answer_instructions",
        "runtime_generated_prompt",
    }
    assert packet["bois_frame"]["core"]["projection"] == "core_surface"
    assert packet["projected_core"][0]["chunk_id"] == "core-surface:identity"
    assert packet["projected_core"][1]["chunk_id"] == "core-surface:norm:N-BASE-001"


def test_context_provider_is_stateless_between_frames():
    with active_runtime_imports():
        from application.context_provider import ContextProvider

        provider = ContextProvider(surface_provider=_StaticSurfaceProvider())
        first = provider.frame("Explain BOIS", session_id="frame-readonly")
        second = provider.frame("Explain BOIS", session_id="frame-readonly")

    assert first["session_id"] == second["session_id"] == "frame-readonly"
    assert first["frame_id"] != second["frame_id"]
    assert first["projected_core"] == second["projected_core"]


def test_developer_mode_exposes_safe_projection_trace():
    with active_runtime_imports():
        from application.context_provider import ContextProvider

        provider = ContextProvider(surface_provider=_StaticSurfaceProvider())
        packet = provider.frame(
            "Explain BOIS",
            session_id="frame-developer",
            mode="developer",
        )

    trace = packet["developer_trace"]
    assert trace["trace_version"] == "boris-projection-trace/1.0"
    assert trace["core_surface"]["verification"] == "loaded_by_verified_core_surface"
    assert trace["projection"]["projection_kind"] == "bounded_lexical"
    assert trace["projection"]["semantic_routing"] is False
    assert trace["projection"]["candidate_count"] == 1
    assert trace["projection"]["selected_count"] == 1
    assert trace["selected_objects"][0]["object_id"] == "N-BASE-001"
    assert trace["selected_objects"][0]["reason"] == "lexical_match"
    assert trace["selected_objects"][0]["projected_chunk"]["text"]
    assert trace["excluded_objects"] == []
    assert trace["runtime_capabilities"]["semantic_executor"] == "not_invoked"
    assert trace["runtime_capabilities"]["llm"] == "not_called"
    assert set(trace["stage_timings_ms"]) == {
        "core_surface_load",
        "context_projection",
        "packet_build",
        "total",
    }
    assert all(value >= 0 for value in trace["stage_timings_ms"].values())


def test_default_and_production_modes_do_not_expose_developer_trace():
    with active_runtime_imports():
        from application.context_provider import ContextProvider

        provider = ContextProvider(surface_provider=_StaticSurfaceProvider())
        default = provider.frame("Explain BOIS", mode="default")
        production = provider.frame("Explain BOIS", mode="production")

    assert "developer_trace" not in default
    assert "developer_trace" not in production


def test_context_provider_rejects_unknown_mode():
    with active_runtime_imports():
        from application.context_provider import ContextProvider

        provider = ContextProvider(surface_provider=_StaticSurfaceProvider())
        with pytest.raises(ValueError, match="Unsupported frame mode"):
            provider.frame("Explain BOIS", mode="debug")


def test_bound_projected_core_limits_count_dedupes_and_preserves_rank():
    with active_runtime_imports():
        from application.context_packet import bound_projected_core

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

    returned, metadata = bound_projected_core(chunks)

    assert [chunk["chunk_id"] for chunk in returned] == ["a", "b", "c", "d", "e", "f"]
    assert metadata["returned_chunks"] == MAX_CHUNKS
    assert metadata["total_characters"] == 6
    assert metadata["truncated"] is True


def test_bound_projected_core_truncates_chunk_and_total_budget():
    with active_runtime_imports():
        from application.context_packet import bound_projected_core

    chunks = [
        _chunk("one", 1.0, "x" * (MAX_CHUNK_CHARACTERS + 20)),
        _chunk("two", 0.9, "y" * MAX_CHUNK_CHARACTERS),
        _chunk("three", 0.8, "z" * MAX_CHUNK_CHARACTERS),
        _chunk("four", 0.7, "q" * MAX_CHUNK_CHARACTERS),
        _chunk("five", 0.6, "r" * MAX_CHUNK_CHARACTERS),
    ]

    returned, metadata = bound_projected_core(chunks)

    assert len(returned[0]["text"]) == MAX_CHUNK_CHARACTERS
    assert metadata["total_characters"] == MAX_TOTAL_CHARACTERS
    assert metadata["returned_chunks"] == 4
    assert metadata["truncated"] is True


def test_bound_projected_core_mandatory_chunks_do_not_bypass_limits():
    with active_runtime_imports():
        from application.context_packet import bound_projected_core

    chunks = [
        {
            **_chunk(str(index), 1.0 - index / 10, "x" * 10),
            "mandatory": True,
        }
        for index in range(MAX_CHUNKS + 2)
    ]

    returned, metadata = bound_projected_core(chunks)

    assert len(returned) == MAX_CHUNKS
    assert metadata["truncated"] is True


def test_bois_frame_public_projection_uses_top_level_allowlist():
    with active_runtime_imports():
        from application.context_packet import project_public_bois_frame

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
        from application.context_packet import project_public_boris_context

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
        from application.context_packet import project_public_boris_context

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
        from application.context_packet import project_public_boris_context

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
        from application.context_packet import build_context_packet

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


def test_projected_chunk_allowlist_and_secret_redaction(monkeypatch):
    with active_runtime_imports():
        from application.context_packet import bound_projected_core

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

        returned, metadata = bound_projected_core(chunks)

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
        from application.context_packet import build_context_packet

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
                core_projection={
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
    assert packet["packet_version"] == "boris-context/2.0"


def test_normal_packet_still_contains_expected_public_fields():
    with active_runtime_imports():
        from application.context_packet import build_context_packet

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
    assert "projected_core" in packet
    assert "projection_metadata" in packet
    assert "answer_instructions" in packet
    assert "runtime_generated_prompt" in packet
    assert packet["runtime_generated_prompt"]


def test_runtime_generated_prompt_contains_public_frame_context():
    with active_runtime_imports():
        from application.context_packet import build_context_packet

        packet = build_context_packet(
            _session_stub(),
            _frame_context_stub(
                core_projection={
                    "chunks": [{
                        "id": "chunk",
                        "section": "section",
                        "title": "title",
                        "text": "projected public core",
                        "score": 0.5,
                    }]
                },
            ),
        )

    prompt = packet["runtime_generated_prompt"]
    assert "## User input\nintentional user input remains" in prompt
    assert "## Answer instructions" in prompt
    assert "Use this packet as the controlling BOIS/SIMA/BORIS frame." in prompt
    assert "## BOIS frame" in prompt
    assert '"framework": "BOIS"' in prompt
    assert "## SIMA signals" in prompt
    assert '"risk": 0.2' in prompt
    assert "## BORIS context" in prompt
    assert '"name": "BORIS"' in prompt
    assert "## Projected core" in prompt
    assert "projected public core" in prompt
    assert "provide the final answer yourself" in prompt


def test_runtime_generated_prompt_uses_sanitized_public_data(monkeypatch):
    with active_runtime_imports():
        from application.context_packet import build_context_packet

        monkeypatch.setenv("OPENAI_API_KEY", "super-secret-test-value")
        packet = build_context_packet(
            _session_stub(),
            _frame_context_stub(
                bois_frame={
                    "framework": "BOIS",
                    "core": {
                        "safe": "super-secret-test-value",
                        "system_prompt": "remove",
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
                        "safe": "super-secret-test-value",
                        "debug_context": "remove",
                    },
                    "environment": {"OPENAI_API_KEY": "remove"},
                    "session": {
                        "session_id": "session",
                        "clarification_cycles": 0,
                        "max_clarification_cycles": 3,
                        "authorization": "remove",
                    },
                },
                core_projection={
                    "chunks": [{
                        "id": "chunk",
                        "section": "section",
                        "title": "title",
                        "text": "chunk super-secret-test-value",
                        "score": 0.5,
                        "embedding": [1, 2, 3],
                    }]
                },
            ),
        )

    prompt = packet["runtime_generated_prompt"]
    for forbidden in (
        "super-secret-test-value",
        "system_prompt",
        "raw_prompt",
        "debug_context",
        "OPENAI_API_KEY",
        "authorization",
        "embedding",
        "/opt/private",
    ):
        assert forbidden not in prompt
    assert "[redacted]" in prompt


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
    core_projection=None,
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
        core_projection=core_projection or {"chunks": []},
    )


class _StaticSurfaceProvider:
    def __init__(self):
        norm = SimpleNamespace(
            norm_id="N-BASE-001",
            layer="BASE",
            norm_type="INVARIANT",
            fields={
                "card_status": "ACTIVE",
                "available_for_application": "TRUE",
                "title": "BOIS principle",
                "formulation": "Explain BOIS without inventing facts.",
            },
        )
        self.surface = SimpleNamespace(
            package_id="BOIS_TEST_CORE",
            artifact_version="1.0",
            release_package_id="BOIS_TEST_RELEASE",
            release_version="1.1",
            status="INTERNAL_STATIC_PASS",
            purpose="evaluation",
            release_flavor="PASSIVE_DATA_ONLY",
            content_set_sha256="a" * 64,
            manifest_sha256="b" * 64,
            package_identity={
                "manifest_dialect": "release-envelope-v1",
                "release_package_id": "BOIS_TEST_RELEASE",
                "release_version": "1.1",
                "normative_package_id": "BOIS_TEST_CORE",
                "normative_content_version": "1.0",
            },
            norm_ids=(norm.norm_id,),
            base_norms=(norm,),
            get_norm=lambda norm_id: norm,
        )

    def get(self):
        return self.surface


@contextmanager
def active_runtime_imports():
    prefixes = ("api", "application", "core_surface", "llm")
    saved_path = list(sys.path)
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if _matches_prefix(name, prefixes)
    }

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
