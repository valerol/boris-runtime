# Protocol

The middleware executes one request through a fixed protocol pipeline:

```text
Input
-> BOIS/SIMA/BORIS protocol layers
-> Prompt Builder
-> LLM Adapter
-> Response Parser
-> Decision Executor
-> Protocol Loop
-> Output
```

## Pipeline Steps

- Input: user text plus optional caller context.
- Core Loader: loads BOIS, SIMA, and BORIS declarative definitions.
- BOIS layer: injects declarative reasoning structure.
- SIMA layer: detects uncertainty, risk, and missing fields.
- BORIS layer: injects operator/domain context.
- Prompt Builder: injects definitions and request data into a prompt.
- LLM Adapter: calls the selected LLM implementation.
- Response Parser: parses the response contract.
- Decision Executor: handles protocol decisions without agent behavior.
- Protocol Loop: repeats only for GAP or QUESTION clarification.
- Output: returns a strict protocol dictionary.

## Runtime Outcomes

Allowed outcomes are:

- `ANSWER`
- `QUESTION`
- `TOOL_CALL`
- `GAP`

The current parser recognizes:

- `ANSWER: <answer>`
- `QUESTION: <question>`
- `TOOL_CALL: <tool request>`
- `GAP: <missing information>`

## Protocol Boundary

BOIS, SIMA, and BORIS are injected as declarative definitions. The runtime does
not reason philosophically itself, does not implement a cognitive model, and
does not own AI behavior. It only enforces the protocol boundary around prompt
construction, LLM calls, response parsing, and outcome selection.
