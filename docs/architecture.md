# BORIS Runtime Architecture

## Current boundary

The repository has one canonical Core representation: `CoreSurface`.

```text
release package
  -> CoreSurfaceLoader
  -> immutable CoreSurface
     -> Runtime compatibility verification

immutable CoreSurface
  -> application Context Projector
  -> bounded context projection

immutable CoreSurface + trusted server Core selection
  -> Runtime Compatibility
  -> application ExecutionService
  -> signed CHATGPT_HOST_ONLY compiler + calculator work orders (public MCP)
     or OPENAI_API compiler + calculator (private HTTP only)
  -> SemanticExecutor validation and gate constraints
  -> ExecutionCandidate
```

The loader validates package layout, inventory, hashes, identity, dependency
order, lifecycle status, and norm catalog before any consumer sees canonical
records. No active component reads the former local definition folders or an
unverified machine JSON directly.

## Active modules

| Module | Responsibility | Explicit exclusions |
|---|---|---|
| `core_surface` | Verify and expose the passive, query-independent canonical package | Query selection, semantic calculation, state mutation, activation |
| `runtime_compatibility` | Declare substrate capabilities, execute package-required checks, create attestation | Meaning creation, activation, external action |
| `semantic_executor` | Produce a non-executing `ExecutionCandidate` | Independent review, state admission, tools, memory |
| `application` | Compile raw requests, orchestrate semantic candidates, build diagnostic frames, and validate supplied answers | Independent review, policy admission, state mutation, tool execution |
| `llm` | Canonical structured/unstructured inference port | Policy decisions |
| `api` | Private HTTP transport | Core or semantic logic |
| `mcp_server` | Public read-only `boris.execute` transport | Direct Core access, LLM calls, memory |
| `cli` | Local context-frame transport | Alternative engine |

## Semantic path

```text
server boris-core checkout
  -> CoreSurface
  -> repository content binding and scoped acceptance
  -> RuntimeCompatibilityVerifier
  -> RuntimeAttestation
  -> SemanticInputCompiler
  -> SemanticViewBuilder
  -> semantic calculator
  -> deterministic validation and gate constraints
  -> ExecutionCandidate
```

Semantic execution requires an accepted attestation for
`semantic_evaluation`. The result is candidate material only. It cannot mutate
Runtime or Core state.

The receiving profile supports both the legacy three-valued Predicate DSL and
the current Core v2.23 four-valued contract. `UNKNOWN` constrains material
uncertainty to `HOLD`; formal `ERROR` constrains the candidate to `REPAIR`.

Compatibility and repository content binding are checked before the compiler
or calculator can call an LLM. The configured server directory is accepted only
for `semantic_evaluation`; archive compatibility mode still requires an
explicit acceptance record. The compiler preserves raw input and request
context as an untrusted phenomenon; it may classify only phases, triggers,
layers, scopes, and explicitly named norm references exposed by the verified
Core Surface. Supplied facts, evidence, and authority must be copied exactly.
Deterministic validation rejects all other output.

## Public ChatGPT execution path

```text
ChatGPT
  -> public MCP boris.execute
  -> private POST /runtime/execute
  -> ExecutionService
  -> ExecutionCandidate envelope
  -> signed HOLD handoff when operator input is required
```

The MCP tool list is exactly `{"boris.execute"}`. There is no public
`boris.frame` alias. Every request follows the same semantic route.
`BORIS_RUNTIME_MODE=dev` changes server-side observability only; it is not a
tool or API argument. The public
envelope uses `boris-execution/1.0`, marks the result as
`status=semantic_candidate`, and exposes the final constrained gate, norm
results, unknowns, conflicts, alternatives, and explicit limitations.

`HOLD`, `STOP`, and `REPAIR` remain normal Runtime results. The MCP presentation
layer must not weaken them or substitute a separate ChatGPT answer.

## ChatGPT host executor

The private HTTP API retains the autonomous provider when a trusted client
explicitly selects the legacy route:

```text
private POST /runtime/execute operation=execute
  -> SemanticInputCompiler
  -> OPENAI_API semantic calculator
  -> validated ExecutionCandidate
```

