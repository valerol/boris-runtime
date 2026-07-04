class BORISContext:
    """BORIS layer: operator/domain specialization injected into prompt."""

    def build(self, definitions, state):
        if isinstance(definitions, dict) or hasattr(definitions, "__getitem__"):
            return {
                "name": "BORIS",
                "role": "operator/domain specialization",
                "context": dict(definitions["boris_context"]),
                "session": {
                    "session_id": state.session_id,
                    "clarification_cycles": state.clarification_cycles,
                    "max_clarification_cycles": state.max_clarification_cycles,
                },
            }

        return {
            "name": "BORIS",
            "role": "operator/domain specialization",
            "definition": definitions.boris,
            "session": {
                "clarification_cycles": state.clarification_cycles,
                "max_clarification_cycles": state.max_clarification_cycles,
            },
        }
