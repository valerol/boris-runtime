from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def freeze_value(value):
    if isinstance(value, dict):
        return MappingProxyType({
            key: freeze_value(nested)
            for key, nested in value.items()
        })
    if isinstance(value, list):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ComponentRecord:
    path: str
    role: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    package_id: str
    artifact_version: str
    status: str
    release_flavor: str
    root_directory: str
    components: tuple[ComponentRecord, ...]
    loading_order: tuple[str, ...]
    raw: Mapping[str, Any] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "raw", freeze_value(dict(self.raw)))


@dataclass(frozen=True, slots=True)
class NormRecord:
    norm_id: str
    layer: str
    norm_type: str
    fields: Mapping[str, str] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


@dataclass(frozen=True, slots=True)
class CoreSurface:
    source: str
    source_kind: str
    package_id: str
    artifact_version: str
    status: str
    release_flavor: str
    purpose: str
    root_directory: str
    archive_sha256: str | None
    content_set_sha256: str
    manifest_sha256: str
    components: tuple[ComponentRecord, ...]
    loading_order: tuple[str, ...]
    machine_canon: Mapping[str, Any] = field(repr=False)
    norms_by_layer: Mapping[str, tuple[NormRecord, ...]] = field(repr=False)
    _norm_index: Mapping[str, NormRecord] = field(repr=False)
    _payloads: Mapping[str, bytes] = field(repr=False)

    def __post_init__(self):
        object.__setattr__(self, "machine_canon", freeze_value(dict(self.machine_canon)))
        object.__setattr__(
            self,
            "norms_by_layer",
            MappingProxyType({
                layer: tuple(records)
                for layer, records in self.norms_by_layer.items()
            }),
        )
        object.__setattr__(self, "_norm_index", MappingProxyType(dict(self._norm_index)))
        object.__setattr__(self, "_payloads", MappingProxyType(dict(self._payloads)))

    @property
    def base_norms(self) -> tuple[NormRecord, ...]:
        return self.norms_for_layer("BASE")

    def norms_for_layer(self, layer: str) -> tuple[NormRecord, ...]:
        return self.norms_by_layer.get(layer, ())

    def has_norm(self, norm_id: str) -> bool:
        return norm_id in self._norm_index

    def get_norm(self, norm_id: str) -> NormRecord:
        return self._norm_index[norm_id]

    @property
    def norm_ids(self) -> tuple[str, ...]:
        return tuple(self._norm_index)

    def read_bytes(self, path: str) -> bytes:
        return self._payloads[path]

    def read_json(self, path: str) -> Any:
        return json.loads(self.read_bytes(path).decode("utf-8"))

    @property
    def payload_paths(self) -> tuple[str, ...]:
        return tuple(self._payloads)

    @property
    def loaded_component_hashes(self) -> Mapping[str, str]:
        return MappingProxyType({
            component.path: component.sha256
            for component in self.components
        })

    def summary(self) -> dict[str, Any]:
        norm_type_counts: dict[str, int] = {}
        for record in self._norm_index.values():
            norm_type_counts[record.norm_type] = norm_type_counts.get(record.norm_type, 0) + 1

        return {
            "package_id": self.package_id,
            "artifact_version": self.artifact_version,
            "status": self.status,
            "purpose": self.purpose,
            "release_flavor": self.release_flavor,
            "source_kind": self.source_kind,
            "archive_sha256": self.archive_sha256,
            "content_set_sha256": self.content_set_sha256,
            "manifest_sha256": self.manifest_sha256,
            "component_count": len(self.components),
            "loading_order_count": len(self.loading_order),
            "embedded_executable": bool(self.machine_canon.get("executable", False)),
            "norm_layers": {
                layer: len(records)
                for layer, records in sorted(self.norms_by_layer.items())
            },
            "norm_types": dict(sorted(norm_type_counts.items())),
            "norm_type_policy": "opaque_source_values",
        }