The public MCP route is unconditionally host-only. Its schema has no
`operation` field; the adapter infers prepare versus submit from the mutually
exclusive request shapes:

```text
boris.execute with input or signed resume
  -> Runtime compatibility
  -> signed COMPILATION SemanticWorkOrder

ChatGPT compiles one semantic_input

boris.execute with work-order ID, token, and semantic_input
  -> verify token and one-shot registry state
  -> re-verify Core and RuntimeAttestation
  -> validate SemanticInput
  -> deterministic Semantic View
  -> signed CALCULATION SemanticWorkOrder

ChatGPT calculates one semantic_result

boris.execute with new work-order ID, token, and semantic_result
  -> verify the second token and one-shot registry state
  -> re-verify Core and RuntimeAttestation
  -> rebuild and hash the Semantic View
  -> validate candidate_result as the phase capsule primary object
     -> invalid first submission: HOLD + one signed correction work order
     -> invalid correction: HOLD without another work order
  -> SemanticCalculationValidator
  -> deterministic gate constraints
  -> ExecutionCandidate
```

Work orders use `boris-semantic-work-order/0.4` and bind:

- session and work-order IDs;
- Core reference and RuntimeAttestation SHA-256;
- exact source material and compiler catalog for `COMPILATION`;
- exact `SemanticInput` and Semantic View for `CALCULATION`;
- stage prompt and response-schema SHA-256;
- phase, selected norms, active layers, triggers, and scopes through the
  hashed view;
- issue and expiry times.

The calculation order also carries
`boris-phase-output-contract/1.0`. Its semantic output is derived from the
phase capsule's canonical `primary_object` and matching full
`required_object_schemas` entry. The gate-context schema is listed separately
as Runtime-owned and cannot replace the semantic output. Thus C04 accepts a
canonical `Question`, not a final recommendation or the shorter future
`GateContextC04` projection.

Submission is size-limited and single-use. An invalid first calculation
returns exactly one new signed calculation work order with `gate=HOLD`, the
unchanged semantic bindings, the parent work-order ID, and structured
code/path/received/expected/instruction diagnostics. If that submission is
still invalid, Runtime preserves `HOLD` without generating a third work order.
The correction is not canonical `REPAIR`: Core requires `REPAIR` to create a
new revision and a new cycle returning to `C00`. This closes host submission
compliance without pretending to implement C00-C11 state transitions,
Independent Reviewer, or Policy Kernel.

An accepted object receives the same strict validation and gate constraints as
an API-provider result.
ChatGPT cannot alter a formal result, omit a selected norm, fabricate a Core
reference, claim execution, or redirect Runtime-owned uncertainty without
rejection.

This boundary provides contract isolation only. The ChatGPT model still sees
the current conversation, system and project instructions, and any other
host-visible tool context. The PoC registry is bounded and in-memory, so work
orders do not survive restart and require one Runtime API worker or sticky
routing. Registry entries are transport transaction state, not domain memory,
cycle objects, admitted state events, or Policy Kernel decisions.

Runtime includes the Core-declared `minimum_context_window_tokens` in the work
order, but ChatGPT does not expose a provider identity or capacity attestation
to the MCP server. `host_model_identity_not_attested` and
`host_context_capacity_not_attested` therefore remain explicit limitations in
both the work order and resulting candidate. The existing RuntimeAttestation
continues to bind the receiving Runtime substrate and Core compatibility; it
is not reinterpreted as proof about the ChatGPT host.

The host route never constructs the Runtime API adapter. The configured LLM is
used only by the autonomous `OPENAI_API` route. A signed HOLD resume already
contains a validated `SemanticInput`, so it skips `COMPILATION` and starts with
the `CALCULATION` work order.

## Stateless HOLD continuation

Until a signed operator-machine authority registry and memory physiology exist,
every recoverable system `HOLD` is owned by the human operator. The explicit
handoff introduces no Runtime memory. The `boris-execution/1.0` envelope
requires:

- a non-empty conditional `candidate_result`, or `candidate_result: null` with
  `candidate_unavailable_reason`;
