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
print(surface.source_sha256)
print(len(surface.base_norms))
print(surface.norms_for_layer("PERSONAL"))
```

The returned `CoreSurface` is immutable. Canonical `norm_type` values are
preserved exactly as supplied by the package and are not reduced to a Runtime
enum.

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
- complete `SHA256SUMS.txt` reproduction;
- dependency coverage and topological load order;
- package identity and version agreement across manifest, machine canon, and
  final verification;
- unique norm IDs;
- declared catalog counts;
- explicit grouping by native package layer.

## Deliberately deferred

The human-readable canon distinguishes nine statement types while the current
machine catalog exposes three `norm_type` values plus separate modality and
operation fields. Core Surface does not invent their mapping. Until the
canonical projection is clarified or practical semantic execution requires a
decision, all supplied classification fields remain opaque source data.

This foundation does not yet integrate the surface into `RuntimeSession`. Such
an attachment would be decorative until the Semantic Executor consumes exact
Core Surface references and Independent Review checks the same version and
hash.
