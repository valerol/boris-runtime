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
)
```

The default provider reads `BORIS_CORE_PACKAGE` and loads the package through
Core Surface. Production currently points it at the checked-out
`/opt/boris-core` directory; an exact ZIP is not required. The former
`BORIS_CORE_PATH` alias is not supported.

`frame()` is stateless and never calls an LLM. `BORIS_RUNTIME_MODE=dev`
additionally returns a sanitized `developer_trace` with Core Surface metadata
and complete projection selection diagnostics. Any other or absent value
returns the compact `boris-context/2.0` packet.

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
from application.execution import OperatorAcceptanceProvider
from runtime_compatibility import RuntimeCompatibilityVerifier

acceptance = OperatorAcceptanceProvider().get(surface)
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

## Application execution and HOLD resume

```python
from application.execution import ExecutionService

service = ExecutionService()
result = service.execute(
    "Evaluate this phenomenon.",
    session_id="correlation-id",
    context={"facts": {}, "evidence": [], "authority": {}},
)

if result["gate"] == "HOLD":
    required = result["hold"]["required_operator_input"]
    if required is not None:
        # Collect only the signed current-cycle selector values.
        operator_values = {
            "authorization.granted": True,
        }
        result = service.execute(
            session_id=result["session_id"],
            resume={
                "continuation_token": result["hold"][
                    "continuation_token"
                ],
                "operator_input": {
                    "resolution_mode": "PROVIDE_INFORMATION",
                    "statement": "The operator clarification.",
                    "values": operator_values,
                    "resolved_unknowns": [
                        item["unknown_id"]
                        for item in required["semantic_unknowns"]
                    ],
                },
            },
        )
```

`BORIS_CONTINUATION_SECRET` must contain at least 32 bytes before Runtime can
issue or verify a system-HOLD token. A valid resume reconstructs the signed
`SemanticInput`, verifies the current Core identity and session, creates a
current-cycle `OperatorDecision`, and skips `SemanticInputCompiler`.
`semantic_unknowns`, `predicate_inputs`, and `system_targets` remain separate.
The five modes are `PROVIDE_INFORMATION`, `CONFIRM_ASSUMPTION`,
`ALLOW_CONDITIONAL_PROCEEDING`, `CHANGE_SCOPE`, and `TERMINATE_CYCLE`.
The decision is not written into `facts`, `evidence`, `authority`, or
persistent Runtime state. Value and conditional modes never force a gate;
termination returns a terminal operator-resolved `HOLD` without invoking the
calculator.

The default service constructs canonical `ServerLLMProvider`. The return
envelope identifies `semantic_provider: SERVER_LLM` and contains an
`ExecutionCandidate` plus `boris-independent-review/1.0`, not an executed
action or `KernelDecision`. Review `PASS` supports the candidate's existing
gate and does not replace it. The semantic provider uses one low-level adapter
instance for compilation and calculation; Independent Reviewer uses a new
adapter instance and distinct IND2 method. A signed resume skips compilation,
recalculates, and reviews the new exact candidate.
`BORIS_SERVER_LLM_TIMEOUT_SECONDS` bounds each low-level provider request.

## Experimental `ChatGPTHostProvider`

```python
work_order = service.prepare_host(
    "Evaluate this phenomenon.",
    session_id="correlation-id",
    context={"facts": {}, "evidence": [], "authority": {}},
)

# The current ChatGPT host calculates only work_order["semantic_prompt"]
# and returns one object matching work_order["response_schema"].
result = service.submit_host(
    work_order_id=work_order["work_order_id"],
    work_order_token=work_order["submission_contract"][
        "work_order_token"
    ],
    semantic_result=semantic_result,
    session_id=work_order["session_id"],
)
```

The host work-order secret and TTL are configured through
`BORIS_HOST_EXECUTOR_SECRET` and
`BORIS_HOST_WORK_ORDER_TTL_SECONDS`. A work order is bound to the exact Core,
attestation, input, view, prompt, schema, session, phase, and scope. It can be
submitted once. The PoC registry is in-memory and single-process.

`prepare_host()` prepares the compiler contract without calling the configured
LLM; `submit_host()` performs no LLM call and reuses the normal semantic
validator and deterministic gate guards. This compatibility route is private
and experimental; public MCP does not expose these methods.

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
