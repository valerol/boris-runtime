from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from core_surface.contracts import normalize_contract
from core_surface.errors import CatalogError, LifecycleError, PackageLayoutError
from core_surface.integrity import (
    MANIFEST_PATH,
    sha256_hex,
    validate_identity,
    validate_integrity,
)
from core_surface.manifest import parse_manifest, validate_relative_path
from core_surface.models import CoreSurface, NormRecord


MAX_FILE_COUNT = 256
MAX_FILE_SIZE = 32 * 1024 * 1024
MAX_PACKAGE_SIZE = 128 * 1024 * 1024
PURPOSES = {"evaluation", "active"}
IGNORED_DIRECTORY_NAMES = {".git"}


def load_core_surface(source, *, purpose="evaluation") -> CoreSurface:
    if purpose not in PURPOSES:
        raise LifecycleError(f"Unsupported Core Surface purpose: {purpose}")

    path = Path(source)
    if path.is_dir():
        root_directory, payloads = _read_directory(path)
        source_kind = "directory"
        archive_hash = None
    elif path.is_file() and zipfile.is_zipfile(path):
        root_directory, payloads = _read_zip(path)
        source_kind = "archive"
        archive_hash = sha256_hex(path.read_bytes())
    else:
        raise PackageLayoutError(f"Core Surface source is not a directory or ZIP: {source}")

    payloads = _normalize_public_manifest_path_case(payloads)
    content_set_hash = _hash_content_set(payloads)

    if MANIFEST_PATH not in payloads:
        raise PackageLayoutError("MANIFEST.json is missing from the package root.")

    manifest = parse_manifest(
        payloads[MANIFEST_PATH],
        payloads=payloads,
    )
    if (
        manifest.root_directory is not None
        and manifest.root_directory != root_directory
    ):
        raise PackageLayoutError(
            f"Root directory mismatch: manifest={manifest.root_directory!r}, "
            f"source={root_directory!r}"
        )

    _validate_lifecycle(manifest.status, purpose)
    validate_integrity(manifest, payloads)
    source_machine_canon = validate_identity(
        manifest,
        payloads,
        archive_sha256=archive_hash,
    )
    (
        machine_canon,
        norms_by_layer,
        norm_index,
        applicability_by_norm,
        phase_descriptions,
        phase_contexts,
        accepted_layers,
        compatibility_contract,
    ) = normalize_contract(manifest, payloads)
    release_flavor = manifest.release_flavor or source_machine_canon.get(
        "release_flavor"
    )
    if not isinstance(release_flavor, str) or not release_flavor.strip():
        raise PackageLayoutError(
            "The package does not expose a non-empty release flavor."
        )
    declared_counts = manifest.raw.get(
        "catalog_counts",
        manifest.raw.get("normative_counts"),
    )
    _validate_catalog_counts(declared_counts, norm_index, norms_by_layer)

    return CoreSurface(
        source=str(path),
        source_kind=source_kind,
        package_id=manifest.package_id,
        artifact_version=manifest.artifact_version,
        status=manifest.status,
        release_flavor=release_flavor.strip(),
        purpose=purpose,
        root_directory=root_directory,
        archive_sha256=archive_hash,
        content_set_sha256=content_set_hash,
        manifest_sha256=sha256_hex(payloads[MANIFEST_PATH]),
        components=manifest.components,
        loading_order=manifest.loading_order,
        machine_canon=machine_canon,
        norms_by_layer=norms_by_layer,
        _norm_index=norm_index,
        _payloads=payloads,
        applicability_by_norm=applicability_by_norm,
        phase_descriptions=phase_descriptions,
        phase_contexts=phase_contexts,
        accepted_layers=accepted_layers,
        compatibility_contract=compatibility_contract,
        manifest_dialect=manifest.manifest_dialect,
        release_package_id=manifest.release_package_id,
        release_version=manifest.release_version,
        normative_package_id=manifest.normative_package_id,
        normative_content_version=manifest.normative_content_version,
        transport=manifest.transport,
    )


