class SIMA:

    def analyze(self, event):
        text = event.get("input", "")

        return {
            "facts": [text],
            "uncertainty": 0.3 if len(text) > 10 else 0.8,
            "risk": 0.2
        }
