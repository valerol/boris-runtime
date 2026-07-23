# SDK API

This document describes the current public API implemented in the repository.
It does not list planned APIs.

## BOISRuntime

Location: `runtime/runtime.py`

`BOISRuntime` is the canonical Runtime composition root. It owns one
`RuntimeSession`, one `ProtocolEngine`, and the clarification loop.

```python
from runtime.runtime import BOISRuntime

runtime = BOISRuntime()
output = runtime.run("Explain BOIS Runtime")
print(output["type"])
print(output["content"])
```

The returned dictionary contains:

- `type`: `ANSWER`, `QUESTION`, `TOOL_CALL`, or `GAP`;
- `content`: string;
- `metadata`: object.

`BOISRuntime.frame(...)` reuses the same Runtime framing path without calling
the LLM or advancing conversation state.

## RuntimeSession

Location: `runtime/session.py`

`RuntimeSession` holds one immutable Phase 2 Core, mutable Runtime state, session
ID, and creation timestamp.

Use `create_runtime_session(core_ref, session_id=None)` to create a session.
Core Surface and Semantic Executor are deliberately not attached to this
session in Phase 4F.

## ProtocolEngine

Location: `protocol/engine.py`

`ProtocolEngine` runs one canonical protocol turn against an existing
`RuntimeSession`.

```python
from llm.llm_adapter import MockLLMAdapter
from protocol.engine import ProtocolEngine
from runtime.session import create_runtime_session

session = create_runtime_session("core/definitions")
engine = ProtocolEngine(llm_adapter=MockLLMAdapter())
output = engine.run_turn(session, "Explain BOIS Runtime")
```

## Core Surface

Location: `core_surface/`

```python
from core_surface import load_core_surface

surface = load_core_surface("/path/to/core.zip", purpose="evaluation")
```

The immutable result separates exact archive, content-set, and manifest hashes.
It loads and validates passive package data but does not calculate semantics.

## Runtime Compatibility

Location: `runtime_compatibility/`

`RuntimeCompatibilityVerifier.verify(...)` reads the package's runtime schemas,
templates, and validation specification and returns a substrate declaration,
operator decision, specification checks, and RuntimeAttestation.

An attestation accepted for `semantic_evaluation` is mandatory before the
Semantic Executor calculator can be called.

## SemanticExecutor

Location: `semantic_executor/`

`SemanticExecutor(surface, calculator, compatibility)` returns a non-executing
`ExecutionCandidate`. It is isolated from `ProtocolEngine`, Runtime sessions,
tools, memory, HTTP, and MCP.

See [semantic_executor.md](semantic_executor.md) for the complete contract.

## Canonical LLM port

Location: `llm/llm_adapter.py`

Adapters implement:

```python
call(prompt: str) -> str
call_structured(prompt: str, system_message: str) -> str
```

`runtime.config.LazyLLMAdapter` forwards both operations without losing the
structured system contract or JSON mode.

## Compatibility facades

The following imports remain available for earlier SDK callers, but they are no
longer independent execution paths:

- `runtime.engine.MiddlewareEngine` delegates to `BOISRuntime`;
- `api.fastapi_server.app` is an alias of `api.app.app`;
- legacy `POST /run` remains available there as a deprecated compatibility
  route and delegates through `MiddlewareEngine`;
- `adapters.llm` names are backed by the canonical `llm` implementations.

Legacy component injection into `MiddlewareEngine` is rejected. The earlier
`runtime.prompt_builder`, `runtime.response_parser`, and `ProtocolLoop` were
removed during Phase 4R.
