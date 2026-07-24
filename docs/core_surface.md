# Core Surface Foundation

`core_surface` is the passive, versioned trust boundary between a BOIS Core
package and future semantic execution.

It currently proves that a package can be read without executing embedded code,
that its complete inventory and declared dependency order are intact, and that
Base Core norms remain separate from personal, domain, and candidate layers.
It does not select applicable norms or calculate philosophical meaning.

## Public API

```python
from core_surface import load_core_surface

surface = load_core_surface("/path/to/core-package.zip", purpose="evaluation")

print(surface.package_id)
print(surface.artifact_version)
print(surface.release_package_id)
print(surface.release_version)
print(surface.normative_package_id)
print(surface.normative_content_version)
print(surface.source_kind)
print(surface.archive_sha256)
print(surface.content_set_sha256)
print(len(surface.base_norms))
print(surface.norms_for_layer("PERSONAL"))
```

The returned `CoreSurface` is immutable. Canonical `norm_type` values are
preserved exactly as supplied by the package and are not reduced to a Runtime
enum.

Identity fields are intentionally separate:

- `manifest_dialect` identifies the recognized manifest contract;
- `release_package_id` and `release_version` identify the immutable transport
  release;
- `normative_package_id` and `normative_content_version` identify the
  normative content carried by that release;
- compatibility aliases `package_id` and `artifact_version` refer to the
  normative identity and never replace the release identity;
- `source_kind` is `archive` or `directory`;
- `archive_sha256` is present only when the original ZIP was loaded;
- `content_set_sha256` is the deterministic hash of relative paths and payload
  bytes for both source kinds;
- `manifest_sha256` binds the exact manifest.

A directory hash is never presented as an archive hash. Canonical Runtime
attestation therefore requires the original ZIP.

## Manifest dialects

The loader recognizes two explicit dialects and rejects partial, mixed, or
unknown identities:

- legacy manifests with `package_id`, `artifact_version`, `release_flavor`,
  and `root_directory`;
- release-envelope manifests with `release_package_id`, `release_version`,
  `normative_package_id`, `normative_content_version`, `transport`, and
  `validation_envelope`.

Release-envelope manifests do not synthesize `root_directory` or collapse the
two version axes. The observed archive/directory root remains a transport
property. `INTERNAL_STATIC_PASS` proves the package's declared static boundary;
it is not `ACTIVE`, Runtime compatibility, OperatorAcceptance, or permission to
execute.

## Command-line validation

```bash
python -m core_surface /path/to/core-package.zip
```

Successful validation prints a JSON summary. A rejected package exits with
status 2 and reports the failed boundary.

Candidate packages load only with `purpose="evaluation"`. Requesting
`purpose="active"` requires package status `ACTIVE`; the loader does not change
package status and does not activate a package.

## Checks performed

- safe single-root ZIP or directory layout;
- no traversal paths, symlinks, encrypted entries, duplicate entries, or
  oversized payloads;
- exact manifest inventory;
- component sizes and SHA-256 values;
- complete legacy `SHA256SUMS.txt` or release `CHECKSUMS.json` reproduction;
- legacy `DEPENDENCY_DAG.tsv` or release `BUILD_DEPENDENCY_DAG.tsv` coverage
  and topological load order;
- release validation-envelope hashes and
  `RELEASE_ENVELOPE_SCHEMA.json` identity constants;
- package identity and version agreement across manifest, machine canon, and
  final verification;
- unique norm IDs;
- declared legacy catalog or release normative counts;
- explicit grouping by native package layer.

## Deliberately deferred

The human-readable canon distinguishes nine statement types while the current
machine catalog exposes three `norm_type` values plus separate modality and
operation fields. Core Surface does not invent their mapping. Until the
canonical projection is clarified or practical semantic execution requires a
decision, all supplied classification fields remain opaque source data.

Phase 4F now consumes exact Core Surface references in an isolated Minimal
Semantic Executor only after `runtime_compatibility` validates the package's own
runtime contract and creates an accepted RuntimeAttestation. The surface still
does not integrate into `RuntimeSession`; Independent Review and Policy Kernel
admission remain absent.
