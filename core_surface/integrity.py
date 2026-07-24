from __future__ import annotations

import csv
import hashlib
import io
import json

from core_surface.errors import IntegrityError
from core_surface.manifest import (
    LEGACY_MANIFEST_DIALECT,
    RELEASE_MANIFEST_DIALECT,
    SHA256_PATTERN,
    validate_relative_path,
)
from core_surface.models import ManifestRecord


MANIFEST_PATH = "MANIFEST.json"
CHECKSUM_PATH = "SHA256SUMS.txt"
DEPENDENCY_PATH = "assurance/DEPENDENCY_DAG.tsv"
RELEASE_CHECKSUM_PATH = "CHECKSUMS.json"
RELEASE_DEPENDENCY_PATH = "assurance/BUILD_DEPENDENCY_DAG.tsv"
FINAL_VERIFICATION_PATH = "FINAL_VERIFICATION.json"
RELEASE_SCHEMA_PATH = "schema/RELEASE_ENVELOPE_SCHEMA.json"
SELF_CONSISTENCY_PATH = "assurance/SELF_CONSISTENCY_REPORT.json"
VALIDATION_RECEIPT_PATH = "assurance/VALIDATION_RECEIPT.json"


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_integrity(manifest: ManifestRecord, payloads: dict[str, bytes]) -> None:
    if manifest.manifest_dialect == LEGACY_MANIFEST_DIALECT:
        _validate_legacy_inventory(manifest, payloads)
    elif manifest.manifest_dialect == RELEASE_MANIFEST_DIALECT:
        _validate_release_inventory(manifest, payloads)
    else:
        raise IntegrityError(
            f"Unsupported manifest dialect: {manifest.manifest_dialect}"
        )
    _validate_manifest_components(manifest, payloads)
    if manifest.manifest_dialect == LEGACY_MANIFEST_DIALECT:
        _validate_checksum_file(payloads)
        _validate_dependency_order(manifest, payloads)
    else:
        _validate_release_checksum_file(manifest, payloads)
        _validate_release_dependency_order(manifest, payloads)
        _validate_release_envelope_hashes(manifest, payloads)
        _validate_release_envelope_schema(manifest, payloads)


def validate_identity(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
    *,
    archive_sha256: str | None = None,
) -> dict:
    machine = _read_json(payloads, "machine/CORE_CANON.json")
    final = _read_json(payloads, FINAL_VERIFICATION_PATH)

    if manifest.manifest_dialect == LEGACY_MANIFEST_DIALECT:
        _require_matching_fields(
            machine,
            {
                "package_id": manifest.package_id,
                "artifact_version": manifest.artifact_version,
                "release_flavor": manifest.release_flavor,
            },
            "machine/CORE_CANON.json",
        )
        _require_matching_fields(
            final,
            {
                "package_id": manifest.package_id,
                "artifact_version": manifest.artifact_version,
                "status": manifest.status,
            },
            FINAL_VERIFICATION_PATH,
        )
        return machine

    _require_matching_fields(
        machine,
        {
            "package_id": manifest.package_id,
            "artifact_version": manifest.artifact_version,
            "executable": False,
        },
        "machine/CORE_CANON.json",
    )
    _require_matching_fields(
        final,
        {
            "release_package_id": manifest.release_package_id,
            "release_version": manifest.release_version,
            "normative_package_id": manifest.normative_package_id,
            "normative_content_version": manifest.normative_content_version,
            "status": manifest.status,
            "manifest_sha256": sha256_hex(payloads[MANIFEST_PATH]),
        },
        FINAL_VERIFICATION_PATH,
    )
    declared_archive = final.get("archive_sha256")
    if (
        archive_sha256 is not None
        and isinstance(declared_archive, str)
        and SHA256_PATTERN.fullmatch(declared_archive)
        and declared_archive != archive_sha256
    ):
        raise IntegrityError(
            "archive_sha256 mismatch in FINAL_VERIFICATION.json: "
            f"expected {declared_archive!r}, got {archive_sha256!r}"
        )
    return machine


