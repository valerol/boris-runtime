import json
import os
from pathlib import Path

import numpy as np

from core_retriever.build_index import DEFAULT_MODEL, build_core_index


DEFAULT_CORE_PATH = "/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json"
DEFAULT_TOP_K = 12
DEFAULT_MIN_SCORE = 0.0
DEFAULT_MAX_CHARS = 12000
PROJECT_ROOT = Path(__file__).resolve().parents[1]

GENERIC_BOOSTS = {
    "bois": ("bois",),
    "sima": ("sima", "risk"),
    "boris": ("boris",),
    "d/v/s": ("d/v/s", "dvs"),
    "m7": ("m7",),
    "m@s": ("m@s",),
    "oper": ("oper", "operome"),
    "operome": ("operome", "oper"),
    "philosophical machine": ("philosophical machine", "философ"),
    "comparison": ("comparison", "analysis", "сравн"),
    "analysis": ("analysis", "анализ"),
    "risk": ("risk", "sima"),
    "evidence": ("evidence", "доказ"),
    "substrate": ("substrate", "субстрат"),
}


class CoreRetrieverError(RuntimeError):
    pass


def retrieve_core_chunks(
    query: str,
    index_dir: str | Path | None = None,
    top_k: int | None = None,
    include_mandatory: bool = True,
    model_loader=None,
) -> list[dict]:
    index_path = resolve_index_dir(index_dir)
    top_k_value = safe_int(
        top_k if top_k is not None else os.getenv("BORIS_CORE_RETRIEVER_TOP_K"),
        DEFAULT_TOP_K,
    )
    min_score = safe_float(os.getenv("BORIS_CORE_RETRIEVER_MIN_SCORE"), DEFAULT_MIN_SCORE)

    _ensure_index(index_path, model_loader=model_loader)
    chunks, embeddings, manifest = _load_index(index_path)
    if not chunks:
        return []

    model_name = manifest.get("model_name") or os.getenv("BORIS_CORE_RETRIEVER_MODEL") or DEFAULT_MODEL
    model = _load_model(model_name, model_loader=model_loader)
    query_embedding = np.asarray(
        model.encode([query or ""], normalize_embeddings=True),
        dtype=np.float32,
    )[0]

    scores = _apply_generic_boosts(
        query=query or "",
        chunks=chunks,
        scores=embeddings @ query_embedding,
    )
    ranked_indexes = []
    for index in np.argsort(scores)[::-1]:
        score = float(scores[index])
        if score < min_score or score < 0:
            continue
        ranked_indexes.append(index)
        if len(ranked_indexes) >= max(top_k_value, 0):
            break

    selected = []
    if include_mandatory:
        selected.extend(
            _with_score(chunk, float(scores[index]))
            for index, chunk in enumerate(chunks)
            if chunk.get("mandatory")
        )
    selected.extend(_with_score(chunks[index], float(scores[index])) for index in ranked_indexes)

    return sorted(_dedupe_by_id(selected), key=lambda item: item.get("score", 0), reverse=True)


def retrieve_core_context(
    query: str,
    index_dir: str | Path | None = None,
    top_k: int | None = None,
    include_mandatory: bool = True,
    model_loader=None,
):
    index_path = resolve_index_dir(index_dir)
    chunks = retrieve_core_chunks(
        query=query,
        index_dir=index_path,
        top_k=top_k,
        include_mandatory=include_mandatory,
        model_loader=model_loader,
    )
    manifest = load_manifest(index_path)
    return {
        "mode": "external",
        "chunks": chunks,
        "manifest": manifest,
        "rendered": render_retrieved_chunks(chunks),
    }


def render_retrieved_chunks(chunks, max_chars=None):
    if not chunks:
        return "No BOIS Core chunks retrieved."

    char_budget = safe_positive_int(
        max_chars if max_chars is not None else os.getenv("BORIS_CORE_RETRIEVER_MAX_CHARS"),
        DEFAULT_MAX_CHARS,
    )
    rendered = []
    used_chars = 0
    for chunk in chunks:
        score = chunk.get("score")
        score_text = "n/a" if score is None else f"{score:.4f}"
        block = "\n".join((
            f"[{chunk['id']}] section={chunk['section']} title={chunk['title']} score={score_text}",
            chunk["text"],
        ))
        projected = used_chars + len(block) + (5 if rendered else 0)
        if char_budget > 0 and projected > char_budget and not chunk.get("mandatory"):
            break
        rendered.append(block)
        used_chars = projected
    return "\n\n---\n\n".join(rendered)


