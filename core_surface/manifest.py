from __future__ import annotations

import json
import re
from pathlib import PurePosixPath

from core_surface.errors import ManifestError
from core_surface.models import ComponentRecord, ManifestRecord


SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LEGACY_MANIFEST_DIALECT = "legacy-v1"
RELEASE_MANIFEST_DIALECT = "release-envelope-v1"
PUBLIC_CORE_MANIFEST_DIALECT = "public-core-v2"
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
PUBLIC_CORE_REQUIRED_FIELDS = {
    "artifact_sets",
    "artifact_version",
    "canonical_authority",
    "file_count",
    "files",
    "release_id",
}


def parse_manifest(
    payload: bytes,
    *,
    payloads: dict[str, bytes] | None = None,
) -> ManifestRecord:
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
    has_public_core_identity = {
        "release_id",
        "artifact_version",
        "canonical_authority",
        "artifact_sets",
        "file_count",
        "files",
    } <= set(raw)
    identity_count = sum((
        has_legacy_identity,
        has_release_identity,
        has_public_core_identity,
    ))
    if identity_count > 1:
        raise ManifestError("MANIFEST.json mixes manifest dialect identity fields.")
    if has_legacy_identity:
        dialect = LEGACY_MANIFEST_DIALECT
        required_fields = LEGACY_REQUIRED_FIELDS
    elif has_release_identity:
        dialect = RELEASE_MANIFEST_DIALECT
        required_fields = RELEASE_REQUIRED_FIELDS
    elif has_public_core_identity:
        dialect = PUBLIC_CORE_MANIFEST_DIALECT
        required_fields = PUBLIC_CORE_REQUIRED_FIELDS
    else:
        raise ManifestError(
            "Unknown manifest dialect: no complete supported identity is present."
        )

    missing = required_fields - set(raw)
    if missing:
        raise ManifestError(
            f"Missing {dialect} manifest fields: {sorted(missing)}"
        )

    if dialect == PUBLIC_CORE_MANIFEST_DIALECT:
        if payloads is None:
            raise ManifestError(
                "public-core-v2 parsing requires the complete package payload set."
            )
        components = _parse_public_components(raw, payloads)
        loading_order = _parse_public_files(raw["files"])
        release = _read_payload_object(payloads, "RELEASE.json")
        status = _required_text(release, "status")
    else:
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
    elif dialect == RELEASE_MANIFEST_DIALECT:
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
    else:
        release_package_id = _required_text(raw, "release_id")
        release_version = _required_text(raw, "artifact_version")
        normative_package_id = release_package_id
        normative_content_version = release_version
        package_id = normative_package_id
        artifact_version = normative_content_version
        release_flavor = str(
            release.get("profile_projection") or "PUBLIC"
        ).strip()
        root_directory = None
        transport = "directory-or-single-root-archive"
        validation_envelope = tuple(
            path
            for path in loading_order
            if path.startswith("validation/")
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


def _parse_public_files(value) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ManifestError("public-core-v2 files must be a non-empty array.")
    result = tuple(validate_relative_path(path) for path in value)
    if len(result) != len(set(result)):
        raise ManifestError("public-core-v2 files contains duplicate paths.")
    return result


def _parse_public_components(
    raw: dict,
    payloads: dict[str, bytes],
) -> tuple[ComponentRecord, ...]:
    checksums = _read_payload_object(payloads, "CHECKSUMS.json")
    entries = checksums.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("CHECKSUMS.json.entries must be a non-empty array.")
    components = []
    seen = set()
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ManifestError(
                f"CHECKSUMS.json.entries[{index}] must be an object."
            )
        path = validate_relative_path(item.get("path"))
        if path in seen:
            raise ManifestError(f"Duplicate CHECKSUMS.json path: {path}")
        seen.add(path)
        sha256 = str(item.get("sha256", "")).lower()
        if not SHA256_PATTERN.fullmatch(sha256):
            raise ManifestError(f"Invalid SHA-256 for component: {path}")
        size_bytes = item.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ManifestError(f"Invalid size_bytes for component: {path}")
        components.append(ComponentRecord(
            path=path,
            role=_public_component_role(path),
            sha256=sha256,
            size_bytes=size_bytes,
        ))
    declared_count = raw.get("file_count")
    if not isinstance(declared_count, int) or declared_count < 1:
        raise ManifestError("public-core-v2 file_count must be positive.")
    return tuple(components)


def _read_payload_object(payloads: dict[str, bytes], path: str) -> dict:
    try:
        value = json.loads(payloads[path].decode("utf-8"))
    except KeyError as exc:
        raise ManifestError(f"{path} is required by public-core-v2.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"{path} is not valid UTF-8 JSON.") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{path} must contain an object.")
    return value


def _public_component_role(path: str) -> str:
    prefix = path.split("/", 1)[0]
    return {
        "assurance": "ASSURANCE_DECLARATION",
        "fixtures": "FIXTURE_DATA",
        "lineage": "LINEAGE_DATA",
        "machine": "TYPED_PROJECTION",
        "payload": "TYPED_PAYLOAD",
        "runtime": "RUNTIME_DATA",
        "schema": "SCHEMA",
        "source": "SOURCE_MODEL",
        "trust": "TRUST_MATERIAL",
        "validation": "VALIDATION_EVIDENCE",
    }.get(prefix, "RELEASE_ARTIFACT")


def _required_text(raw: dict, field: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must be a non-empty string.")
    return value.strip()
