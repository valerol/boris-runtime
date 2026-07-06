import json
import os
from pathlib import Path

import numpy as np

from core_retriever.build_index import DEFAULT_MODEL, build_core_index


DEFAULT_CORE_PATH = "/opt/boris-core/core/BOIS_Core_v3_2_4_Sokrat.machine.json"
DEFAULT_TOP_K = 12
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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

    scores = embeddings @ query_embedding
    ranked_indexes = np.argsort(scores)[::-1][:max(top_k_value, 0)]

    selected = []
    if include_mandatory:
        selected.extend(
            _with_score(chunk, float(scores[index]))
            for index, chunk in enumerate(chunks)
            if chunk.get("mandatory")
        )
    selected.extend(_with_score(chunks[index], float(scores[index])) for index in ranked_indexes)

    return sorted(_dedupe_by_id(selected), key=lambda item: item.get("score", 0), reverse=True)


def render_retrieved_chunks(chunks):
    if not chunks:
        return "No BOIS Core chunks retrieved."

    rendered = []
    for chunk in chunks:
        score = chunk.get("score")
        score_text = "n/a" if score is None else f"{score:.4f}"
        rendered.append("\n".join((
            f"[{chunk['id']}] section={chunk['section']} title={chunk['title']} score={score_text}",
            chunk["text"],
        )))
    return "\n\n---\n\n".join(rendered)


def index_debug_summary(chunks, index_dir: str | Path | None = None):
    index_path = resolve_index_dir(index_dir)
    manifest_path = index_path / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

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
