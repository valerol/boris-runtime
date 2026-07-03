# BOIS / SIMA / BORIS Middleware SDK

This repository has been reset from a runtime/platform MVP into a lightweight
protocol middleware SDK.

The project is not an AI platform and not a full runtime system. It enforces
BOIS / SIMA / BORIS protocol definitions on top of existing LLM platforms.

## Current Structure

```text
bois-middleware/
  core/          declarative protocol definitions and loader
  runtime/       minimal stateless protocol execution
  adapters/      LLM, memory, tool, and platform boundaries
  cli/           validation CLI
  api/           optional API boundary
  examples/      usage examples
  docs/          architecture reset notes
  archive/       v0 runtime artifacts
```

## Run CLI

```bash
cd bois-middleware
python cli/run.py
```

The CLI uses a deterministic mock LLM adapter by default and has no UI,
database, vector store, Telegram, or Open WebUI dependency.

## Architecture

Read `bois-middleware/docs/architecture_reset.md` for the reset model,
artifact reclassification, and execution pipeline.
