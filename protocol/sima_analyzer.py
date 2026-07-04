class SIMAAnalyzer:
    """SIMA layer: deterministic uncertainty, risk, and missing-field analysis."""

    def analyze(self, user_input, state):
        text = (user_input or "").strip()
        lowered = text.lower()
        missing_fields = []

        if not text:
            missing_fields.append("request")

        if "clarification:" not in lowered and self._needs_observable_context(lowered):
            missing_fields.append("observable_context")

        repeated_fields = [
            field for field in missing_fields
            if state.has_asked_about(field)
        ]
        risk = 0.8 if missing_fields else 0.2

        return {
            "risk": risk,
            "missing_fields": missing_fields,
            "repeated_fields": repeated_fields,
            "question": self._question_for(missing_fields),
        }

    @staticmethod
    def _needs_observable_context(text):
        asks_about_private_state = any(
            phrase in text
            for phrase in (
                "what color are my",
                "what colour are my",
                "where are my",
                "what am i wearing",
            )
        )
        return asks_about_private_state

    @staticmethod
    def _question_for(missing_fields):
        if "request" in missing_fields:
            return "What request should the middleware process?"
        if "observable_context" in missing_fields:
            return "Provide the missing observable context."
        if missing_fields:
            return "Provide the missing information."
        return ""

