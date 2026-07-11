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

The Runtime now has two public composition-root modes behind the private HTTP
API:

```text
MCP boris.ask
  -> private POST /runtime/ask
  -> BOISRuntime.run(...)
  -> ProtocolEngine.run_turn(...)
  -> configured LLM adapter
  -> Runtime-generated protocol answer

MCP boris.frame
  -> private POST /runtime/frame
  -> BOISRuntime.frame(...)
  -> ProtocolEngine.build_frame_context(...)
  -> bounded BOIS/SIMA/BORIS context packet
  -> ChatGPT-generated final answer
```

`boris.frame` is context-provider mode. It reuses Runtime SIMA extraction, BOIS
frame construction, BORIS context construction, and BOIS Core retrieval, but it
does not build the final raw LLM prompt, call an external LLM, parse LLM output,
record a final answer, update `last_decision`, update `last_output_type`, add
asked clarification questions, increment clarification cycles, or write to the
processed-input cache.

The Runtime API remains private. MCP remains the public adapter boundary, and
the MCP server communicates with Runtime only through the HTTP API. The MCP
server must not import Runtime, ProtocolEngine, Core loader, or LLM adapter
internals.

The context packet is explicit and bounded:

```json
{
  "packet_version": "boris-context/1.0",
  "frame_id": "uuid",
  "session_id": "session-id",
  "input": "effective user input",
  "runtime_mode": "context_provider",
  "llm_called": false,
  "bois_frame": {},
  "sima": {
    "risk": 0.0,
    "uncertainty": 0.0,
    "missing_fields": [],
    "ambiguity_score": 0.0
  },
  "boris_context": {},
  "retrieved_core": [],
  "retrieval_metadata": {
    "returned_chunks": 0,
    "total_characters": 0,
    "truncated": false,
    "max_chunks": 6,
    "max_chunk_characters": 3000,
    "max_total_characters": 12000
  },
  "answer_instructions": []
}
```

The packet is also an explicit public projection. `bois_frame` exposes only
`framework`, `core`, `input`, and `constraints`. `boris_context` exposes only
`name`, `role`, `context`, `definition`, and `session`; inside `session`, only
`session_id`, `clarification_cycles`, and `max_clarification_cycles` are public.

Flexible canonical containers such as `bois_frame.core`,
`boris_context.context`, and `boris_context.definition` are recursively filtered
instead of serialized wholesale. Secret-like and internal keys are removed with
a normalized case-insensitive key policy, including prompt payloads,
authorization data, credentials, environment fields, tracebacks, vectors, debug
contexts, and internal filesystem path fields. Configured secret values from
secret-like environment variables are redacted as `[redacted]` when they appear
inside allowed internal frame/context fields or retrieved chunk text. The
top-level packet `input` remains intentional model-visible user content and is
not globally rewritten.

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