def _read_zip(path: Path) -> tuple[str, dict[str, bytes]]:
    payloads = {}
    total_size = 0
    root_directory = None

    with zipfile.ZipFile(path) as archive:
        file_infos = [info for info in archive.infolist() if not info.is_dir()]
        if not file_infos or len(file_infos) > MAX_FILE_COUNT:
            raise PackageLayoutError("ZIP file count is empty or exceeds the safety limit.")

        for info in file_infos:
            if info.flag_bits & 0x1:
                raise PackageLayoutError(f"Encrypted ZIP entry is not supported: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise PackageLayoutError(f"ZIP symlink is not allowed: {info.filename}")
            if info.file_size > MAX_FILE_SIZE:
                raise PackageLayoutError(f"ZIP entry exceeds the size limit: {info.filename}")

            path_parts = _safe_zip_parts(info.filename)
            current_root = path_parts[0]
            if root_directory is None:
                root_directory = current_root
            elif root_directory != current_root:
                raise PackageLayoutError("ZIP must contain exactly one package root directory.")
            if len(path_parts) < 2:
                raise PackageLayoutError("Package files must be nested below the root directory.")

            relative = validate_relative_path(PurePosixPath(*path_parts[1:]).as_posix())
            if relative in payloads:
                raise PackageLayoutError(f"Duplicate ZIP entry: {relative}")
            payload = archive.read(info)
            if len(payload) != info.file_size:
                raise PackageLayoutError(f"ZIP size changed while reading: {info.filename}")
            total_size += len(payload)
            if total_size > MAX_PACKAGE_SIZE:
                raise PackageLayoutError("ZIP package exceeds the total size limit.")
            payloads[relative] = payload

    return str(root_directory), payloads


def _read_directory(path: Path) -> tuple[str, dict[str, bytes]]:
    root = _resolve_directory_root(path)
    payloads = {}
    total_size = 0

    for candidate in sorted(root.rglob("*")):
        if _is_ignored_directory_entry(candidate, root):
            continue
        if candidate.is_symlink():
            raise PackageLayoutError(f"Package symlink is not allowed: {candidate}")
        if not candidate.is_file():
            continue
        relative = validate_relative_path(candidate.relative_to(root).as_posix())
        size = candidate.stat().st_size
        if size > MAX_FILE_SIZE:
            raise PackageLayoutError(f"Package file exceeds the size limit: {relative}")
        total_size += size
        if total_size > MAX_PACKAGE_SIZE:
            raise PackageLayoutError("Package exceeds the total size limit.")
        payloads[relative] = candidate.read_bytes()

    if not payloads or len(payloads) > MAX_FILE_COUNT:
        raise PackageLayoutError("Package file count is empty or exceeds the safety limit.")
    return root.name, payloads


def _is_ignored_directory_entry(candidate: Path, root: Path) -> bool:
    try:
        relative_parts = candidate.relative_to(root).parts
    except ValueError:
        return False
    return bool(relative_parts and relative_parts[0] in IGNORED_DIRECTORY_NAMES)


def _resolve_directory_root(path: Path) -> Path:
    if (path / MANIFEST_PATH).is_file():
        return path
    candidates = [
        child
        for child in path.iterdir()
        if child.is_dir() and (child / MANIFEST_PATH).is_file()
    ]
    if len(candidates) != 1:
        raise PackageLayoutError(
            "Directory must be a package root or contain exactly one package root."
        )
    return candidates[0]


def _normalize_public_manifest_path_case(
    payloads: dict[str, bytes],
) -> dict[str, bytes]:
    """Use public-v2 manifest spelling for unambiguous case-only path differences."""

    manifest_payload = payloads.get(MANIFEST_PATH)
    if manifest_payload is None:
        return payloads
    try:
        raw = json.loads(manifest_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return payloads
    if not isinstance(raw, dict) or not {
        "release_id",
        "artifact_version",
        "canonical_authority",
        "artifact_sets",
        "file_count",
        "files",
    }.issubset(raw):
        return payloads

    declared = raw.get("files")
    if not isinstance(declared, list) or not all(
        isinstance(path, str) for path in declared
    ):
        return payloads

    declared_by_casefold = {}
    for path in declared:
        canonical = validate_relative_path(path)
        folded = canonical.casefold()
        previous = declared_by_casefold.get(folded)
        if previous is not None and previous != canonical:
            raise PackageLayoutError(
                "Public Core manifest contains case-colliding paths: "
                f"{previous!r}, {canonical!r}"
            )
        declared_by_casefold[folded] = canonical

    actual_by_casefold = {}
    for path in payloads:
        folded = path.casefold()
        previous = actual_by_casefold.get(folded)
        if previous is not None and previous != path:
            raise PackageLayoutError(
                "Core package contains case-colliding paths: "
                f"{previous!r}, {path!r}"
            )
        actual_by_casefold[folded] = path

    normalized = {}
    for path, payload in payloads.items():
        target = declared_by_casefold.get(path.casefold(), path)
        if target in normalized:
            raise PackageLayoutError(
                f"Core package path normalization collides at {target!r}."
            )
        normalized[target] = payload
    return normalized


def _safe_zip_parts(filename: str) -> tuple[str, ...]:
    if "\x00" in filename or "\\" in filename:
        raise PackageLayoutError(f"Unsafe ZIP path: {filename!r}")
    path = PurePosixPath(filename)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PackageLayoutError(f"Unsafe ZIP path: {filename!r}")
    return path.parts


def _validate_catalog_counts(
    counts,
    norm_index: dict[str, NormRecord],
    norms_by_layer: dict[str, tuple[NormRecord, ...]],
) -> None:
    if counts is None:
        return
    if not isinstance(counts, Mapping):
        raise CatalogError("catalog_counts must be an object when present.")

    expected = {
        "total": len(norm_index),
        "base": len(norms_by_layer.get("BASE", ())),
        "candidate": sum(
            record.fields.get("card_status") == "CANDIDATE"
            for record in norm_index.values()
        ),
        "active": sum(
            record.fields.get("card_status") == "ACTIVE"
            for record in norm_index.values()
        ),
        "active_for_application": sum(
            record.fields.get("available_for_application") == "TRUE"
            for record in norm_index.values()
        ),
        "personal_active": sum(
            record.layer == "PERSONAL"
            and record.fields.get("card_status") == "ACTIVE"
            for record in norm_index.values()
        ),
        "publication_candidate_inactive": sum(
            record.layer == "PUBLICATION_CANDIDATE"
            and record.fields.get("card_status") == "CANDIDATE"
            and record.fields.get("available_for_application") == "FALSE"
            for record in norm_index.values()
        ),
        "personal_ids": sum(
            record.norm_id.startswith("T-N-")
            for record in norm_index.values()
        ),
    }
    for field, actual in expected.items():
        if field in counts and counts[field] != actual:
            raise CatalogError(
                f"catalog_counts.{field} mismatch: expected {counts[field]}, got {actual}"
            )


def _validate_lifecycle(status: str, purpose: str) -> None:
    if purpose == "active" and status != "ACTIVE":
        raise LifecycleError(
            f"Package status {status!r} cannot be loaded for active use."
        )


def _hash_content_set(payloads: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path, payload in sorted(payloads.items()):
        encoded_path = path.encode("utf-8")
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()
