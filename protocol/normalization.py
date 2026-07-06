CLARIFICATION_METADATA_KEYS = {
    "missing_fields",
    "needs_clarification",
    "requires_clarification",
    "gap_key",
}

CLARIFICATION_PHRASES = (
    "please clarify",
    "clarify",
    "please specify",
    "specify",
    "provide more information",
    "provide more details",
    "provide details",
    "need more information",
    "need additional information",
    "cannot determine",
    "can't determine",
    "cannot answer without",
    "which one",
    "what exactly",
    "identify the",
    "describe the",
    "attach",
    "provide evidence",
    "missing information",
    "missing field",
    "уточните",
    "пожалуйста, уточните",
    "укажи",
    "укажите",
    "предоставьте",
    "предоставь",
    "добавьте",
    "добавь",
    "опишите",
    "опиши",
    "поясните",
    "поясни",
    "нужна дополнительная информация",
    "нужно больше информации",
    "не могу определить",
    "невозможно определить",
    "без дополнительной информации",
    "о каком",
    "о какой",
    "о каких",
)

FINAL_ANSWER_MARKERS = (
    "if you want",
    "если хотите",
    "могу также",
    "let me know",
)


def normalize_protocol_output_type(output):
    if getattr(output, "type", None) != "ANSWER":
        return output

    if not is_clarification_request_content(
        getattr(output, "content", ""),
        getattr(output, "metadata", {}) or {},
    ):
        return output

    output.type = "QUESTION"
    output.metadata = {
        **(output.metadata or {}),
        "normalized_output_type": True,
        "original_output_type": "ANSWER",
        "normalized_to_type": "QUESTION",
        "normalization_reason": "clarification_request_in_answer",
    }
    return output


def is_clarification_request_content(content: str, metadata: dict | None = None) -> bool:
    metadata = metadata or {}
    if _metadata_requests_clarification(metadata):
        return True

    text = (content or "").strip()
    if not text:
        return False

    lowered = text.lower()
    if _looks_like_optional_follow_up(lowered):
        return False

    phrase_hit = any(phrase in lowered for phrase in CLARIFICATION_PHRASES)
    question_like = "?" in text or "？" in text
    imperative_start = lowered.startswith((
        "please ",
        "could you ",
        "can you ",
        "уточните",
        "пожалуйста",
        "укажите",
        "предоставьте",
        "опишите",
        "поясните",
    ))
    cannot_without_info = any(
        marker in lowered
        for marker in (
            "without more information",
            "without additional information",
            "без дополнительной информации",
            "не имея дополнительной информации",
        )
    )

    return phrase_hit and (question_like or imperative_start or cannot_without_info)


def _metadata_requests_clarification(metadata):
    missing_fields = metadata.get("missing_fields")
    if isinstance(missing_fields, list) and any(str(item).strip() for item in missing_fields):
        return True

    for key in ("needs_clarification", "requires_clarification"):
        if metadata.get(key) is True:
            return True

    gap_key = str(metadata.get("gap_key", "")).strip().lower()
    if gap_key and any(marker in gap_key for marker in ("missing", "clarification", "unknown", "недостат", "уточ")):
        return True

    return False


def _looks_like_optional_follow_up(lowered):
    return any(marker in lowered for marker in FINAL_ANSWER_MARKERS)
