import json
import os
import re
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
BOIS_FRAME_PUBLIC_FIELDS = ("framework", "core", "input", "constraints")
BORIS_CONTEXT_PUBLIC_FIELDS = ("name", "role", "context", "definition", "session")
BORIS_SESSION_PUBLIC_FIELDS = (
    "session_id",
    "clarification_cycles",
    "max_clarification_cycles",
)
FORBIDDEN_PUBLIC_KEYS = {
    "apikey",
    "openaiapikey",
    "secret",
    "secrets",
    "token",
    "accesstoken",
    "refreshtoken",
    "authorization",
    "authheader",
    "password",
    "passwd",
    "credential",
    "credentials",
    "privatekey",
    "clientsecret",
    "rawprompt",
    "systemprompt",
    "finalprompt",
    "promptpayload",
    "environment",
    "env",
    "environ",
    "environmentvariables",
    "headers",
    "httpheaders",
    "traceback",
    "stacktrace",
    "exception",
    "exceptiondata",
    "internalpath",
    "filesystempath",
    "filepath",
    "embedding",
    "embeddings",
    "vector",
    "vectors",
    "debugcontext",
    "runtimeinternal",
}
SECRET_ENV_NAME_PATTERN = re.compile(
    r"(^OPENAI_API_KEY$|_API_KEY$|_TOKEN$|_SECRET$|_PASSWORD$|_CREDENTIAL$)"
)
MIN_SECRET_VALUE_LENGTH = 8


def build_context_packet(session, frame_context):
    retrieved_core, retrieval_metadata = bound_retrieved_core(
        frame_context.core_context.get("chunks", [])
    )
    packet = {
        "packet_version": PACKET_VERSION,
        "frame_id": str(uuid4()),
        "session_id": session.session_id,
        "input": frame_context.user_input,
        "runtime_mode": RUNTIME_MODE,
        "llm_called": False,
        "bois_frame": project_public_bois_frame(frame_context.bois_frame),
        "sima": _sanitize_sima(frame_context.sima),
        "boris_context": project_public_boris_context(frame_context.boris_context),
        "retrieved_core": retrieved_core,
        "retrieval_metadata": retrieval_metadata,
        "answer_instructions": list(ANSWER_INSTRUCTIONS),
    }
    packet["runtime_generated_prompt"] = build_runtime_generated_prompt(packet)
    return packet


def build_runtime_generated_prompt(packet):
    user_input = redact_known_secrets(packet.get("input", ""))
    sections = [
        (
            "Task",
            (
                "You are ChatGPT. Generate the final user-facing answer using the "
                "public BOIS/SIMA/BORIS context below. Do not call BORIS again for "
                "this answer."
            ),
        ),
        ("User input", user_input),
        ("Answer instructions", _stable_json(packet.get("answer_instructions", []))),
        ("BOIS frame", _stable_json(packet.get("bois_frame", {}))),
        ("SIMA signals", _stable_json(packet.get("sima", {}))),
        ("BORIS context", _stable_json(packet.get("boris_context", {}))),
        ("Retrieved core", _stable_json(packet.get("retrieved_core", []))),
        (
            "Final response requirement",
            (
                "Use only the public context above as the controlling frame. "
                "Respect missing fields, risk, uncertainty, ambiguity, constraints, "
                "and retrieved core. If necessary information is missing, ask a "
                "necessary non-duplicate clarification question. Otherwise, provide "
                "the final answer yourself."
            ),
        ),
    ]
    prompt = "\n\n".join(f"## {title}\n{body}" for title, body in sections)
    return redact_known_secrets(prompt)


def project_public_bois_frame(frame):
    if not isinstance(frame, dict):
        return {}
    projected = {}
    for field in BOIS_FRAME_PUBLIC_FIELDS:
        if field in frame:
            projected[field] = sanitize_public_value(frame[field])
    return projected


def project_public_boris_context(context):
    if not isinstance(context, dict):
        return {}
    projected = {}
    for field in BORIS_CONTEXT_PUBLIC_FIELDS:
        if field not in context:
            continue
        if field == "session":
            projected[field] = project_public_boris_session(context[field])
        else:
            projected[field] = sanitize_public_value(context[field])
    return projected


def project_public_boris_session(session):
    if not isinstance(session, dict):
        return {}
    projected = {}
    for field in BORIS_SESSION_PUBLIC_FIELDS:
        if field in session:
            projected[field] = sanitize_public_value(session[field])
    return projected


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
        text = redact_known_secrets(_safe_text(chunk.get("text", "")))
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
            "chunk_id": redact_known_secrets(str(chunk.get("id") or chunk.get("chunk_id") or "")),
            "section": redact_known_secrets(_safe_text(chunk.get("section", ""))),
            "title": redact_known_secrets(_safe_text(chunk.get("title", ""))),
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


def sanitize_public_value(value):
    if isinstance(value, dict):
        return _sanitize_mapping(value)
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value]
    if isinstance(value, str):
        return redact_known_secrets(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_known_secrets(_safe_text(value))


def is_forbidden_public_key(key):
    return _normalize_public_key(key) in FORBIDDEN_PUBLIC_KEYS


def redact_known_secrets(text):
    result = str(text or "")
    for secret in _known_secret_values():
        result = result.replace(secret, "[redacted]")
    return result


def _stable_json(value):
    return redact_known_secrets(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    )


def _sanitize_mapping(value):
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if is_forbidden_public_key(key):
                continue
            sanitized[redact_known_secrets(_safe_text(key))] = sanitize_public_value(item)
        return sanitized
    return {}


def _known_secret_values():
    secrets = []
    seen = set()
    for name, value in os.environ.items():
        if not value or len(value) < MIN_SECRET_VALUE_LENGTH:
            continue
        if not SECRET_ENV_NAME_PATTERN.search(name.upper()):
            continue
        if value in seen:
            continue
        seen.add(value)
        secrets.append(value)
    return tuple(secrets)


def _normalize_public_key(key):
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def _safe_text(value):
    return str(value or "")


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
