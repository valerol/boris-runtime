class BORISContext:
    """BORIS layer: operator/domain specialization injected into prompt."""

    def build(self, definitions, state):
        return {
            "name": "BORIS",
            "role": "operator/domain specialization",
            "definition": definitions.boris,
            "session": {
                "clarification_cycles": state.clarification_cycles,
                "max_clarification_cycles": state.max_clarification_cycles,
            },
        }

