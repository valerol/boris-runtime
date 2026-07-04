class SIMASignalExtractor:
    """Produces SIMA signals only. It does not make final decisions."""

    def extract(self, user_input, state):
        text = (user_input or "").strip()
        lowered = text.lower()
        missing_fields = []
        observable_context_required = self._needs_observable_context(lowered)

        if not text:
            missing_fields.append("request")

        if observable_context_required and "clarification:" not in lowered:
            missing_fields.append("observable_context")

        uncertainty = 0.8 if missing_fields else 0.2
        risk = 0.8 if observable_context_required else (0.6 if missing_fields else 0.2)

        return {
            "risk": risk,
            "uncertainty": uncertainty,
            "missing_fields": missing_fields,
            "ambiguity_score": 0.7 if missing_fields else 0.1,
            "observable_context_required": observable_context_required,
        }

    @staticmethod
    def _needs_observable_context(text):
        return any(
            phrase in text
            for phrase in (
                "what color are my",
                "what colour are my",
                "where are my",
                "what am i wearing",
            )
        )

