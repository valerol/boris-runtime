import json
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) in sys.path:
    sys.path.remove(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from core_retriever.build_index import build_core_index
from core_retriever.chunk_core import chunk_core
from core_retriever.retrieve import render_retrieved_chunks, retrieve_core_chunks
from protocol.normalization import (
    is_clarification_request_content,
    normalize_protocol_output_type,
)
from prompt.prompt_builder import PromptBuilder


class FakeEmbeddingModel:
    vocabulary = [
        "bois",
        "sima",
        "boris",
        "d/v/s",
        "evidence",
        "org-output",
        "org-sima",
        "org-phil-machine",
        "machine",
        "analysis",
        "priority",
        "россии",
        "сша",
    ]

    def encode(self, texts, normalize_embeddings=True):
        vectors = []
        for text in texts:
            lowered = text.lower()
            vector = np.array(
                [float(lowered.count(token)) for token in self.vocabulary],
                dtype=np.float32,
            )
            if not vector.any():
                vector[0] = 1.0
            if normalize_embeddings:
                vector = vector / np.linalg.norm(vector)
            vectors.append(vector)
        return np.vstack(vectors)


def fake_model_loader(_model_name):
    return FakeEmbeddingModel()


def sample_core():
    return {
        "package": "BOIS Core",
        "version": "3.2.4",
        "profile": "Sokrat",
        "canon": "BOIS definition, SIMA definition, BORIS definition",
        "evidence_boundary": "Evidence boundary defines allowed evidence.",
        "priorities": [
            {"id": "P0", "title": "Priority P0", "text": "Highest priority"},
            {"id": "P7", "title": "Priority P7", "text": "Lowest priority"},
        ],
        "organs": [
            {"id": "ORG-OUTPUT", "title": "Output organ", "text": "Answer rendering"},
            {"id": "ORG-SIMA", "title": "SIMA organ", "text": "SIMA risk analysis"},
            {
                "id": "ORG-PHIL-MACHINE",
                "title": "Philosophical machine organ",
                "text": "Philosophical machine analysis for России and США",
            },
        ],
        "terms": [
            {"term_ru": "D/V/S", "term_en": "D/V/S", "definition": "D/V/S mechanism"},
            {"term_ru": "SIMA", "term_en": "SIMA", "definition": "SIMA definition"},
        ],
        "procedures": [
            {"id": "M7", "title": "M7", "text": "Mechanism-level comparison"},
        ],
    }


def write_sample_core(tmp_path):
    core_path = tmp_path / "BOIS_Core_v3_2_4_Sokrat.machine.json"
    core_path.write_text(
        json.dumps(sample_core(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return core_path


def test_chunker_returns_multiple_chunks_and_mandatory(tmp_path):
    core_path = write_sample_core(tmp_path)

    chunks = chunk_core(core_path)

    assert len(chunks) > 5
    assert any(chunk["id"] == "organs:org-sima" for chunk in chunks)
    assert any("SIMA definition" in chunk.get("mandatory_keys", []) for chunk in chunks)
    phil_machine = next(chunk for chunk in chunks if chunk["id"] == "organs:org-phil-machine")
    assert phil_machine["mandatory"] is False


def test_build_index_writes_expected_files(tmp_path):
    core_path = write_sample_core(tmp_path)
    index_dir = tmp_path / "index"

    manifest = build_core_index(
        core_path,
        index_dir,
        model_name="fake-model",
        model_loader=fake_model_loader,
    )

    assert (index_dir / "core_chunks.json").exists()
    assert (index_dir / "core_embeddings.npy").exists()
    assert (index_dir / "manifest.json").exists()
    assert manifest["chunks_count"] > 5
    assert manifest["embedding_shape"][0] == manifest["chunks_count"]


def test_retrieve_returns_relevant_and_deduped_chunks(tmp_path):
    core_path = write_sample_core(tmp_path)
    index_dir = tmp_path / "index"
    build_core_index(core_path, index_dir, model_name="fake-model", model_loader=fake_model_loader)

    items = retrieve_core_chunks(
        "сделай сравнительный analysis россии и сша как philosophical machine",
        index_dir=index_dir,
        top_k=3,
        model_loader=fake_model_loader,
    )

    ids = [item["id"] for item in items]
    assert len(ids) == len(set(ids))
    assert any(not item.get("mandatory") for item in items)
    assert any(item["score"] >= 0 for item in items)


def test_retrieve_respects_top_k_min_score_and_mandatory_allowlist(tmp_path, monkeypatch):
    core_path = write_sample_core(tmp_path)
    index_dir = tmp_path / "index"
    build_core_index(core_path, index_dir, model_name="fake-model", model_loader=fake_model_loader)
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_MIN_SCORE", "0.95")

    items = retrieve_core_chunks(
        "analysis",
        index_dir=index_dir,
        top_k=1,
        model_loader=fake_model_loader,
    )

    semantic_items = [item for item in items if not item.get("mandatory")]
    assert len(semantic_items) <= 1
    assert all(item["score"] >= 0 for item in items)
    assert all(
        item.get("mandatory") or item["score"] >= 0.95
        for item in items
    )
    assert all(
        item["id"] in {
            "core:metadata",
            "terms:d-v-s",
            "terms:sima",
            "priorities:p0",
            "organs:org-output",
        }
        or not item.get("mandatory")
        for item in items
    )


def test_render_respects_max_chars_for_non_mandatory_chunks():
    chunks = [
        {
            "id": "core:metadata",
            "section": "metadata",
            "title": "metadata",
            "score": 0.1,
            "mandatory": True,
            "text": "mandatory grounding",
        },
        {
            "id": "organs:large",
            "section": "organs",
            "title": "large",
            "score": 0.9,
            "mandatory": False,
            "text": "x" * 500,
        },
    ]

    rendered = render_retrieved_chunks(chunks, max_chars=120)

    assert "mandatory grounding" in rendered
    assert "organs:large" not in rendered


def test_prompt_builder_includes_retrieved_active_core_when_enabled(monkeypatch):
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "true")
    monkeypatch.setattr(
        "prompt.prompt_builder.retrieve_core_context",
        lambda query: _external_context(),
    )

    builder = PromptBuilder()
    prompt = builder.build(
        core=_core_stub(),
        sima_signals={},
        bois_frame={},
        boris_context={},
        user_input="analyze",
        state=_StateStub(),
    )

    assert "RETRIEVED_ACTIVE_CORE:" in prompt
    assert "SIMA mechanism chunk" in prompt
    assert "EXTERNAL_CORE_SOURCE:" in prompt
    assert "IMMUTABLE_CORE:" not in prompt
    assert "LOCAL_FALLBACK_CORE:" not in prompt
    assert builder.last_context["core"]["core_source"] == "external"


def test_prompt_builder_omits_retrieved_active_core_when_disabled(monkeypatch):
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")

    prompt = PromptBuilder().build(
        core=_core_stub(),
        sima_signals={},
        bois_frame={},
        boris_context={},
        user_input="analyze",
        state=_StateStub(),
    )

    assert "RETRIEVED_ACTIVE_CORE:" not in prompt
    assert "LOCAL_FALLBACK_CORE:" in prompt
    assert "IMMUTABLE_CORE:" not in prompt


def test_protocol_engine_metadata_uses_external_core_when_retrieved(monkeypatch):
    with active_runtime_imports():
        from llm.llm_adapter import LLMAdapter
        from protocol.engine import ProtocolEngine
        from runtime.session import create_runtime_session

        class AnswerLLM(LLMAdapter):
            adapter_name = "mock"

            def call(self, prompt: str) -> str:
                return '{"type": "ANSWER", "content": "ok", "metadata": {}}'

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "true")
        monkeypatch.setattr(
            "prompt.prompt_builder.retrieve_core_context",
            lambda query: _external_context(),
        )
        session = create_runtime_session("core/definitions", session_id="external-core-test")
        engine = ProtocolEngine(llm_adapter=AnswerLLM())

        output = engine.run_turn(session, "analysis")

    assert output["metadata"]["core_source"] == "external"
    assert output["metadata"]["core_version"] != "local"
    assert output["metadata"]["retrieved_chunk_count"] == 1


def test_clarification_turn_adds_structured_context(monkeypatch):
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
    state = _StateStub()
    state.clarification_cycles = 1
    state.last_output_type = "CLARIFIED"
    state.current_input = "original\nClarification: supplied detail"
    state.asked_questions = [{"question": "What detail?", "gap_key": "detail"}]

    prompt = PromptBuilder().build(
        core=_core_stub(),
        sima_signals={},
        bois_frame={},
        boris_context={},
        user_input=state.current_input,
        state=state,
    )

    assert "CLARIFICATION_CONTEXT:" in prompt
    assert "ORIGINAL_REQUEST:" in prompt
    assert "USER_CLARIFICATIONS:" in prompt
    assert "Do not repeat the previous clarification question" in prompt
    assert "supplied detail" in prompt


def test_repeated_question_metadata_after_clarification():
    with active_runtime_imports():
        from protocol.decision import PostLLMController
        from runtime.session import create_runtime_session
        from runtime.state import ProtocolOutput

        session = create_runtime_session("core/definitions", session_id="repeat-test")
        session.state.clarification_cycles = 1
        session.state.asked_questions.append({
            "question": "What detail?",
            "gap_key": "detail",
        })

        output = PostLLMController().control(
            session,
            {"risk": 0, "uncertainty": 0, "missing_fields": []},
            {},
            {},
            ProtocolOutput("QUESTION", "What detail?", {}),
        ).to_dict()

    assert output["type"] == "GAP"
    assert output["metadata"]["repeated_question"] is True
    assert output["metadata"]["repeated_after_clarification"] is True
    assert output["metadata"]["previous_question"] == "What detail?"


def test_answer_clarification_request_is_normalized():
    output = _ProtocolOutputStub(
        "ANSWER",
        "Please clarify which item should be analyzed?",
        {},
    )

    normalized = normalize_protocol_output_type(output)

    assert normalized.type == "QUESTION"
    assert normalized.metadata["normalized_output_type"] is True
    assert normalized.metadata["original_output_type"] == "ANSWER"
    assert normalized.metadata["normalized_to_type"] == "QUESTION"


def test_genuine_answer_is_not_normalized():
    output = _ProtocolOutputStub(
        "ANSWER",
        "The request can be completed with the available information.",
        {},
    )

    normalized = normalize_protocol_output_type(output)

    assert normalized.type == "ANSWER"
    assert "normalized_output_type" not in normalized.metadata


def test_metadata_missing_fields_trigger_normalization():
    assert is_clarification_request_content(
        "Additional information is required.",
        {"missing_fields": ["target"]},
    )


def test_normalized_question_enters_loop_and_records_clarification(monkeypatch):
    with active_runtime_imports():
        from protocol.engine import ProtocolEngine
        from runtime.loop import ProtocolRuntimeLoop
        from runtime.session import create_runtime_session

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
        llm = _ClarifyingAnswerLLM()
        session = create_runtime_session("core/definitions", session_id="normalized-loop")
        engine = ProtocolEngine(llm_adapter=llm)
        loop = ProtocolRuntimeLoop(engine)
        provided = []

        def input_provider(output):
            provided.append(output)
            return "supplied field value"

        output = loop.run(session, "initial request", input_provider=input_provider)

        assert output["type"] == "ANSWER"
        assert len(provided) == 1
        assert provided[0]["type"] == "QUESTION"
        assert provided[0]["metadata"]["normalized_output_type"] is True
        assert session.state.clarification_cycles == 1
        assert "Clarification: supplied field value" in session.state.current_input
        assert session.state.asked_questions
        assert "CLARIFICATION_CONTEXT:" in llm.prompts[-1]
        assert "ORIGINAL_REQUEST:" in llm.prompts[-1]
        assert "USER_CLARIFICATIONS:" in llm.prompts[-1]
        assert set(output) == {"type", "content", "metadata"}


def test_missing_fields_merge_preserves_llm_fields():
    with active_runtime_imports():
        from protocol.decision import PostLLMController
        from runtime.session import create_runtime_session
        from runtime.state import ProtocolOutput

        session = create_runtime_session("core/definitions", session_id="missing-fields")
        output = PostLLMController().control(
            session,
            {"risk": 0, "uncertainty": 0, "missing_fields": []},
            {},
            {},
            ProtocolOutput("QUESTION", "Please specify the target?", {"missing_fields": ["target"]}),
        ).to_dict()

        assert output["metadata"]["missing_fields"] == ["target"]


def test_previous_answer_like_clarification_fallback_records_next_input(monkeypatch):
    with active_runtime_imports():
        from protocol.engine import ProtocolEngine
        from runtime.session import create_runtime_session

        monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "false")
        llm = _FinalAnswerLLM()
        session = create_runtime_session("core/definitions", session_id="fallback")
        session.state.current_input = "original request"
        session.state.last_output_type = "ANSWER"
        session.state.last_decision = {
            "type": "ANSWER",
            "content": "Please clarify which target should be used?",
            "metadata": {},
        }
        engine = ProtocolEngine(llm_adapter=llm)

        output = engine.run_turn(session, "supplied fallback detail")

        assert output["type"] == "ANSWER"
        assert session.state.clarification_cycles == 1
        assert "Clarification: supplied fallback detail" in session.state.current_input
        assert "CLARIFICATION_CONTEXT:" in llm.prompts[-1]


def _core_stub():
    return {
        "bois_core": {},
        "sima_rules": {},
        "boris_context": {},
        "meta": {},
    }


class _StateStub:
    last_decision = {}
    clarification_cycles = 0
    max_clarification_cycles = 3
    last_output_type = None
    current_input = ""
    asked_questions = []

    def snapshot(self):
        return {}


def _external_context():
    return {
        "mode": "external",
        "manifest": {
            "source_path": "/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json",
            "source_sha256": "abc123",
            "model_name": "fake-model",
            "chunks_count": 10,
        },
        "chunks": [
            {
                "id": "organs:org-sima",
                "section": "organs",
                "title": "ORG-SIMA",
                "score": 0.9,
                "text": "SIMA mechanism chunk",
            }
        ],
        "rendered": "[organs:org-sima] section=organs title=ORG-SIMA score=0.9000\nSIMA mechanism chunk",
    }


class _ProtocolOutputStub:
    def __init__(self, output_type, content, metadata):
        self.type = output_type
        self.content = content
        self.metadata = metadata


class _ClarifyingAnswerLLM:
    adapter_name = "mock"

    def __init__(self):
        self.calls = 0
        self.prompts = []

    def call(self, prompt: str) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.calls == 1:
            return (
                '{"type": "ANSWER", '
                '"content": "Please clarify which field should be used?", '
                '"metadata": {"missing_fields": ["field"]}}'
            )
        return '{"type": "ANSWER", "content": "final", "metadata": {}}'


class _FinalAnswerLLM:
    adapter_name = "mock"

    def __init__(self):
        self.prompts = []

    def call(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return '{"type": "ANSWER", "content": "final", "metadata": {}}'


@contextmanager
def active_runtime_imports():
    prefixes = ("core", "runtime", "protocol", "prompt", "llm")
    saved = {
        name: module
        for name, module in sys.modules.items()
        if _matches_prefix(name, prefixes)
    }
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in list(sys.modules):
            if _matches_prefix(name, prefixes):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def _matches_prefix(name, prefixes):
    return name in prefixes or name.startswith(tuple(f"{prefix}." for prefix in prefixes))
