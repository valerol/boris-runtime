# Protocol

The middleware executes one request through a fixed protocol pipeline:

```text
Input
-> Core Loader
-> Prompt Builder
-> LLM Adapter
-> Response Parser
-> Protocol Loop
-> Output
```

## Pipeline Steps

- Input: user text plus optional caller context.
- Core Loader: loads BOIS, SIMA, and BORIS declarative definitions.
- Prompt Builder: injects definitions and request data into a prompt.
- LLM Adapter: calls the selected LLM implementation.
- Response Parser: parses the response contract.
- Protocol Loop: chooses the protocol outcome.
- Output: returns a `ProtocolResponse`.

## Runtime Outcomes

Allowed outcomes are:

- final answer
- clarification request
- tool call request

The current parser recognizes:

- `FINAL: <answer>`
- `CLARIFY: <question>`
- `TOOL: <name> <json-args>`

## Protocol Boundary

BOIS, SIMA, and BORIS are injected as declarative definitions. The runtime does
not reason philosophically itself, does not implement a cognitive model, and
does not own AI behavior. It only enforces the protocol boundary around prompt
construction, LLM calls, response parsing, and outcome selection.

