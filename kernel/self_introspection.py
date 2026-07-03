from runtime.contracts import runtime_response


INTROSPECTION_TRIGGERS = {
    "what can you do",
    "who are you",
    "explain yourself",
    "capabilities",
    "limitations"
}


def is_introspection_query(query):
    normalized = query.strip().lower().rstrip("?.!")
    return normalized in INTROSPECTION_TRIGGERS


def explain_system(query: str, domain, memory=None) -> dict:
    domain_snapshot = domain.snapshot()
    trace_sources = ["domain"]
    memory_summary = None

    if memory is not None and hasattr(memory, "read_recent"):
        recent_events = memory.read_recent(limit=1)
        memory_summary = {
            "available": True,
            "recent_event_count": len(recent_events)
        }
        trace_sources.append("memory")

    answer = _build_answer(query, domain_snapshot)

    return runtime_response(
        "SELF_DESCRIPTION",
        answer=answer,
        trace={
            "source": trace_sources,
            "query": query,
            "domain": domain_snapshot,
            "memory": memory_summary
        },
        state={
            "mode": "self_introspection",
            "read_only": True,
            "domain": {
                "name": domain_snapshot.get("name"),
                "version": domain_snapshot.get("version")
            }
        },
        actions=[]
    )


def _build_answer(query, domain_snapshot):
    capabilities = "; ".join(domain_snapshot["capabilities"])
    limitations = "; ".join(domain_snapshot["limitations"])
    criteria = "; ".join(domain_snapshot["success_criteria"])

    return (
        f"I am BORIS Runtime ({domain_snapshot['name']} domain, "
        f"{domain_snapshot['version']}). I can help with: {capabilities}. "
        f"My current limitations are: {limitations}. "
        f"I aim to: {criteria}."
    )
