import json

import numpy as np

from core_retriever.build_index import build_core_index
from core_retriever.chunk_core import chunk_core
from core_retriever.retrieve import retrieve_core_chunks
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
    assert any("ORG-PHIL-MACHINE" in chunk.get("mandatory_keys", []) for chunk in chunks)


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
    assert "organs:org-phil-machine" in ids
    assert any(item["score"] >= 0 for item in items)


def test_prompt_builder_includes_retrieved_active_core_when_enabled(monkeypatch):
    monkeypatch.setenv("BORIS_CORE_RETRIEVER_ENABLED", "true")
    monkeypatch.setattr(
        "prompt.prompt_builder.retrieve_core_chunks",
        lambda query: [
            {
                "id": "organs:org-sima",
                "section": "organs",
                "title": "ORG-SIMA",
                "score": 0.9,
                "text": "SIMA mechanism chunk",
            }
        ],
    )

    prompt = PromptBuilder().build(
        core=_core_stub(),
        sima_signals={},
        bois_frame={},
        boris_context={},
        user_input="analyze",
        state=_StateStub(),
    )

    assert "RETRIEVED_ACTIVE_CORE:" in prompt
    assert "SIMA mechanism chunk" in prompt


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


def _core_stub():
    return {
        "bois_core": {},
        "sima_rules": {},
        "boris_context": {},
        "meta": {},
    }


class _StateStub:
    last_decision = {}

    def snapshot(self):
        return {}
