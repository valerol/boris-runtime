from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from core_surface.errors import ManifestError
from core_surface.models import ComponentRecord, ManifestRecord


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_FIELDS = {
    "package_id",
    "artifact_version",
    "status",
    "release_flavor",
    "root_directory",
    "components",
    "loading_order",
}


def parse_manifest(payload: bytes) -> ManifestRecord:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"MANIFEST.json is not valid UTF-8 JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("MANIFEST.json must contain an object.")

    missing = REQUIRED_FIELDS - set(raw)
    if missing:
        raise ManifestError(f"Missing manifest fields: {sorted(missing)}")

    components = _parse_components(raw["components"])
    loading_order = _parse_loading_order(raw["loading_order"])
    root_directory = _required_text(raw, "root_directory")
    if "/" in root_directory or "\\" in root_directory:
        raise ManifestError("root_directory must be one directory name.")

    return ManifestRecord(
        package_id=_required_text(raw, "package_id"),
        artifact_version=_required_text(raw, "artifact_version"),
        status=_required_text(raw, "status"),
        release_flavor=_required_text(raw, "release_flavor"),
        root_directory=root_directory,
        components=components,
        loading_order=loading_order,
        raw=raw,
    )


def validate_relative_path(path: str) -> str:
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise ManifestError(f"Unsafe or empty package path: {path!r}")

    parsed = PurePosixPath(path)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ManifestError(f"Unsafe package path: {path!r}")
    return parsed.as_posix()


def _parse_components(value) -> tuple[ComponentRecord, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestError("components must be a non-empty array.")

    result = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ManifestError(f"components[{index}] must be an object.")

        path = validate_relative_path(item.get("path"))
        if path in seen:
            raise ManifestError(f"Duplicate component path: {path}")
        seen.add(path)

        sha256 = str(item.get("sha256", "")).lower()
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ManifestError(f"Invalid SHA-256 for component: {path}")

        size_bytes = item.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ManifestError(f"Invalid size_bytes for component: {path}")

        result.append(ComponentRecord(
            path=path,
            role=str(item.get("role", "")).strip(),
            sha256=sha256,
            size_bytes=size_bytes,
        ))

    return tuple(result)


def _parse_loading_order(value) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestError("loading_order must be a non-empty array.")
    result = tuple(validate_relative_path(path) for path in value)
    if len(result) != len(set(result)):
        raise ManifestError("loading_order contains duplicate paths.")
    return result


def _required_text(raw: dict, field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string.")
    return value.strip()
