class PromptBuilder:
    """Deterministic prompt builder for the protocol pipeline."""

    def build(self, core, sima_signals, bois_frame, boris_context, user_input, state):
        return "\n".join(
            [
                "BOIS/SIMA/BORIS MIDDLEWARE PROTOCOL",
                "Allowed response types: ANSWER, QUESTION, TOOL_CALL, GAP.",
                "Return exactly one line as '<TYPE>: <content>'.",
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
                "USER_INPUT:",
                user_input,
            ]
        )