def _validate_legacy_inventory(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    actual = set(payloads)
    expected = {component.path for component in manifest.components}
    expected.update({MANIFEST_PATH, CHECKSUM_PATH})
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise IntegrityError(
            f"Package inventory mismatch; missing={missing}, unexpected={unexpected}"
        )

    if set(manifest.loading_order) != actual:
        missing = sorted(actual - set(manifest.loading_order))
        unexpected = sorted(set(manifest.loading_order) - actual)
        raise IntegrityError(
            f"loading_order mismatch; missing={missing}, unexpected={unexpected}"
        )

    declared_count = manifest.raw.get("manifest_entry_count")
    if declared_count is not None and declared_count != len(manifest.components):
        raise IntegrityError(
            "manifest_entry_count does not match the component inventory."
        )


def _validate_release_inventory(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    actual = set(payloads)
    component_paths = {component.path for component in manifest.components}
    envelope_paths = set(manifest.validation_envelope)
    if component_paths & envelope_paths:
        raise IntegrityError(
            "Release components and validation_envelope must be disjoint."
        )
    required_envelope = {
        RELEASE_CHECKSUM_PATH,
        FINAL_VERIFICATION_PATH,
        SELF_CONSISTENCY_PATH,
        VALIDATION_RECEIPT_PATH,
    }
    if not required_envelope.issubset(envelope_paths):
        missing = sorted(required_envelope - envelope_paths)
        raise IntegrityError(
            f"validation_envelope is missing required paths: {missing}"
        )

    expected = component_paths | envelope_paths | {MANIFEST_PATH}
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise IntegrityError(
            f"Package inventory mismatch; missing={missing}, unexpected={unexpected}"
        )

    expected_order = actual - {
        MANIFEST_PATH,
        RELEASE_CHECKSUM_PATH,
        FINAL_VERIFICATION_PATH,
    }
    if set(manifest.loading_order) != expected_order:
        missing = sorted(expected_order - set(manifest.loading_order))
        unexpected = sorted(set(manifest.loading_order) - expected_order)
        raise IntegrityError(
            f"loading_order mismatch; missing={missing}, unexpected={unexpected}"
        )


def _validate_manifest_components(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    for component in manifest.components:
        payload = payloads[component.path]
        if len(payload) != component.size_bytes:
            raise IntegrityError(
                f"Size mismatch for {component.path}: "
                f"expected {component.size_bytes}, got {len(payload)}"
            )
        actual_hash = sha256_hex(payload)
        if actual_hash != component.sha256:
            raise IntegrityError(
                f"SHA-256 mismatch for {component.path}: "
                f"expected {component.sha256}, got {actual_hash}"
            )


def _validate_checksum_file(payloads: dict[str, bytes]) -> None:
    try:
        text = payloads[CHECKSUM_PATH].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrityError("SHA256SUMS.txt is not valid UTF-8.") from exc

    checksums = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            raise IntegrityError(f"Malformed checksum line {line_number}.")
        expected_hash, raw_path = parts
        path = validate_relative_path(raw_path.lstrip("*"))
        expected_hash = expected_hash.lower()
        if not SHA256_PATTERN.fullmatch(expected_hash):
            raise IntegrityError(f"Invalid checksum on line {line_number}.")
        if path in checksums:
            raise IntegrityError(f"Duplicate checksum entry: {path}")
        checksums[path] = expected_hash

    expected_paths = set(payloads) - {CHECKSUM_PATH}
    if set(checksums) != expected_paths:
        missing = sorted(expected_paths - set(checksums))
        unexpected = sorted(set(checksums) - expected_paths)
        raise IntegrityError(
            f"Checksum inventory mismatch; missing={missing}, unexpected={unexpected}"
        )

    for path, expected_hash in checksums.items():
        actual_hash = sha256_hex(payloads[path])
        if actual_hash != expected_hash:
            raise IntegrityError(
                f"SHA256SUMS mismatch for {path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )


def _validate_release_checksum_file(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    checksums = _read_json(payloads, RELEASE_CHECKSUM_PATH)
    _require_matching_fields(
        checksums,
        {
            "algorithm": "SHA-256",
            "release_package_id": manifest.release_package_id,
            "release_version": manifest.release_version,
        },
        RELEASE_CHECKSUM_PATH,
    )
    entries = checksums.get("entries")
    if not isinstance(entries, dict) or not entries:
        raise IntegrityError("CHECKSUMS.json.entries must be a non-empty object.")
    if checksums.get("count") != len(entries):
        raise IntegrityError("CHECKSUMS.json count does not match its entries.")

    expected_paths = set(payloads) - {
        RELEASE_CHECKSUM_PATH,
        FINAL_VERIFICATION_PATH,
    }
    if set(entries) != expected_paths:
        missing = sorted(expected_paths - set(entries))
        unexpected = sorted(set(entries) - expected_paths)
        raise IntegrityError(
            f"Checksum inventory mismatch; missing={missing}, unexpected={unexpected}"
        )

    for raw_path, record in entries.items():
        path = validate_relative_path(raw_path)
        if not isinstance(record, dict):
            raise IntegrityError(f"Invalid CHECKSUMS.json entry for {path}.")
        expected_hash = str(record.get("sha256", "")).lower()
        expected_size = record.get("size_bytes")
        if not SHA256_PATTERN.fullmatch(expected_hash):
            raise IntegrityError(f"Invalid checksum for {path}.")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise IntegrityError(f"Invalid checksum size for {path}.")
        payload = payloads[path]
        if len(payload) != expected_size:
            raise IntegrityError(
                f"CHECKSUMS.json size mismatch for {path}: "
                f"expected {expected_size}, got {len(payload)}"
            )
        actual_hash = sha256_hex(payload)
        if actual_hash != expected_hash:
            raise IntegrityError(
                f"CHECKSUMS.json hash mismatch for {path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )


def _validate_dependency_order(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    try:
        text = payloads[DEPENDENCY_PATH].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrityError(f"{DEPENDENCY_PATH} is not valid UTF-8.") from exc

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required_columns = {"path", "depends_on", "required", "load_order"}
    if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
        raise IntegrityError(f"{DEPENDENCY_PATH} is missing required columns.")

    rows = list(reader)
    paths = [validate_relative_path(row["path"]) for row in rows]
    if len(paths) != len(set(paths)):
        raise IntegrityError(f"{DEPENDENCY_PATH} contains duplicate paths.")
    if set(paths) != set(manifest.loading_order):
        raise IntegrityError(f"{DEPENDENCY_PATH} does not cover loading_order.")

    order_index = {path: index for index, path in enumerate(manifest.loading_order)}
    for row in rows:
        path = validate_relative_path(row["path"])
        if row["required"].strip().upper() != "TRUE":
            raise IntegrityError(f"Optional dependency nodes are not supported: {path}")
        try:
            dependencies = json.loads(row["depends_on"])
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"Invalid dependency list for {path}.") from exc
        if not isinstance(dependencies, list):
            raise IntegrityError(f"Dependency list for {path} must be an array.")
        for dependency in dependencies:
            dependency = validate_relative_path(dependency)
            if dependency not in order_index:
                raise IntegrityError(f"Unknown dependency for {path}: {dependency}")
            if order_index[dependency] >= order_index[path]:
                raise IntegrityError(
                    f"Dependency order violation: {dependency} must precede {path}"
                )
        try:
            declared_order = int(row["load_order"])
        except ValueError as exc:
            raise IntegrityError(f"Invalid load_order for {path}.") from exc
        if declared_order != order_index[path] + 1:
            raise IntegrityError(f"load_order mismatch for {path}.")


def _validate_release_dependency_order(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    try:
        text = payloads[RELEASE_DEPENDENCY_PATH].decode("utf-8")
    except (KeyError, UnicodeDecodeError) as exc:
        raise IntegrityError(
            f"{RELEASE_DEPENDENCY_PATH} is missing or not valid UTF-8."
        ) from exc

    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    required_columns = {
        "node_id",
        "path",
        "depends_on",
        "dependency_kind",
        "reason",
    }
    if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
        raise IntegrityError(
            f"{RELEASE_DEPENDENCY_PATH} is missing required columns."
        )

    rows = list(reader)
    paths = [validate_relative_path(row["path"]) for row in rows]
    if len(paths) != len(set(paths)):
        raise IntegrityError(
            f"{RELEASE_DEPENDENCY_PATH} contains duplicate paths."
        )
    if tuple(paths) != manifest.loading_order:
        raise IntegrityError(
            f"{RELEASE_DEPENDENCY_PATH} does not reproduce loading_order."
        )

    order_index = {path: index for index, path in enumerate(paths)}
    for row in rows:
        path = validate_relative_path(row["path"])
        dependency = row["depends_on"].strip()
        if dependency:
            dependency = validate_relative_path(dependency)
            if dependency not in order_index:
                raise IntegrityError(f"Unknown dependency for {path}: {dependency}")
            if order_index[dependency] >= order_index[path]:
                raise IntegrityError(
                    f"Dependency order violation: {dependency} must precede {path}"
                )
        if row["dependency_kind"].strip() != "LOAD_BEFORE":
            raise IntegrityError(
                f"Unsupported dependency kind for {path}: "
                f"{row['dependency_kind']!r}"
            )


def _validate_release_envelope_hashes(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    final = _read_json(payloads, FINAL_VERIFICATION_PATH)
    expected = {
        "checksums_sha256": sha256_hex(payloads[RELEASE_CHECKSUM_PATH]),
        "manifest_sha256": sha256_hex(payloads[MANIFEST_PATH]),
        "self_consistency_report_sha256": sha256_hex(
            payloads[SELF_CONSISTENCY_PATH]
        ),
        "validation_receipt_sha256": sha256_hex(
            payloads[VALIDATION_RECEIPT_PATH]
        ),
    }
    _require_matching_fields(final, expected, FINAL_VERIFICATION_PATH)


def _validate_release_envelope_schema(
    manifest: ManifestRecord,
    payloads: dict[str, bytes],
) -> None:
    schema = _read_json(payloads, RELEASE_SCHEMA_PATH)
    required = schema.get("required")
    properties = schema.get("properties")
    identity_fields = {
        "release_package_id": manifest.release_package_id,
        "release_version": manifest.release_version,
        "normative_package_id": manifest.normative_package_id,
        "normative_content_version": manifest.normative_content_version,
        "status": manifest.status,
    }
    if not isinstance(required, list) or not set(identity_fields).issubset(required):
        raise IntegrityError(
            "RELEASE_ENVELOPE_SCHEMA.json lacks required identity fields."
        )
    if not isinstance(properties, dict):
        raise IntegrityError(
            "RELEASE_ENVELOPE_SCHEMA.json.properties must be an object."
        )
    for field, value in identity_fields.items():
        definition = properties.get(field)
        if not isinstance(definition, dict):
            raise IntegrityError(
                f"RELEASE_ENVELOPE_SCHEMA.json lacks {field!r}."
            )
        declared_const = definition.get("const")
        if declared_const is not None and declared_const != value:
            raise IntegrityError(
                f"{field} mismatch in RELEASE_ENVELOPE_SCHEMA.json: "
                f"expected {value!r}, got {declared_const!r}"
            )


def _read_json(payloads: dict[str, bytes], path: str) -> dict:
    if path not in payloads:
        raise IntegrityError(f"Required identity surface is missing: {path}")
    try:
        value = json.loads(payloads[path].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"{path} is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"{path} must contain an object.")
    return value


def _require_matching_fields(value: dict, expected: dict, path: str) -> None:
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            raise IntegrityError(
                f"{field} mismatch in {path}: "
                f"expected {expected_value!r}, got {value.get(field)!r}"
            )
