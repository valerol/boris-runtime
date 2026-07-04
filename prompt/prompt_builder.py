class PromptBuilder:
    """Deterministic prompt builder for the Phase 1 protocol pipeline."""

    def build(self, bois_context, sima_analysis, boris_context, user_input, state):
        return "\n".join(
            [
                "BOIS/SIMA/BORIS MIDDLEWARE PROTOCOL",
                "Allowed response types: ANSWER, QUESTION, TOOL_CALL, GAP.",
                "",
                "BOIS_CONTEXT:",
                str(bois_context),
                "",
                "SIMA_ANALYSIS:",
                str(sima_analysis),
                "",
                "BORIS_CONTEXT:",
                str(boris_context),
                "",
                "CURRENT_STATE:",
                str(state.snapshot()),
                "",
                "RESPONSE_CONTRACT:",
                "Return exactly one line as '<TYPE>: <content>'.",
                "",
                "USER_INPUT:",
                user_input,
            ]
        )

