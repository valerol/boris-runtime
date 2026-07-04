# Vision

`boris-runtime` is the repository for the BOIS / SIMA / BORIS Middleware SDK.
It exists to provide a lightweight protocol execution layer that can sit on top
of existing LLM platforms without becoming a platform itself.

The project is not an AI platform, chatbot product, UI, memory system, vector
database, or agent framework. It is an SDK that loads declarative protocol
definitions, builds prompts, calls an LLM through an adapter, parses the model
response, and returns a protocol-shaped result.

## Responsibility Model

- BOIS = declarative cognitive framework
- SIMA = analytical uncertainty, risk, and structure layer
- BORIS = operator or domain specialization
- Runtime = protocol executor
- Platform = external UI, tools, memory, auth, and storage

The runtime does not own user experience, persistence, authentication, tool
execution, or long-term memory. Those concerns belong to the host platform and
enter the SDK only through adapters.

