# SDK API

This document describes the current public API implemented in the repository.
It does not list planned APIs.

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

