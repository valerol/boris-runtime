# Protocol Engine

## Purpose

The Protocol Engine is Phase 3 of the BOIS / SIMA / BORIS Middleware SDK.

It starts only after a `RuntimeSession` exists. It does not load raw files,
parse Markdown, parse YAML, parse JSON, or create Core objects. It operates only
on the immutable canonical Core attached to the Runtime Session.

## Dependency Boundary

Required flow:

```text
Core Source
-> Phase 2 Core Loader
-> Canonical Core
-> Core Lock / Immutable Core
-> RuntimeSession
-> ProtocolEngine
-> Execution Loop
```

`ProtocolEngine` receives:

- `RuntimeSession`
- user input

It never receives a file path or raw source content.

## Execution Cycle

```text
INPUT
-> RuntimeSession with immutable canonical Core
-> SIMA signal analysis
-> BOIS structural framing
-> BORIS context application
-> Prompt Builder
-> LLM Adapter
-> Parser
-> Validation Layer
-> Post-LLM Control
-> OUTPUT or Clarification Loop
```

## SIMA Signals

`protocol/sima_signals.py` defines `SIMASignalExtractor`.

SIMA produces signals only:

- risk
- uncertainty
- missing fields
- ambiguity score
- observable context requirement

SIMA does not make final output decisions, does not block LLM invocation, and
does not directly return terminal GAP.

## BOIS Frame

`protocol/bois_frame.py` defines `BOISFrameBuilder`.

BOIS creates a structural frame from the immutable canonical BOIS core and user
input. It does not invent facts, call the LLM, or make final decisions.

## BORIS Context

`protocol/boris_context.py` defines `BORISContext`.

BORIS applies operator/domain context from the immutable canonical core and
runtime state. It does not override or mutate core and does not make final
decisions.

## Parser And Validator

Parser and validator are separate.

- Parser: converts raw LLM text into structured protocol output.
- Validator: verifies output shape and allowed output type.

Allowed output types:

- `ANSWER`
- `QUESTION`
- `TOOL_CALL`
- `GAP`

## Post-LLM Controller

`protocol/decision.py` defines `PostLLMController`.

PostLLMController operates only after the LLM response has been parsed and
validated. It may:

- attach session metadata
- reject repeated identical clarification questions
- cache exact input/output pairs through runtime state
- stop clarification loops when the configured limit is reached

PostLLMController must not:

- decide whether the initial LLM call is needed
- classify user intent semantically
- generate domain-specific clarification questions
- generate domain-specific answers

## GAP Semantics

GAP is a managed post-LLM protocol signal, not an automatic pre-LLM hard stop.

GAP may lead to loop continuation only when the LLM returned `GAP` and the CLI
provides clarification. Runtime does not create domain-specific GAP questions
before calling the LLM.

## Duplicate Input Cache

Exact duplicate input is detected after trimming. If the exact same string was
already processed in the same session, ProtocolEngine returns the cached output
with `metadata.duplicate = true` and does not call the LLM again.

## QuestionMemory

`protocol/question_memory.py` defines `QuestionMemory`.

Question memory stores asked questions, detects repeated questions, tracks
unresolved gaps, and prevents repeated clarification prompts. It uses
`RuntimeState` only and does not implement database persistence.
