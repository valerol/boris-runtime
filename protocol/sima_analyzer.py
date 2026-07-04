class SIMAAnalyzer:
    """Compatibility SIMA analyzer. Produces generic signals only."""

    def analyze(self, user_input, state):
        text = (user_input or "").strip()
        missing_fields = ["request"] if not text else []
        risk = 0.5 if missing_fields else 0.2

        return {
            "risk": risk,
            "uncertainty": 0.6 if missing_fields else 0.2,
            "missing_fields": missing_fields,
            "repeated_fields": [],
            "question": "",
        }
