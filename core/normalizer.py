import hashlib
import json


CANONICAL_FIELDS = (
    "bois_core",
    "sima_rules",
    "boris_context",
    "meta",
)


def normalize_core(raw_core, source="", version=""):
    raw = raw_core if isinstance(raw_core, dict) else {
        "bois_core": {
            "format": "text",
            "content": str(raw_core),
        }
    }

    canonical = {
        "bois_core": _normalize_component(raw, "bois_core", "bois"),
        "sima_rules": _normalize_component(raw, "sima_rules", "sima"),
        "boris_context": _normalize_component(raw, "boris_context", "boris"),
        "meta": {
            "source": str(source or _meta_value(raw, "source")),
            "version": str(version or _meta_value(raw, "version")),
            "hash": "",
        },
    }
    canonical["meta"]["hash"] = _hash_core(canonical)
    return canonical


def _normalize_component(raw, canonical_key, alias):
    value = raw.get(canonical_key)

    if value is None:
        value = raw.get(alias, {})

    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, list):
        return {
            "items": list(value),
        }

    if value is None:
        return {}

    return {
        "content": str(value),
    }


def _meta_value(raw, key):
    meta = raw.get("meta", {})
    if isinstance(meta, dict):
        return meta.get(key, "")
    return ""


def _hash_core(core):
    hashable = {
        key: value
        for key, value in core.items()
        if key != "meta"
    }
    hashable["meta"] = {
        key: value
        for key, value in core.get("meta", {}).items()
        if key != "hash"
    }
    payload = json.dumps(hashable, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

