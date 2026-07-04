# SDK API

This document describes the current public API implemented in the repository.
It does not list planned APIs.

## BOISRuntime

Location: `runtime/runtime.py`

`BOISRuntime` is the Phase 1 CLI MVP composition root. It wires the explicit
runtime loop with:

- `CoreLoader`
- `BOIParser`
- `SIMAAnalyzer`
- `BORISContext`
- `PromptBuilder`
- `LLMAdapter`
- `ProtocolResponseParser`
- `DecisionExecutor`

```python
from runtime.runtime import BOISRuntime

runtime = BOISRuntime()
output = runtime.run("Explain BOIS Runtime")
print(output["type"])
print(output["content"])
```

The returned object is a dictionary with:

- `type`: `ANSWER`, `QUESTION`, `TOOL_CALL`, or `GAP`
- `content`: string
- `metadata`: object

## RuntimeSession

Location: `runtime/session.py`

`RuntimeSession` holds exactly one immutable canonical Core, runtime state,
session id, and creation timestamp.

Use `create_runtime_session(core_ref, session_id=None)` to create a session from
the Phase 2 Core Loader.

## ProtocolEngine

Location: `protocol/engine.py`

`ProtocolEngine` runs one protocol turn against an existing `RuntimeSession`.
It does not load files or parse raw core definitions.

```python
from llm.llm_adapter import MockLLMAdapter
from protocol.engine import ProtocolEngine
from runtime.session import create_runtime_session

session = create_runtime_session("core/definitions")
engine = ProtocolEngine(llm_adapter=MockLLMAdapter())
output = engine.run_turn(session, "Explain BOIS Runtime")
print(output["type"])
print(output["content"])
```

## MiddlewareEngine

Location: `runtime/engine.py`

`MiddlewareEngine` is the stateless protocol execution engine. It is
constructed with an LLM adapter and optional loader, prompt builder, response
parser, protocol loop, memory adapter, and tool adapter.

```python
from adapters.llm import MockLLMAdapter
from runtime.engine import MiddlewareEngine

engine = MiddlewareEngine(MockLLMAdapter())
response = engine.run("Explain BOIS Runtime")
print(response.type)
print(response.content)
```

## MiddlewareEngine.run(user_input, context=None)

Runs one protocol execution. `user_input` is normalized to a stripped string.
`context` is optional caller-provided metadata.

Returns a `ProtocolResponse`.

If `user_input` is empty, the engine returns a clarification response without
calling the LLM adapter.

## CoreLoader

Location: `core/loader.py`

Loads BOIS, SIMA, and BORIS definition files from `core/definitions/` by
default and returns `ProtocolDefinitions`.

## PromptBuilder

Location: `runtime/prompt_builder.py`

Builds the prompt passed to the LLM adapter by combining protocol definitions,
request data, and optional memory adapter context.

## ResponseParser

Location: `runtime/response_parser.py`

Parses model output into `ParsedResponse`. It recognizes `FINAL:`,
`CLARIFY:`, and `TOOL:` prefixes.

## ProtocolLoop

Location: `runtime/loop.py`

Converts `ParsedResponse` into `ProtocolResponse` with one of the current
outcomes: `final`, `clarification`, or `tool_call`.

## ProtocolRequest

Location: `core/protocol.py`

Dataclass containing:

- `user_input`
- `context`

## ProtocolResponse

Location: `core/protocol.py`

Dataclass containing:

- `type`
- `content`
- `trace`
- `tool_request`

## ParsedResponse

Location: `core/protocol.py`

Dataclass containing:

- `kind`
- `content`
- `tool_name`
- `tool_args`
