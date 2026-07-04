# Archive

The `archive/` directory contains legacy and reference material that is no
longer part of the active SDK execution path.

## archive/v0-runtime

`archive/v0-runtime/` contains the previous runtime v0 system, including:

- old kernel composition code
- previous schema-driven runtime experiments
- previous adapters
- old tests
- old FastAPI and CLI entrypoints
- previous roadmap and epistemic hierarchy artifacts

It is retained for audit, migration reference, and historical context only.

## Rules

- Do not import active runtime code from `archive/v0-runtime`.
- Do not treat archived adapters as current platform integrations.
- Do not add new execution logic to the archive.
- Use `core/`, `runtime/`, `adapters/`, `cli/`, `api/`, and `examples/` for
  active SDK work.

The Phase 0 reset rationale is retained in
[architecture_reset.md](architecture_reset.md) as historical context.

