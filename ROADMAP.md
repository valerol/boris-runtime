# BOIS Middleware SDK Roadmap

## Purpose

BOIS / SIMA / BORIS Middleware SDK is a protocol execution layer for applying
declarative BOIS, SIMA, and BORIS definitions on top of existing LLM platforms.

The roadmap tracks SDK evolution only. It does not turn the project into an AI
platform, agent runtime, UI, memory system, or storage layer.

## Current Focus

- Keep BOIS, SIMA, and BORIS definitions declarative.
- Keep runtime execution stateless and deterministic.
- Maintain adapter boundaries for LLM, memory, tools, and platforms.
- Validate the protocol pipeline through the CLI.

## Milestones

### Phase 1: Middleware SDK Foundation

- Root-level SDK structure established.
- Legacy runtime v0 archived under `archive/v0-runtime`.
- Declarative definitions placed under `core/definitions`.
- Minimal runtime pipeline implemented.
- Mock LLM CLI validation available.

### Phase 2: Protocol Contract Stabilization

- Define stable request and response envelopes.
- Tighten response parser contract.
- Document clarification and tool-call semantics.
- Add compatibility notes for chat-based host platforms.

### Phase 3: Adapter Expansion

- Add optional real LLM adapters.
- Define memory adapter examples without built-in persistence.
- Define tool adapter examples without runtime-owned tool execution.
- Document platform integration patterns.

### Phase 4: Specification Hardening

- Version BOIS, SIMA, and BORIS definition files.
- Add protocol conformance examples.
- Add lightweight validation checks for SDK boundaries.
- Maintain changelog entries for breaking protocol changes.

## Non-Goals

- No built-in UI.
- No built-in database.
- No vector database.
- No autonomous agent system.
- No platform-specific coupling.
- No executable BOIS, SIMA, or BORIS reasoning engines.

