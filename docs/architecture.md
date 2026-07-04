# Architecture

The repository is a root-level SDK. There is no nested wrapper directory such as
`bois-middleware/` or another `boris-runtime/` inside the repository.

## Root Structure

```text
core/       declarative definitions and loaders
runtime/    active protocol execution pipeline
protocol/   BOIS, SIMA, and BORIS protocol layers
prompt/     deterministic prompt construction
llm/        Phase 1 LLM adapter interface
adapters/   LLM, memory, tool, and platform boundaries
cli/        local validation entrypoint
api/        optional FastAPI boundary
examples/   minimal SDK usage examples
docs/       current documentation set
archive/    legacy/reference artifacts only
```

Active code lives in:

- `core/`
- `runtime/`
- `protocol/`
- `prompt/`
- `llm/`
- `adapters/`
- `cli/`
- `api/`
- `examples/`

Legacy code lives only in:

- `archive/v0-runtime/`

No active runtime code should import from `archive/v0-runtime`.

## Runtime Flow

```text
User/Platform -> Middleware Runtime -> LLM Adapter -> LLM
```

The platform provides UI, transport, authentication, tools, memory, and storage.
The middleware runtime applies the BOIS / SIMA / BORIS protocol and delegates
LLM inference to an adapter.

## Separation Of Concerns

- BOIS is declarative and lives under `core/definitions/`.
- SIMA is declarative analytical guidance and lives under `core/definitions/`.
- BORIS is declarative operator/domain specialization and lives under
  `core/definitions/`.
- Runtime code executes protocol boundaries only.
- Adapter code defines external integration boundaries.
- Platform-specific systems are external to the core SDK.

The historical reset rationale is retained in
[architecture_reset.md](architecture_reset.md) as Phase 0 context. It is not the
main architecture document.
