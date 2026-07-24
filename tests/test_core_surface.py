import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from application.context_projection import project_core_context
from application.context_provider import CoreSurfaceProvider, CoreSurfaceUnavailable
from core_surface import (
    CatalogError,
    IntegrityError,
    LifecycleError,
    PackageLayoutError,
    load_core_surface,
)


def test_candidate_directory_loads_for_evaluation_and_separates_layers(tmp_path):
    package_root = build_package(tmp_path)

    surface = load_core_surface(package_root)

    assert surface.package_id == "BOIS_TEST_CORE_V1"
    assert surface.artifact_version == "1.0"
    assert surface.status == "INTERNAL_CANDIDATE"
    assert surface.source_kind == "directory"
    assert surface.archive_sha256 is None
    assert len(surface.content_set_sha256) == 64
    assert [record.norm_id for record in surface.base_norms] == ["N-BASE-001"]
    assert [record.norm_id for record in surface.norms_for_layer("PERSONAL")] == [
        "T-N-001"
    ]
    assert surface.get_norm("N-FUTURE-001").norm_type == "FUTURE_STATEMENT_TYPE"
    assert surface.summary()["norm_type_policy"] == "opaque_source_values"

    with pytest.raises(TypeError):
        surface.get_norm("N-BASE-001").fields["title"] = "changed"


def test_candidate_cannot_be_loaded_for_active_use(tmp_path):
    package_root = build_package(tmp_path)

    with pytest.raises(LifecycleError, match="cannot be loaded for active use"):
        load_core_surface(package_root, purpose="active")


def test_zip_loads_without_extraction_and_reports_archive_hash(tmp_path):
    package_root = build_package(tmp_path)
    archive_path = tmp_path / "core.zip"
    write_zip(package_root, archive_path)

    surface = load_core_surface(archive_path)
    directory_surface = load_core_surface(package_root)

    assert surface.source_kind == "archive"
    assert surface.archive_sha256 == hashlib.sha256(
        archive_path.read_bytes()
    ).hexdigest()
    assert len(surface.content_set_sha256) == 64
    assert surface.content_set_sha256 == directory_surface.content_set_sha256
    assert surface.read_json("machine/CORE_CANON.json")["executable"] is False


