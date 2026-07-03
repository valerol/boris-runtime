class BOIS:

    def reason(self, semantic_context, memory):
        semantic = semantic_context.get(
            "semantic_interpretation",
            semantic_context
        )
        ambiguity = semantic.get("ambiguity_score", 0)
        requires_clarification = semantic.get("requires_clarification_hint", False)

        required_information = []

        if requires_clarification or ambiguity > 0.6:
            required_information.append("need_more_input")

        return {
            "hypotheses": [
                semantic.get(
                    "user_intent_hypothesis",
                    "The user wants a response to the request."
                )
            ],
            "required_information": required_information,
            "semantic_summary": semantic.get("semantic_summary", ""),
            "reasoning_paths": [
                {
                    "source": "semantic_interpretation",
                    "summary": semantic.get("semantic_summary", "")
                }
            ],
            "plan": "minimal_test_first"
        }
