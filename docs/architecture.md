# Architecture

The repository is a root-level SDK. There is no nested wrapper directory such as
`bois-middleware/` or another `boris-runtime/` inside the repository.

## Root Structure

```text
core/                  declarative definitions and loaders
core_surface/          immutable package loading and trust boundary
runtime_compatibility/ substrate declaration and Runtime attestation
semantic_executor/     isolated semantic calculation experiment
runtime/               active protocol execution pipeline
protocol/              BOIS, SIMA, and BORIS protocol layers
prompt/                deterministic prompt construction
llm/                   canonical plain and structured LLM port
adapters/              compatibility and external capability boundaries
cli/                   local validation entrypoint
api/                   canonical FastAPI boundary
examples/              minimal SDK usage examples
docs/                  current documentation set
archive/               legacy/reference artifacts only
```

Active code lives in:

- `core/`
- `core_surface/`
- `runtime_compatibility/`
- `semantic_executor/`
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

## Canonical Runtime Flow

```text
User/Platform -> api.app -> BOISRuntime -> ProtocolEngine -> LLM port -> LLM
```

The platform provides UI, transport, authentication, tools, memory, and storage.
The middleware runtime applies the BOIS / SIMA / BORIS protocol and delegates
LLM inference to an adapter.

The Runtime supports multiple operations through one composition root behind
the HTTP API, while the public MCP connector exposes adapter-level tools:

```text
private POST /runtime/ask
  -> BOISRuntime.run(...)
  -> ProtocolEngine.run_turn(...)
  -> configured LLM adapter
  -> Runtime-generated protocol answer

public MCP boris.frame
  -> private POST /runtime/frame
  -> BOISRuntime.frame(...)
  -> ProtocolEngine.build_frame_context(...)
  -> bounded BOIS/SIMA/BORIS context packet
  -> runtime_generated_prompt
  -> ChatGPT-generated final answer

private POST /runtime/validate
  -> RuntimeRegistry.validate(...)
  -> validation engine
  -> layered validation report
```

Phase 4F adds a separate experimental semantic path:

```text
versioned Core package
  -> immutable Core Surface
  -> RuntimeCompatibilityVerifier
  -> RuntimeAttestation
  -> Semantic View
  -> LLM semantic calculation
  -> deterministic validation
  -> non-executing ExecutionCandidate
```

The attestation must match the exact archive, manifest, content set, and loaded
component hashes and must be explicitly accepted for `semantic_evaluation`
before the calculator is called.

The verifier executes every package-declared required check through a
fail-closed registry. Unknown or non-passing checks produce `HOLD`; they cannot
be silently replaced by a smaller Runtime-owned checklist.

This path is not imported by `ProtocolEngine`, the HTTP API, or MCP. It does not
mutate `RuntimeSession`, admit state transitions, call tools, write memory, or
activate packages. Its result remains operator-review material until an
Independent Reviewer and Policy Kernel are implemented.

## Compatibility-only modules

The earlier Phase 1 SDK path is no longer a parallel engine:

- `runtime.engine.MiddlewareEngine` delegates to `BOISRuntime` and rejects
  injection of the removed earlier prompt/parser/loop components;
- `api.fastapi_server.app` is the same object as `api.app.app`;
- deprecated `POST /run` remains on the compatibility server and delegates to
  the canonical Runtime;
- `adapters.llm` exposes compatibility names backed by the canonical LLM port;
- the unused `runtime/prompt_builder.py`, `runtime/response_parser.py`, and
  earlier `ProtocolLoop` were removed.

`boris.validate` remains stateless answer validation for Phase 4D context
packets. It is not the future Independent Reviewer and is not reused as one.

`boris.frame` is context-provider mode. It reuses Runtime SIMA extraction, BOIS
frame construction, BORIS context construction, and BOIS Core retrieval, but it
does not call an external LLM, parse LLM output,
record a final answer, update `last_decision`, update `last_output_type`, add
asked clarification questions, increment clarification cycles, or write to the
processed-input cache.

The Runtime API remains private. MCP remains the public adapter boundary, and
the MCP server communicates with Runtime only through the HTTP API. The MCP
server must not import Runtime, ProtocolEngine, Core loader, or LLM adapter
internals.

MCP tools return native MCP `CallToolResult` objects. The public `boris.frame`
tool delivers the context packet through MCP `structuredContent` and the full
safe `runtime_generated_prompt` through `content`; error envelopes set
`isError: true`. The MCP adapter does not serialize its own
`structuredContent`/`content` envelope into a JSON text block.

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
