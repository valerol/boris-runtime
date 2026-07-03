from kernel.llm import LLM


SEMANTIC_INTERPRETATION_KEYS = {
    "semantic_summary",
    "user_intent_hypothesis",
    "context_entities",
    "ambiguity_score",
    "risk_flags",
    "requires_clarification_hint"
}


def llm_semantic_interpretation(input: str) -> dict:
    return LLM().interpret_semantics(input)


def llm_semantic_interpretation_with(llm, input: str) -> dict:
    if hasattr(llm, "interpret_semantics"):
        interpretation = llm.interpret_semantics(input)
    else:
        interpretation = LLM(api_key="", load_environment=False).interpret_semantics(input)

    return normalize_semantic_interpretation(interpretation, input)


def normalize_semantic_interpretation(interpretation, user_input: str) -> dict:
    if not isinstance(interpretation, dict):
        interpretation = {}

    fallback = LLM(api_key="", load_environment=False).interpret_semantics(user_input)
    return {
        "semantic_summary": str(
            interpretation.get("semantic_summary") or fallback["semantic_summary"]
        ),
        "user_intent_hypothesis": str(
            interpretation.get("user_intent_hypothesis")
            or fallback["user_intent_hypothesis"]
        ),
        "context_entities": interpretation.get("context_entities")
        if isinstance(interpretation.get("context_entities"), list)
        else fallback["context_entities"],
        "ambiguity_score": _bounded_score(
            interpretation.get("ambiguity_score"),
            fallback["ambiguity_score"]
        ),
        "risk_flags": interpretation.get("risk_flags")
        if isinstance(interpretation.get("risk_flags"), list)
        else fallback["risk_flags"],
        "requires_clarification_hint": bool(
            interpretation.get(
                "requires_clarification_hint",
                fallback["requires_clarification_hint"]
            )
        )
    }


def _bounded_score(value, fallback):
    try:
        score = float(value)
    except (TypeError, ValueError):
        return fallback

    return min(1.0, max(0.0, score))
