class SIMA:

    def analyze(self, event):
        text = event.get("input", "")
        semantic = event.get("semantic_interpretation", {})
        bois = event.get("bois", {})
        ambiguity = semantic.get("ambiguity_score")

        if ambiguity is None:
            uncertainty = 0.3 if len(text) > 10 else 0.8
        else:
            uncertainty = float(ambiguity)

        risk = min(
            1.0,
            uncertainty + (0.1 if bois.get("required_information") else 0.0)
        )

        return {
            "facts": [text],
            "uncertainty": uncertainty,
            "risk": risk
        }
