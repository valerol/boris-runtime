from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from core_surface.errors import ManifestError
from core_surface.models import ComponentRecord, ManifestRecord


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LEGACY_MANIFEST_DIALECT = "legacy-v1"
RELEASE_MANIFEST_DIALECT = "release-envelope-v1"
LEGACY_REQUIRED_FIELDS = {
    "package_id",
    "artifact_version",
    "status",
    "release_flavor",
    "root_directory",
    "components",
    "loading_order",
}
RELEASE_REQUIRED_FIELDS = {
    "release_package_id",
    "release_version",
    "normative_package_id",
    "normative_content_version",
    "status",
    "transport",
    "executable_code",
    "component_count",
    "components",
    "loading_order",
    "validation_envelope",
}


def parse_manifest(payload: bytes) -> ManifestRecord:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"MANIFEST.json is not valid UTF-8 JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ManifestError("MANIFEST.json must contain an object.")

    has_legacy_identity = {"package_id", "artifact_version"} <= set(raw)
    has_release_identity = {
        "release_package_id",
        "release_version",
        "normative_package_id",
        "normative_content_version",
    } <= set(raw)
    if has_legacy_identity and has_release_identity:
        raise ManifestError(
            "MANIFEST.json mixes legacy and release-envelope identity fields."
        )
    if has_legacy_identity:
        dialect = LEGACY_MANIFEST_DIALECT
        required_fields = LEGACY_REQUIRED_FIELDS
    elif has_release_identity:
        dialect = RELEASE_MANIFEST_DIALECT
        required_fields = RELEASE_REQUIRED_FIELDS
    else:
        raise ManifestError(
            "Unknown manifest dialect: neither complete legacy nor "
            "release-envelope identity fields are present."
        )

    missing = required_fields - set(raw)
    if missing:
        raise ManifestError(
            f"Missing {dialect} manifest fields: {sorted(missing)}"
        )

    components = _parse_components(raw["components"])
    loading_order = _parse_loading_order(raw["loading_order"])
    status = _required_text(raw, "status")

    if dialect == LEGACY_MANIFEST_DIALECT:
        package_id = _required_text(raw, "package_id")
        artifact_version = _required_text(raw, "artifact_version")
        release_package_id = package_id
        release_version = artifact_version
        normative_package_id = package_id
        normative_content_version = artifact_version
        release_flavor = _required_text(raw, "release_flavor")
        root_directory = _required_text(raw, "root_directory")
        transport = None
        validation_envelope = ()
        if "/" in root_directory or "\\" in root_directory:
            raise ManifestError("root_directory must be one directory name.")
    else:
        release_package_id = _required_text(raw, "release_package_id")
        release_version = _required_text(raw, "release_version")
        normative_package_id = _required_text(raw, "normative_package_id")
        normative_content_version = _required_text(
            raw,
            "normative_content_version",
        )
        package_id = normative_package_id
        artifact_version = normative_content_version
        release_flavor = None
        root_directory = None
        transport = _required_text(raw, "transport")
        validation_envelope = _parse_validation_envelope(
            raw["validation_envelope"]
        )
        if raw["executable_code"] is not False:
            raise ManifestError(
                "Release-envelope packages must declare executable_code=false."
            )
        component_count = raw["component_count"]
        if not isinstance(component_count, int) or component_count < 1:
            raise ManifestError("component_count must be a positive integer.")
        if component_count != len(components):
            raise ManifestError(
                "component_count does not match the component inventory."
            )

    return ManifestRecord(
        manifest_dialect=dialect,
        package_id=package_id,
        artifact_version=artifact_version,
        status=status,
        release_flavor=release_flavor,
        root_directory=root_directory,
        release_package_id=release_package_id,
        release_version=release_version,
        normative_package_id=normative_package_id,
        normative_content_version=normative_content_version,
        transport=transport,
        validation_envelope=validation_envelope,
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

        required = item.get("required", True)
        if not isinstance(required, bool):
            raise ManifestError(f"Invalid required flag for component: {path}")
        if required is not True:
            raise ManifestError(
                f"Optional manifest components are not supported: {path}"
            )

        result.append(ComponentRecord(
            path=path,
            role=str(item.get("role", "")).strip(),
            sha256=sha256,
            size_bytes=size_bytes,
            required=required,
        ))

    return tuple(result)


def _parse_loading_order(value) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestError("loading_order must be a non-empty array.")
    result = tuple(validate_relative_path(path) for path in value)
    if len(result) != len(set(result)):
        raise ManifestError("loading_order contains duplicate paths.")
    return result


def _parse_validation_envelope(value) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestError("validation_envelope must be a non-empty array.")
    result = tuple(validate_relative_path(path) for path in value)
    if len(result) != len(set(result)):
        raise ManifestError("validation_envelope contains duplicate paths.")
    return result


def _required_text(raw: dict, field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string.")
    return value.strip()