- `hold.hold_record` with `hold_id`, the Core-required `cycle_id`, return state
  and gate, reason, scope, source/evidence references, unknowns, open debts,
  and state hash;
- a separate `hold.blocking_precondition` whose resolution permits a same-phase
  gate recheck but does not itself imply `PASS`, plus
  `owner: OPERATOR`;
- `hold.required_operator_input` with separate path-aware semantic unknowns,
  formal Core selector inputs, and exact system targets;
- an HMAC-SHA256 `continuation_token` bound to the exact `SemanticInput`, Core
  identity, session, HOLD targets, prior current-cycle decisions, expiry, and
  resume count.

Resume uses the same `/runtime/execute` and `boris.execute` entry. Runtime
verifies the signature, expiry, session, current Core identity, and signed
`HoldRecord.state_hash` before any semantic LLM call. The response becomes a
`boris-operator-decision/1.0` current-cycle control object, never a fact,
evidence item, authority grant, or memory write.

- `PROVIDE_INFORMATION` supplies every signed current-cycle selector and may
  mark declared semantic unknown IDs resolved.
- `CONFIRM_ASSUMPTION` supplies explicit temporary selector assumptions while
  preserving unknowns.
- `ALLOW_CONDITIONAL_PROCEEDING` preserves unknowns and removes only signed
  non-authority, non-mandatory-proof targets from the blocking set.
- `CHANGE_SCOPE` replaces only verified selector arrays and returns to the same
  phase.
- `TERMINATE_CYCLE` resolves the precondition by ending the cycle without
  another semantic calculation.

No mode forces `PASS`, weakens `STOP`, creates authority, or supplies mandatory
proof. A new `HOLD` issues a new token while preserving the cycle identity and
prior effective decisions.

After resume, a non-`HOLD` calculation cannot escape with an empty public
candidate. The LLM contract requires candidate material, while Semantic
Executor provides a deterministic `boris-candidate-projection/1.0` fallback
from the validated calculation if the provider returns `{}` anyway. The
fallback preserves the constrained gate, is identified by
`CANDIDATE_RESULT_PROJECTED` in the trace, and does not implement review,
policy admission, state mutation, memory, or external action.

This mechanism is stateless: Runtime stores no unfinished cycle. Consequently,
an unexpired token can be replayed and cannot be individually revoked. Short
TTL, server-secret rotation, request rate limits, and later persistent cycle
state are the applicable controls. The token does not admit a state event,
write long-term memory, or authorize an external action.

## MCP Developer Surface

In `BORIS_RUNTIME_MODE=dev`, the sole `boris.execute` descriptor links to the
versioned MCP Apps resource `ui://boris/developer-surface-v2-1.html`. The
component receives:

- the candidate and handoff through model-visible `structuredContent`;
- concise gate-preserving instructions through `content`;
- the full sanitized `boris-execution-trace/1.0` only through tool-result
  `_meta`.

The component renders the constrained gate, phase, candidate, structured
operator form, semantic summary, and expandable complete trace. Its Resume
action uses MCP Apps `tools/call` to validate the exact operator decision
through the same `boris.execute`. A non-terminal resume returns a signed
`CALCULATION` work order; the component supplies it through
`ui/update-model-context` and wakes the host through `ui/message` or the
ChatGPT compatibility alias `sendFollowUpMessage`. This preserves the
host-only semantic provider while preventing a fresh compilation cycle. There
is no second debug or continuation tool. The component displays Runtime error
details, has no external assets or network allowlist, and is not published in
production mode.

## Internal context path

```text
Core package
  -> CoreSurface
  -> application Context Projector
  -> bounded lexical projection
  -> ContextProvider
  -> /runtime/frame
  -> internal diagnostics
```

The lexical projection is not semantic routing. It exposes:

- exact release and normative identity;
- content-set and manifest hashes;
- a bounded set of immutable norm records selected by lexical overlap;
- Base norms as a deterministic fallback when no overlap exists.

The `boris-context/2.0` wire contract exposes the projection as
`projected_core` with `projection_metadata`. Version 1 field names
`retrieved_core` and `retrieval_metadata` are intentionally unsupported. The
producer consumes verified Core Surface records but belongs to `application`,
so `core_surface` remains passive and query-independent.

