# Runtime Session Lifecycle

## Purpose

This document defines the lifecycle of BOIS / SIMA / BORIS definitions inside the Middleware SDK.

It freezes the architectural boundary between:

- Phase 2 — Core Loader System
- Phase 3 — Protocol Engine

The runtime implementation MUST follow this lifecycle.

---

# Fundamental Principle

BOIS, SIMA and BORIS are declarative specifications.

They are never executed directly.

They become executable only after passing through the Core Loader pipeline.

---

# Lifecycle


Core Source
│
▼
Loader
│
▼
Normalizer
│
▼
Validator
│
▼
Core Lock (Immutable)
│
▼
Runtime Session
│
▼
Protocol Engine


Each stage has exactly one responsibility.

No stage may bypass another.

---

# Stage Definitions

## Core Source

Possible sources:

- Markdown
- JSON
- YAML
- Folder-based definitions
- GitHub Release

This stage is responsible only for providing BOIS definitions.

It contains no executable logic.

---

## Loader

Responsibilities:

- locate source
- detect format
- read content

Loader MUST NOT:

- validate protocol
- modify definitions
- execute protocol

---

## Normalizer

Responsibilities:

- convert all supported formats into one canonical internal structure

Normalizer MUST NOT:

- change semantics
- inject runtime state
- execute BOIS logic

---

## Validator

Responsibilities:

- validate structural integrity
- verify required sections
- reject invalid definitions

Validator MUST NOT:

- repair invalid definitions
- infer missing meaning

---

## Core Lock

Responsibilities:

- freeze canonical structure
- guarantee immutability during session

After locking:

- no runtime component may modify BOIS definitions

---

## Runtime Session

Runtime Session is the first executable object.

It contains:

- immutable Core
- runtime state
- session metadata

Runtime Session owns execution state.

Runtime Session does NOT own BOIS definitions.

---

## Protocol Engine

Protocol Engine begins only after Runtime Session exists.

It receives:

- Runtime Session
- User Input

It does not read raw files.

It does not parse Markdown.

It operates only on immutable canonical Core.

---

# Ownership Model


Files
↓
Core Loader
↓
Immutable Core
↓
Runtime Session
↓
Protocol Engine


Execution starts ONLY after Runtime Session has been created.

---

# Architectural Rules

Rule 1

Protocol Engine MUST NEVER load files.

Rule 2

Protocol Engine MUST NEVER modify Core.

Rule 3

Runtime Session MUST reference exactly one immutable Core.

Rule 4

Core Loader MUST finish completely before Protocol Engine starts.

Rule 5

BOIS, SIMA and BORIS remain declarative throughout the entire lifecycle.

---

# Non-Goals

Runtime Session is NOT:

- memory storage
- conversation history
- database
- agent
- planner
- tool manager

Those components belong to later phases.
