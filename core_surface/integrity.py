from __future__ import annotations

import csv
import hashlib
import io
import json

from core_surface.errors import IntegrityError
from core_surface.manifest import SHA256_PATTERN, validate_relative_path
from core_surface.models import ManifestRecord


MANIFEST_PATH = "MANIFEST.json"
CHECKSUM_PATH = "SHA256SUMS.txt"
DEPENDENCY_PATH = "assurance/DEPENDENCY_DAG.tsv"


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_integrity(manifest: ManifestRecord, payloads: dict[str, bytes]) -> None:
    _validate_inventory(manifest, payloads)
    _validate_manifest_components(manifest, payloads)
    _validate_checksum_file(payloads)
    _validate_dependency_order(manifest, payloads)


def validate_identity(manifest: ManifestRecord, payloads: dict[str, bytes]) -> dict:
    machine = _read_json(payloads, "machine/CORE_CANON.json")
    final = _read_json(payloads, "FINAL_VERIFICATION.json")

    expected = {
        "package_id": manifest.package_id,
        "artifact_version": manifest.artifact_version,
        "release_flavor": manifest.release_flavor,
    }
    _require_matching_fields(machine, expected, "machine/CORE_CANON.json")
    _require_matching_fields(
        final,
        {
            "package_id": manifest.package_id,
            "artifact_version": manifest.artifact_version,
            "status": manifest.status,
        },
        "FINAL_VERIFICATION.json",
    )
    return machine


def _validate_inventory(manifest: ManifestRecord, payloads: dict[str, bytes]) -> None:
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
