class SIMASignalExtractor:
    """Produces generic SIMA prompt metadata only."""

    def extract(self, user_input, state):
        text = (user_input or "").strip()
        missing_fields = ["request"] if not text else []
        uncertainty = 0.6 if missing_fields else 0.2
        risk = 0.5 if missing_fields else 0.2

        return {
            "risk": risk,
            "uncertainty": uncertainty,
            "missing_fields": missing_fields,
            "ambiguity_score": 0.5 if missing_fields else 0.1,
        }
