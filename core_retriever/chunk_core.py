import hashlib
import json
from pathlib import Path


MAJOR_SCALAR_KEYS = {
    "package",
    "version",
    "profile",
    "canon",
    "evidence_boundary",
}

PREFERRED_ID_FIELDS = (
    "id",
    "name",
    "term_ru",
    "term_en",
    "code",
    "key",
    "title",
)

MANDATORY_CHUNK_IDS = {
    "core:metadata",
    "terms:bois",
    "terms:sima",
    "terms:boris",
    "terms:d-v-s",
    "terms:dvs",
    "priorities:p0",
    "priorities:p1",
    "priorities:p2",
    "organs:org-output",
}

MANDATORY_TITLE_KEYS = {
    "bois": "BOIS definition",
    "sima": "SIMA definition",
    "boris": "BORIS definition",
    "d/v/s": "D/V/S",
    "dvs": "D/V/S",
    "p0": "P0 priority",
    "p1": "P1 priority",
    "p2": "P2 priority",
    "org-output": "ORG-OUTPUT",
}


def load_core_json(core_path):
    path = Path(core_path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def chunk_core(core_path):
    path = Path(core_path)
    data = load_core_json(path)
    if not isinstance(data, dict):
        raise ValueError("BOIS Core machine JSON must contain a top-level object.")

    source_hash = sha256_file(path)
    chunks = []

    meta_payload = {
        key: data[key]
        for key in MAJOR_SCALAR_KEYS
        if key in data and not isinstance(data[key], list)
    }
    if meta_payload:
        chunks.append(_make_chunk(
            chunk_id="core:metadata",
            section="metadata",
            title="package/version/profile/canon/evidence_boundary",
            source_path=path,
            source_hash=source_hash,
            payload=meta_payload,
        ))

    handled_keys = set(meta_payload)
    for section in (
        "priorities",
        "organs",
        "terms",
        "procedures",
        "stop_signals",
        "tests",
        "criteria",
        "cycles",
        "conflict_policy",
        "state_schema",
        "state_schema_refs",
    ):
        if section in data:
            chunks.extend(_chunk_value(section, data[section], path, source_hash))
            handled_keys.add(section)

    for section, value in data.items():
        if section in handled_keys:
            continue
        if _is_list_of_dicts(value):
            chunks.extend(_chunk_list(section, value, path, source_hash))
        elif isinstance(value, dict):
            chunks.append(_make_chunk(
                chunk_id=f"{section}:object",
                section=section,
                title=_title_from_record(value, section),
                source_path=path,
                source_hash=source_hash,
                payload=value,
            ))

    return [_with_mandatory_metadata(chunk) for chunk in chunks]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _chunk_value(section, value, source_path, source_hash):
    if _is_list_of_dicts(value):
        return _chunk_list(section, value, source_path, source_hash)
    if isinstance(value, list):
        return [
            _make_chunk(
                chunk_id=f"{section}:{index}",
                section=section,
                title=f"{section} {index}",
                source_path=source_path,
                source_hash=source_hash,
                payload=item,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return [
            _make_chunk(
                chunk_id=f"{section}:{_stable_id(value, 'object')}",
                section=section,
                title=_title_from_record(value, section),
                source_path=source_path,
                source_hash=source_hash,
                payload=value,
            )
        ]
    return [
        _make_chunk(
            chunk_id=f"{section}:value",
            section=section,
            title=section,
            source_path=source_path,
            source_hash=source_hash,
            payload=value,
        )
    ]


def _chunk_list(section, records, source_path, source_hash):
    chunks = []
    for index, record in enumerate(records):
        stable_id = _stable_id(record, str(index))
        chunks.append(_make_chunk(
            chunk_id=f"{section}:{stable_id}",
            section=section,
            title=_title_from_record(record, f"{section} {index}"),
            source_path=source_path,
            source_hash=source_hash,
            payload=record,
        ))
    return chunks


def _make_chunk(chunk_id, section, title, source_path, source_hash, payload):
    text = _render_payload(section, title, payload)
    return {
        "id": chunk_id,
        "section": section,
        "title": title,
        "source_path": str(source_path),
        "source_hash": source_hash,
        "text": text,
    }


def _render_payload(section, title, payload):
    if isinstance(payload, str):
        rendered = payload
    else:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return f"SECTION: {section}\nTITLE: {title}\n{rendered}"


def _is_list_of_dicts(value):
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _stable_id(record, fallback):
    if isinstance(record, dict):
        for field in PREFERRED_ID_FIELDS:
            value = record.get(field)
            if value:
                return _slug(str(value))
    return _slug(str(fallback))


def _title_from_record(record, fallback):
    if isinstance(record, dict):
        for field in ("title", "name", "term_ru", "term_en", "id", "code", "key"):
            value = record.get(field)
            if value:
                return str(value)
    return str(fallback)


def _slug(value):
    return (
        value.strip()
        .lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
    )


def _with_mandatory_metadata(chunk):
    keys = []

    chunk_id = chunk["id"].lower()
    if chunk_id in MANDATORY_CHUNK_IDS:
        keys.append(chunk_id)

    title_key = _slug(chunk["title"])
    if title_key in MANDATORY_TITLE_KEYS:
        keys.append(MANDATORY_TITLE_KEYS[title_key])

    if chunk["section"] == "metadata" and "evidence_boundary" in chunk["text"]:
        keys.append("evidence boundary")

    chunk["mandatory"] = bool(keys)
    chunk["mandatory_keys"] = keys
    return chunk