`/runtime/frame`:

- does not call an LLM;
- does not create or mutate a server-side session;
- treats `session_id` as correlation data only;
- does not create RuntimeAttestation;
- does not claim package activation or semantic applicability;
- bounds output to six chunks, 3000 characters per chunk, and 12000 total
  projected characters.

The frame request has no observability selector. `BORIS_RUNTIME_MODE=dev` adds
`developer_trace` (`boris-projection-trace/1.0`) with:

- verified package identity and non-secret package/component metadata;
- query tokens and all canonical norm candidates;
- selected and excluded norms with scores, matched terms, and reasons;
- projection limits, fallback state, truncation, and stage timings;
- an explicit capability ledger showing that Semantic Executor, Independent
  Reviewer, Policy Kernel, Cycle Guard, and LLM inference were not invoked.

The projection trace is structured observability, not model chain-of-thought. It passes
through the same public-value sanitizer as the context packet and excludes
secrets, hidden prompts, environment data, stack traces, and absolute source
paths. Selected objects include their bounded projected chunks; excluded
objects expose metadata rather than duplicating the full Core content.

Developer execution mode embeds this lexical projection and trace in a separate
`boris-execution-trace/1.0` envelope together with the compiled
`SemanticInput`, Core reference, RuntimeAttestation, semantic selection and
predicate results, suggested and constrained gates, validation issues, stage
ledger, continuation status, and timings. Runtime returns it to the MCP adapter,
which moves it to component-only tool-result `_meta`. It excludes
compiler/calculator prompts, continuation tokens, chain-of-thought, server
secrets, environment data, and absolute source paths.

If the configured Core package is absent or invalid, the API returns
`core_surface_unavailable` with HTTP 503. It does not fall back to local
definitions.

## Answer validation path

`POST /runtime/validate` is a stateless Phase 4D service. It validates a
caller-supplied answer and complete context packet through:

1. packet preflight and leakage checks;
2. deterministic answer checks;
3. optional semantic validation;
4. deterministic/semantic merge in hybrid mode.

This service is not the future Independent Reviewer. It does not establish
packet authenticity, retain packets, rewrite answers, admit state changes, or
apply an `ExecutionCandidate`.

## Removed architecture

The following top-level packages were deleted:

- `core/` — Phase 2 local definition loader;
- `core_retriever/` — direct machine-JSON embedding path;
- `runtime/`, `protocol/`, `prompt/` — Phase 3 prompt middleware, sessions, and
  clarification loop;
- `adapters/` — unused stubs and LLM compatibility facade;
- `archive/` — embedded v0 source copy.

The private `/runtime/ask`, `/runtime/reset`, `/runtime/session/{id}`, legacy
`/run`, `MiddlewareEngine`, `BOISRuntime`, and `ProtocolEngine` contracts were
removed with those paths.

## Kernel boundary

The former proposed monolithic `bois_kernel` is not an active package. Its
semantic-calculation portion now belongs to `semantic_executor`; its passive
registry belongs to `core_surface`.

The following responsibilities remain intentionally unimplemented and must not
be absorbed by the Semantic Executor:

- `IndependentReviewer`;
- deterministic `PolicyKernel`;
- authority and operator-decision enforcement beyond compatibility acceptance;
- state-event admission;
- Cycle Guard;
- domain physiology;
- long-term memory;
- tool and external action execution.

The future cycle is:

```text
ExecutionCandidate
  -> IndependentReviewer
  -> PolicyKernel
  -> StateEvent
```

Only `ExecutionCandidate` is implemented. It packages its result for later
review; it is not an `IndependentReview` or `KernelDecision`.

## Dependency rules

- `core_surface` imports no application, API, MCP, LLM, compatibility, or
  executor code.
- `runtime_compatibility` may read immutable Core Surface data.
- `semantic_executor` may consume Core Surface and compatibility records.
- `application` may consume Core Surface, Runtime compatibility, the LLM port,
  and the public Semantic Executor contracts.
- `api` may import `application`, never the inverse.
- `mcp_server` communicates with `api` only through HTTP.
- no active module may import a removed top-level package.
