# Architecture Reset

## New Principle

BOIS / SIMA / BORIS is a lightweight protocol middleware SDK. It enforces
protocol rules on top of existing LLM platforms such as the OpenAI API, Open
WebUI, Dify, LangGraph, and other chat-based systems.

It is not an AI platform, a full runtime system, a UI, a memory system, or an
agent framework.

## Separation Of Concerns

BOIS is a declarative cognitive and reasoning framework. It lives in
`core/definitions/bois.md` and is injected into prompts as definition text.

SIMA is an analytical risk, structure, and uncertainty model. It lives in
`core/definitions/sima.md` and supplies minimal declarative rules.

BORIS is the operator-specific specialization layer. It lives in
`core/definitions/boris.md` and defines behavioral constraints only.

The middleware runtime only executes protocol:

1. load definitions
2. build prompt
3. call an LLM adapter
4. parse the response contract
5. choose final answer, clarification, or tool request

The platform layer owns UI, authentication, memory, tools, storage, and
transport. These concerns enter the SDK only through adapters.

## Execution Pipeline

```text
Input
-> Core Loader (BOIS/SIMA/BORIS injection)
-> Prompt Builder
-> LLM Call (via adapter)
-> Response Parser
-> Protocol Loop Decision
   -> final answer
   -> clarification request
   -> tool call (via adapter)
-> Output
```

## Artifact Reclassification

Protocol spec:

- `core/definitions/bois.md`
- `core/definitions/sima.md`
- `core/definitions/boris.md`

Reference implementation:

- `archive/v0-runtime/runtime`
- `archive/v0-runtime/core/schema.json`
- `archive/v0-runtime/core/epistemic_hierarchy.json`
- `archive/v0-runtime/adapters`

Legacy / archive:

- `archive/v0-runtime/kernel`
- `archive/v0-runtime/physiology`
- `archive/v0-runtime/server.py`
- `archive/v0-runtime/main_cli.py`
- `archive/v0-runtime/tests`

## Runtime Rules

- Stateless between executions unless an external memory adapter is injected.
- Deterministic in protocol application.
- Minimal logic; no AI behavior lives inside the runtime.
- LLM-agnostic and platform-agnostic.
- No Open WebUI, Telegram, database, vector database, or UI coupling in core.

## CLI Validation

Run from the repository root:

```bash
python cli/run.py
```

The default CLI uses `MockLLMAdapter`, so it works without network access or API
keys. Set `BOIS_LLM=openai` and `OPENAI_API_KEY` only when validating against a
real OpenAI model.