def test_modified_component_is_rejected(tmp_path):
    package_root = build_package(tmp_path)
    catalog = package_root / "assurance" / "NORM_CATALOG.tsv"
    catalog.write_text(catalog.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(IntegrityError, match="Size mismatch|SHA-256 mismatch"):
        load_core_surface(package_root)


def test_duplicate_norm_id_is_rejected_after_valid_repack(tmp_path):
    package_root = build_package(tmp_path, duplicate_norm=True)

    with pytest.raises(CatalogError, match="Duplicate norm ID"):
        load_core_surface(package_root)


def test_zip_path_traversal_is_rejected(tmp_path):
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape/MANIFEST.json", "{}")

    with pytest.raises(PackageLayoutError, match="Unsafe ZIP path"):
        load_core_surface(archive_path)


def test_release_manifest_preserves_release_and_normative_identity(tmp_path):
    package_root = build_release_package(tmp_path)
    archive_path = tmp_path / "release-core.zip"
    write_zip(package_root, archive_path)

    surface = load_core_surface(archive_path)

    assert surface.manifest_dialect == "release-envelope-v1"
    assert surface.package_id == "BOIS_TEST_NORMATIVE_V2"
    assert surface.artifact_version == "2.0"
    assert surface.release_package_id == "BOIS_TEST_RELEASE_V3"
    assert surface.release_version == "3.0"
    assert surface.normative_package_id == "BOIS_TEST_NORMATIVE_V2"
    assert surface.normative_content_version == "2.0"
    assert surface.status == "INTERNAL_STATIC_PASS"
    assert surface.transport == "SINGLE_PASSIVE_DATA_ZIP"
    assert surface.release_flavor == "PASSIVE_DATA_ONLY"
    assert dict(surface.package_identity) == {
        "manifest_dialect": "release-envelope-v1",
        "release_package_id": "BOIS_TEST_RELEASE_V3",
        "release_version": "3.0",
        "normative_package_id": "BOIS_TEST_NORMATIVE_V2",
        "normative_content_version": "2.0",
    }


def test_release_static_pass_does_not_authorize_active_use(tmp_path):
    package_root = build_release_package(tmp_path)

    with pytest.raises(LifecycleError, match="cannot be loaded for active use"):
        load_core_surface(package_root, purpose="active")


def test_context_projection_uses_verified_surface_records(tmp_path):
    surface = load_core_surface(build_package(tmp_path))

    projection = project_core_context(surface, "Personal")

    assert projection["mode"] == "core_surface_projection"
    assert projection["metadata"]["core_source"] == "core_surface"
    assert projection["metadata"]["semantic_routing"] is False
    assert projection["chunks"][0]["id"] == "core-surface:identity"
    assert projection["chunks"][1]["id"] == "core-surface:norm:T-N-001"


def test_context_projection_falls_back_only_to_available_base_norms(tmp_path):
    surface = load_core_surface(build_package(tmp_path))

    projection = project_core_context(surface, "unmatched-query-token")

    assert [chunk["id"] for chunk in projection["chunks"]] == [
        "core-surface:identity",
        "core-surface:norm:N-BASE-001",
    ]


def test_application_provider_caches_one_verified_surface(tmp_path):
    package_root = build_package(tmp_path)
    provider = CoreSurfaceProvider(source=str(package_root))

    first = provider.get()
    second = provider.get()

    assert first is second
    assert first.package_id == "BOIS_TEST_CORE_V1"


def test_application_provider_rejects_legacy_machine_json(tmp_path):
    machine_json = tmp_path / "CORE_CANON.json"
    machine_json.write_text("{}", encoding="utf-8")
    provider = CoreSurfaceProvider(source=str(machine_json))

    with pytest.raises(CoreSurfaceUnavailable):
        provider.get()


def test_release_validation_envelope_tampering_is_rejected(tmp_path):
    package_root = build_release_package(tmp_path)
    receipt = package_root / "assurance" / "VALIDATION_RECEIPT.json"
    receipt.write_text('{"checks":{}}', encoding="utf-8")

    with pytest.raises(IntegrityError, match="CHECKSUMS.json"):
        load_core_surface(package_root)


def build_package(tmp_path: Path, *, duplicate_norm=False) -> Path:
    root = tmp_path / "bois-test-core"
    files = {
        "machine/CORE_CANON.json": json_bytes({
            "package_id": "BOIS_TEST_CORE_V1",
            "artifact_version": "1.0",
            "release_flavor": "PASSIVE_DATA_ONLY",
            "executable": False,
        }),
        "FINAL_VERIFICATION.json": json_bytes({
            "package_id": "BOIS_TEST_CORE_V1",
            "artifact_version": "1.0",
            "status": "INTERNAL_CANDIDATE",
        }),
    }
    norm_rows = [
        "norm_id\tlayer\tnorm_type\tcard_status\ttitle",
        "N-BASE-001\tBASE\tINVARIANT\tACTIVE\tBase",
        "T-N-001\tPERSONAL\tMANDATORY_RULE\tACTIVE\tPersonal",
        "N-FUTURE-001\tDOMAIN\tFUTURE_STATEMENT_TYPE\tCANDIDATE\tFuture",
    ]
    if duplicate_norm:
        norm_rows.append("N-BASE-001\tBASE\tINVARIANT\tACTIVE\tDuplicate")
    files["assurance/NORM_CATALOG.tsv"] = (
        "\n".join(norm_rows) + "\n"
    ).encode("utf-8")

    dependency_paths = [
        "machine/CORE_CANON.json",
        "FINAL_VERIFICATION.json",
        "assurance/NORM_CATALOG.tsv",
        "assurance/DEPENDENCY_DAG.tsv",
        "MANIFEST.json",
        "SHA256SUMS.txt",
    ]
    files["assurance/DEPENDENCY_DAG.tsv"] = dependency_bytes(dependency_paths)

    components = [
        {
            "path": path,
            "role": path.upper().replace("/", "_").replace(".", "_"),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
        for path, payload in files.items()
    ]
    manifest = {
        "package_id": "BOIS_TEST_CORE_V1",
        "artifact_version": "1.0",
        "status": "INTERNAL_CANDIDATE",
        "release_flavor": "PASSIVE_DATA_ONLY",
        "root_directory": root.name,
        "components": components,
        "loading_order": dependency_paths,
        "manifest_entry_count": len(components),
        "catalog_counts": {
            "total": len(norm_rows) - 1,
            "base": 2 if duplicate_norm else 1,
            "active": 3 if duplicate_norm else 2,
            "candidate": 1,
            "personal_ids": 1,
        },
    }
    files["MANIFEST.json"] = json_bytes(manifest)
    files["SHA256SUMS.txt"] = checksum_bytes(files)

    for relative, payload in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return root


def build_release_package(tmp_path: Path) -> Path:
    root = tmp_path / "bois-release-core"
    release_package_id = "BOIS_TEST_RELEASE_V3"
    release_version = "3.0"
    normative_package_id = "BOIS_TEST_NORMATIVE_V2"
    normative_version = "2.0"
    status = "INTERNAL_STATIC_PASS"

    component_files = {
        "machine/CORE_CANON.json": json_bytes({
            "package_id": normative_package_id,
            "artifact_version": normative_version,
            "release_flavor": "PASSIVE_DATA_ONLY",
            "executable": False,
        }),
        "schema/RELEASE_ENVELOPE_SCHEMA.json": json_bytes({
            "type": "object",
            "additionalProperties": False,
            "required": [
                "release_package_id",
                "release_version",
                "normative_package_id",
                "normative_content_version",
                "status",
            ],
            "properties": {
                "release_package_id": {"const": release_package_id},
                "release_version": {"const": release_version},
                "normative_package_id": {"const": normative_package_id},
                "normative_content_version": {"const": normative_version},
                "status": {"type": "string"},
            },
        }),
        "assurance/NORM_CATALOG.tsv": (
            "norm_id\tlayer\tnorm_type\tcard_status\t"
            "available_for_application\ttitle\n"
            "N-BASE-001\tBASE\tINVARIANT\tACTIVE\tTRUE\tBase\n"
        ).encode("utf-8"),
    }
    envelope_files = {
        "assurance/SELF_CONSISTENCY_REPORT.json": json_bytes({
            "release_package_id": release_package_id,
            "release_version": release_version,
            "result": "PASS",
        }),
        "assurance/VALIDATION_RECEIPT.json": json_bytes({
            "checks": {
                "TEST-RELEASE-INTEGRITY": {
                    "result": "PASS",
                    "trace_sha256": "a" * 64,
                },
            },
        }),
    }
    dependency_path = "assurance/BUILD_DEPENDENCY_DAG.tsv"
    loading_order = [
        "machine/CORE_CANON.json",
        "schema/RELEASE_ENVELOPE_SCHEMA.json",
        "assurance/NORM_CATALOG.tsv",
        dependency_path,
        "assurance/SELF_CONSISTENCY_REPORT.json",
        "assurance/VALIDATION_RECEIPT.json",
    ]
    component_files[dependency_path] = release_dependency_bytes(loading_order)

    components = [
        {
            "path": path,
            "required": True,
            "role": "TEST_COMPONENT",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
        for path, payload in component_files.items()
    ]
    validation_envelope = [
        "assurance/VALIDATION_RECEIPT.json",
        "assurance/SELF_CONSISTENCY_REPORT.json",
        "CHECKSUMS.json",
        "FINAL_VERIFICATION.json",
    ]
    manifest = {
        "release_package_id": release_package_id,
        "release_version": release_version,
        "normative_package_id": normative_package_id,
        "normative_content_version": normative_version,
        "status": status,
        "transport": "SINGLE_PASSIVE_DATA_ZIP",
        "executable_code": False,
        "component_count": len(components),
        "components": components,
        "loading_order": loading_order,
        "validation_envelope": validation_envelope,
        "normative_counts": {
            "total": 1,
            "base": 1,
            "active_for_application": 1,
        },
    }

    files = {**component_files, **envelope_files}
    files["MANIFEST.json"] = json_bytes(manifest)
    checksum_entries = {
        path: {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
        for path, payload in files.items()
    }
    checksums = {
        "algorithm": "SHA-256",
        "count": len(checksum_entries),
        "entries": checksum_entries,
        "release_package_id": release_package_id,
        "release_version": release_version,
        "scope": (
            "Every package file except CHECKSUMS.json and "
            "FINAL_VERIFICATION.json."
        ),
    }
    files["CHECKSUMS.json"] = json_bytes(checksums)
    files["FINAL_VERIFICATION.json"] = json_bytes({
        "release_package_id": release_package_id,
        "release_version": release_version,
        "normative_package_id": normative_package_id,
        "normative_content_version": normative_version,
        "status": status,
        "archive_sha256": "EXTERNAL_AFTER_PACKAGING",
        "checksums_sha256": hashlib.sha256(
            files["CHECKSUMS.json"]
        ).hexdigest(),
        "manifest_sha256": hashlib.sha256(files["MANIFEST.json"]).hexdigest(),
        "self_consistency_report_sha256": hashlib.sha256(
            files["assurance/SELF_CONSISTENCY_REPORT.json"]
        ).hexdigest(),
        "validation_receipt_sha256": hashlib.sha256(
            files["assurance/VALIDATION_RECEIPT.json"]
        ).hexdigest(),
    })

    for relative, payload in files.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return root


def dependency_bytes(paths):
    rows = [
        "node_id\tpath\trole\tdepends_on\trequired\tfailure_result\tload_order"
    ]
    for index, path in enumerate(paths, start=1):
        dependencies = [] if index == 1 else [paths[index - 2]]
        rows.append(
            f"DEP-{index:03d}\t{path}\tTEST\t"
            f"{json.dumps(dependencies, separators=(',', ':'))}\t"
            f"TRUE\tSTOP-PACKAGE-INCOMPLETE\t{index}"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def release_dependency_bytes(paths):
    rows = ["node_id\tpath\tdepends_on\tdependency_kind\treason"]
    for index, path in enumerate(paths, start=1):
        dependency = "" if index == 1 else paths[index - 2]
        rows.append(
            f"DAG-{index:03d}\t{path}\t{dependency}\t"
            "LOAD_BEFORE\tDeterministic test load order"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def checksum_bytes(files):
    lines = [
        f"{hashlib.sha256(payload).hexdigest()}  {path}"
        for path, payload in files.items()
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write_zip(package_root: Path, archive_path: Path):
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_root.rglob("*")):
            if path.is_file():
                archive.write(path, f"{package_root.name}/{path.relative_to(package_root)}")
