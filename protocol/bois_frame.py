class BOISFrameBuilder:
    """Builds structural BOIS frame from immutable canonical core."""

    def build(self, core, user_input):
        return {
            "framework": "BOIS",
            "core": dict(core["bois_core"]),
            "input": user_input,
            "constraints": [
                "do_not_invent_facts",
                "use_core_as_structure_only",
            ],
        }

