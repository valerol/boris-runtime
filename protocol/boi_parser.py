class BOIParser:
    """BOIS layer: exposes declarative reasoning structure to the prompt."""

    def parse(self, definitions):
        return {
            "name": "BOIS",
            "role": "declarative cognitive framework",
            "definition": definitions.bois,
            "prompt_rule": "Use BOIS as reasoning structure, not runtime logic.",
        }

