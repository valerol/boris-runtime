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

MCP boris.validate
  -> private POST /runtime/validate
  -> RuntimeRegistry.validate(...)
  -> validation engine
  -> layered validation report
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

MCP tools return native MCP `CallToolResult` objects. Runtime payloads,
context packets, validation reports, and structured error envelopes are
delivered through MCP `structuredContent`; concise model-facing text is
delivered through `content`; and error envelopes set `isError: true`. The MCP
adapter does not serialize its own `structuredContent`/`content` envelope into a
JSON text block.

`boris.validate` is Phase 4D.1 stateless validation. Its input is the
ChatGPT-generated answer, the complete `boris.frame` context packet, and an
optional validation mode. The default mode is `deterministic`; `semantic` and
`hybrid` are also supported. Validation does not rewrite the answer, does not
create or mutate Runtime sessions, does not persist packets, does not look up
`frame_id`, does not enforce packet TTL, and does not verify packet ownership or
HMAC signatures. The supplied `frame_id` is used only for report correlation,
and Runtime does not claim that a supplied packet is authentic or unchanged.

The validation report uses `validation_version: "boris-validation/1.0"` and the
public verdicts `PASS`, `REVISE`, `FAIL`, and `INDETERMINATE`. A mandatory
preflight layer validates packet structure, public field allowlists, retrieval
metadata invariants, bounded retrieved core content, answer instructions, and
the centralized Phase 4D leakage policy before any answer validation layer runs.
Readable but invalid packets return a normal validation report with verdict
`FAIL`; request schema errors remain HTTP 422.

Preflight also validates public field types and structural consistency. Boolean
values do not pass integer or numeric checks: counters must be strict integers,
and SIMA scores must be strict numbers. SIMA `risk`, `uncertainty`, and
`ambiguity_score` are constrained to `0.0 <= value <= 1.0`. `bois_frame`
allowed fields are type-checked, `bois_frame.framework` must be `BOIS`, and
`bois_frame.input` must match packet `input` when present. `boris_context`
allowed fields and session fields are type-checked, `boris_context.name` must
be `BORIS` when present, nested session IDs must match packet `session_id`, and
clarification cycles must be non-negative and cannot exceed the configured
maximum. Retrieved chunks require non-empty string IDs, string section/title/text
fields, and strict numeric relevance. Relevance is not capped at 1.0 because the
current retriever may add lexical boosts to normalized similarity scores.
Retrieval metadata requires strict integer counts and limits, an actual boolean
`truncated`, and cross-field consistency between declared counts/character
totals and returned chunks.

These checks establish structural consistency, logical consistency, and public
contract compatibility only. They do not establish packet authenticity, packet
immutability, server origin, or tamper resistance.

Deterministic validation performs explainable non-LLM checks only and reports
whether each check requires semantic validation. It uses SIMA pass thresholds of
0.30 for risk, uncertainty, and ambiguity. Semantic validation is a dedicated
lazy validator adapter with strict JSON output parsing; it treats both the
packet and answer as untrusted validation data and never returns a rewritten
answer. `BORIS_VALIDATOR_LLM` and `BORIS_VALIDATOR_MODEL` may override the main
LLM settings; otherwise the validator falls back to `BOIS_LLM` and
`OPENAI_MODEL`. In pure semantic mode, unavailable validator configuration
returns HTTP 503 and invalid validator output returns HTTP 502. In hybrid mode,
deterministic structural and security findings remain authoritative, semantic
escalation is selective, and unavailable or invalid semantic validation yields
HTTP 200 with verdict `INDETERMINATE` while preserving deterministic findings.

Validation input-size gates run after packet preflight and before mode dispatch,
including pure semantic and hybrid modes. `MAX_ANSWER_CHARACTERS` bounds the
answer. `MAX_PACKET_TEXT_CHARACTERS` counts all string values in the supplied
context packet, including top-level `input`, because those values are included
in the semantic validation payload. Oversized answers return a normal report
with verdict `REVISE`; oversized packets return verdict `FAIL` and require a
new bounded frame. In both cases `llm_called` remains false and the semantic
adapter is not constructed.

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
