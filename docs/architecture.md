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
  -> SemanticInputCompiler
  -> SemanticExecutor through OPENAI_API
     or signed CHATGPT_HOST prepare/submit
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

## Experimental ChatGPT host executor

The standard request keeps the existing calculator provider:

```text
boris.execute
  -> POST /runtime/execute
  -> SemanticInputCompiler
  -> OPENAI_API semantic calculator
  -> validated ExecutionCandidate
```

The optional host route uses two calls to the same tool:

```text
boris.execute operation=prepare
  -> Runtime compatibility
  -> API-backed SemanticInputCompiler
  -> deterministic Semantic View
  -> signed SemanticWorkOrder

ChatGPT calculates one semantic_result

boris.execute operation=submit
  -> verify token and one-shot registry state
  -> re-verify Core and RuntimeAttestation
  -> rebuild and hash the Semantic View
  -> SemanticCalculationValidator
  -> deterministic gate constraints
  -> ExecutionCandidate
```

The work order uses `boris-semantic-work-order/0.1` and binds:

- session and work-order IDs;
- Core reference and RuntimeAttestation SHA-256;
- exact `SemanticInput` and Semantic View SHA-256;
- calculator prompt and response-schema SHA-256;
- phase, selected norms, active layers, triggers, and scopes through the
  hashed view;
- issue and expiry times.

Submission is size-limited and single-use. An invalid calculation consumes
that attempt; a fresh work order is required. The submitted object receives
the same strict validation and gate constraints as an API-provider result.
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

The current host route still uses the configured LLM for
`SemanticInputCompiler`. A zero-API route would require a separate signed host
compilation work order before Runtime can select the exact phase-complete
Semantic View.

## Stateless HOLD continuation

An operator-owned `HOLD` closes over an explicit handoff without introducing
Runtime memory. The `boris-execution/1.0` envelope requires:

- a non-empty conditional `candidate_result`, or `candidate_result: null` with
  `candidate_unavailable_reason`;
- for operator-owned targets, `hold.required_operator_input` with separate
  path-aware semantic unknowns
  and Core selector inputs used by formal predicates that evaluated to
  `UNKNOWN`;
- for operator-owned targets, an HMAC-SHA256 `continuation_token` bound to the exact `SemanticInput`, Core
  identity, session, HOLD targets, expiry, and resume count.

Runtime-owned, future, model, downstream, and unresolvable uncertainties never
become operator targets by default. A `HOLD` containing only those classes
retains the conditional candidate and returns
`resolution_not_operator_owned` without a token.

Resume uses the same `/runtime/execute` and `boris.execute` entry. Runtime
verifies the signature, expiry, session, and current Core identity before any
semantic LLM call. It reconstructs the signed `SemanticInput`, records the
operator statement as evidence, applies only values for paths declared in the
signed handoff, verifies that every signed target is closed, and only then
reruns Semantic Executor without calling `SemanticInputCompiler` again. A new
HOLD issues a new token containing the updated semantic input. Formal predicate
constraints remain diagnostic: Runtime never preselects the value that would
make a predicate true.

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
versioned MCP Apps resource `ui://boris/developer-surface-v2.html`. The
component receives:

- the candidate and handoff through model-visible `structuredContent`;
- concise gate-preserving instructions through `content`;
- the full sanitized `boris-execution-trace/1.0` only through tool-result
  `_meta`.

The component renders the constrained gate, phase, candidate, structured
operator form, semantic summary, and expandable complete trace. Its Resume
action uses MCP Apps `tools/call` to invoke the same `boris.execute`; there is
no second debug or continuation tool. It has no external assets or network
allowlist. Production mode neither links nor publishes the UI resource.

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
