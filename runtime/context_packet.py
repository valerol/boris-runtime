from uuid import uuid4


PACKET_VERSION = "boris-context/1.0"
RUNTIME_MODE = "context_provider"
MAX_CHUNKS = 6
MAX_CHUNK_CHARACTERS = 3000
MAX_TOTAL_CHARACTERS = 12000
ANSWER_INSTRUCTIONS = [
    "Use this packet as the controlling BOIS/SIMA/BORIS frame.",
    "Generate the final answer yourself.",
    "Respect SIMA risk, uncertainty, ambiguity, and missing fields.",
    "Apply the BOIS frame, BORIS context, and retrieved BOIS Core.",
    "Do not invent missing facts.",
    "Ask only necessary and non-duplicate clarification questions.",
]


def build_context_packet(session, frame_context):
    retrieved_core, retrieval_metadata = bound_retrieved_core(
        frame_context.core_context.get("chunks", [])
    )
    return {
        "packet_version": PACKET_VERSION,
        "frame_id": str(uuid4()),
        "session_id": session.session_id,
        "input": frame_context.user_input,
        "runtime_mode": RUNTIME_MODE,
        "llm_called": False,
        "bois_frame": _sanitize_mapping(frame_context.bois_frame),
        "sima": _sanitize_sima(frame_context.sima),
        "boris_context": _sanitize_mapping(frame_context.boris_context),
        "retrieved_core": retrieved_core,
        "retrieval_metadata": retrieval_metadata,
        "answer_instructions": list(ANSWER_INSTRUCTIONS),
    }


def bound_retrieved_core(chunks):
    ranked = list(chunks or [])
    deduped = []
    seen = set()
    truncated = False

    for chunk in ranked:
        chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "").strip()
        if not chunk_id or chunk_id in seen:
            if chunk_id in seen:
                truncated = True
            continue
        seen.add(chunk_id)
        deduped.append(chunk)

    if len(deduped) > MAX_CHUNKS:
        truncated = True

    selected = deduped[:MAX_CHUNKS]
    returned = []
    total_characters = 0

    for chunk in selected:
        text = _safe_text(chunk.get("text", ""))
        if len(text) > MAX_CHUNK_CHARACTERS:
            text = text[:MAX_CHUNK_CHARACTERS]
            truncated = True

        remaining = MAX_TOTAL_CHARACTERS - total_characters
        if remaining <= 0:
            truncated = True
            break

        if len(text) > remaining:
            text = text[:remaining]
            truncated = True

        total_characters += len(text)
        returned.append({
            "chunk_id": str(chunk.get("id") or chunk.get("chunk_id") or ""),
            "section": _safe_text(chunk.get("section", "")),
            "title": _safe_text(chunk.get("title", "")),
            "text": text,
            "relevance": _safe_float(chunk.get("score", chunk.get("relevance", 0.0))),
        })

    if len(selected) < len(deduped):
        truncated = True

    return returned, {
        "returned_chunks": len(returned),
        "total_characters": total_characters,
        "truncated": truncated,
        "max_chunks": MAX_CHUNKS,
        "max_chunk_characters": MAX_CHUNK_CHARACTERS,
        "max_total_characters": MAX_TOTAL_CHARACTERS,
    }


def _sanitize_sima(signals):
    signals = signals if isinstance(signals, dict) else {}
    missing_fields = signals.get("missing_fields", [])
    if not isinstance(missing_fields, list):
        missing_fields = []
    return {
        "risk": _safe_float(signals.get("risk", 0.0)),
        "uncertainty": _safe_float(signals.get("uncertainty", 0.0)),
        "missing_fields": [_safe_text(item) for item in missing_fields],
        "ambiguity_score": _safe_float(signals.get("ambiguity_score", 0.0)),
    }


def _sanitize_mapping(value):
    if isinstance(value, dict):
        return {
            _safe_text(key): _sanitize_value(item)
            for key, item in value.items()
        }
    return {}


def _sanitize_value(value):
    if isinstance(value, dict):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return _safe_text(value)


def _safe_text(value):
    return str(value or "")


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
