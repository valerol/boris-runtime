# SDK API

This document lists the active programmatic boundaries.

## Core Surface

```python
from core_surface import load_core_surface

surface = load_core_surface(
    "/path/to/core-package.zip",
    purpose="evaluation",
)
```

`CoreSurface` is immutable and preserves release identity, normative identity,
manifest hash, content-set hash, component hashes, machine canon, and native
norm records.

## Context projection

```python
from application.context_projection import project_core_context

projection = project_core_context(surface, "Explain the STOP constraints")
```

The result contains a bounded passive projection. It is not a semantic
applicability decision.

## ContextProvider

```python
from application import ContextProvider

provider = ContextProvider()
packet = provider.frame(
    "Explain the applicable BOIS constraints",
    session_id="correlation-id",
    mode="developer",
)
```

The default provider reads `BORIS_CORE_PACKAGE` and loads the package through
Core Surface. The former `BORIS_CORE_PATH` alias is not supported.

`frame()` is stateless and never calls an LLM. Modes `default` and `production`
return the compact `boris-context/2.0` packet. Mode `developer` additionally
returns a sanitized `developer_trace` with Core Surface metadata and complete
projection selection diagnostics.

## ValidationEngine

```python
from application import ValidationEngine

report = ValidationEngine().validate(
    answer="ChatGPT-generated answer",
    context_packet=packet,
    validation_mode="deterministic",
)
```

Supported modes are `deterministic`, `semantic`, and `hybrid`. Semantic modes
require a validator adapter factory.

## Runtime compatibility

```python
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityVerifier,
)

compatibility = RuntimeCompatibilityVerifier().verify(
    surface,
    operator_acceptance=acceptance,
)
compatibility.require_semantic_evaluation(surface)
```

Compatibility acceptance authorizes only the declared scope. It does not
activate a package or authorize state mutation.

## Semantic Executor

```python
from semantic_executor import SemanticExecutor, SemanticInput

candidate = SemanticExecutor(
    surface,
    calculator,
    compatibility,
).execute(
    SemanticInput(
        phenomenon="Observed phenomenon",
        phase="semantic_evaluation",
    )
)
```

The return value is an `ExecutionCandidate`, not an executed action or
`KernelDecision`.

## LLM port

Location: `llm/llm_adapter.py`.

Implementations provide:

```python
call(prompt: str) -> str
call_structured(prompt: str, system_message: str) -> str
```

Configuration helpers live in `llm/config.py`.

## Removed SDK contracts

The following names are no longer supported:

- `BOISRuntime`;
- `RuntimeSession`;
- `ProtocolEngine`;
- `MiddlewareEngine`;
- `adapters.llm`;
- legacy `POST /run`;
- private `/runtime/ask`, `/runtime/reset`, and `/runtime/session/{id}`.
