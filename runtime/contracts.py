TYPE_ALIASES = {
    "QUESTION": "CLARIFICATION",
    "FINAL": "ANSWER"
}

VALID_TYPES = {"ANSWER", "CLARIFICATION", "TOOL_REQUEST", "ERROR"}


def normalize_response_type(response_type):
    normalized = TYPE_ALIASES.get(response_type, response_type)
    return normalized if normalized in VALID_TYPES else "ERROR"


def runtime_response(
    response_type,
    answer="",
    trace=None,
    state=None,
    actions=None
):
    normalized_type = normalize_response_type(response_type)
    plain_answer = "" if answer is None else str(answer)

    return {
        "type": normalized_type,
        "answer": plain_answer,
        "content": plain_answer,
        "trace": trace or {},
        "state": state or {},
        "actions": actions or []
    }