def index_debug_summary(chunks, index_dir: str | Path | None = None):
    index_path = resolve_index_dir(index_dir)
    manifest = load_manifest(index_path)

    return {
        "source_path": manifest.get("source_path", ""),
        "source_sha256": manifest.get("source_sha256", ""),
        "chunks_count": manifest.get("chunks_count", 0),
        "selected_chunk_ids": [chunk.get("id") for chunk in chunks],
        "selected_chunk_scores": {
            chunk.get("id"): chunk.get("score")
            for chunk in chunks
        },
    }


def load_manifest(index_dir: str | Path | None = None):
    manifest_path = resolve_index_dir(index_dir) / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def resolve_index_dir(index_dir=None):
    if index_dir:
        return Path(index_dir)

    configured = os.getenv("BORIS_CORE_INDEX_DIR")
    if configured:
        return Path(configured)

    return PROJECT_ROOT / "data" / "core_index"


def core_retriever_enabled():
    return os.getenv("BORIS_CORE_RETRIEVER_ENABLED", "true").strip().lower() == "true"


def core_retriever_debug_enabled():
    return (
        os.getenv("BORIS_RUNTIME_MODE", "").strip().lower() == "dev"
        or os.getenv("BOIS_DEBUG_PROMPT", "").strip().lower() == "true"
    )


def safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_positive_int(value, default):
    parsed = safe_int(value, default)
    return parsed if parsed > 0 else default


def _ensure_index(index_path, model_loader=None):
    required = [
        index_path / "core_chunks.json",
        index_path / "core_embeddings.npy",
        index_path / "manifest.json",
    ]
    if all(path.exists() for path in required):
        return

    if os.getenv("BORIS_CORE_RETRIEVER_AUTO_BUILD", "false").strip().lower() == "true":
        core_path = os.getenv("BORIS_CORE_PATH", DEFAULT_CORE_PATH)
        model_name = os.getenv("BORIS_CORE_RETRIEVER_MODEL", DEFAULT_MODEL)
        build_core_index(core_path, index_path, model_name=model_name, model_loader=model_loader)
        return

    missing = ", ".join(str(path) for path in required if not path.exists())
    raise CoreRetrieverError(
        "BOIS Core index is missing. Build it with "
        "python -m core_retriever.build_index --core <core-json> --out <index-dir>. "
        f"Missing: {missing}"
    )


def _load_index(index_path):
    chunks_path = index_path / "core_chunks.json"
    embeddings_path = index_path / "core_embeddings.npy"
    manifest_path = index_path / "manifest.json"

    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    embeddings = np.load(embeddings_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return chunks, embeddings, manifest


def _load_model(model_name, model_loader=None):
    if model_loader:
        return model_loader(model_name)

    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _with_score(chunk, score):
    item = dict(chunk)
    item["score"] = score
    return item


def _apply_generic_boosts(query, chunks, scores):
    boosted = np.asarray(scores, dtype=np.float32).copy()
    query_lower = query.lower()
    active_terms = [
        term
        for term in GENERIC_BOOSTS
        if term in query_lower or any(trigger in query_lower for trigger in GENERIC_BOOSTS[term])
    ]
    if not active_terms:
        return boosted

    for index, chunk in enumerate(chunks):
        haystack = " ".join((
            str(chunk.get("id", "")),
            str(chunk.get("section", "")),
            str(chunk.get("title", "")),
            str(chunk.get("text", "")),
        )).lower()
        matches = 0
        for term in active_terms:
            if term in haystack or any(trigger in haystack for trigger in GENERIC_BOOSTS[term]):
                matches += 1
        if matches:
            boosted[index] += min(0.15, 0.03 * matches)
    return boosted


def _dedupe_by_id(chunks):
    seen = set()
    deduped = []
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        deduped.append(chunk)
    return deduped
