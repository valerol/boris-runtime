class PromptBuilder:
    """Deterministic prompt builder for the protocol pipeline."""

    def build(self, core, sima_signals, bois_frame, boris_context, user_input, state):
        return "\n".join(
            [
                "BOIS/SIMA/BORIS MIDDLEWARE PROTOCOL",
                "Return ONLY one structured response object.",
                "Required schema:",
                "{'type': 'ANSWER|QUESTION|TOOL_CALL|GAP', 'content': 'string', 'metadata': {}}",
                "Do not return plain text outside schema.",
                "",
                "IMMUTABLE_CORE:",
                str({
                    "bois_core": dict(core["bois_core"]),
                    "sima_rules": dict(core["sima_rules"]),
                    "boris_context": dict(core["boris_context"]),
                    "meta": dict(core["meta"]),
                }),
                "",
                "SIMA_SIGNALS:",
                str(sima_signals),
                "",
                "BOIS_FRAME:",
                str(bois_frame),
                "",
                "BORIS_CONTEXT:",
                str(boris_context),
                "",
                "CURRENT_STATE:",
                str(state.snapshot()),
                "",
                "PREVIOUS_TURN:",
                str(state.last_decision),
                "",
                "USER_INPUT:",
                user_input,
            ]
        )
