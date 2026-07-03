class PromptBuilder:
    """Builds an LLM prompt from protocol definitions and request data."""

    def build(self, definitions, request, memory_context=None):
        memory_text = memory_context or "No external memory adapter context."
        return "\n\n".join(
            [
                "You are an inference engine behind BOIS / SIMA / BORIS middleware.",
                "Follow the declarative protocol definitions below.",
                definitions.bois,
                definitions.sima,
                definitions.boris,
                "Response contract:",
                "- Use 'FINAL: <answer>' for a final answer.",
                "- Use 'CLARIFY: <question>' when one clarification is required.",
                "- Use 'TOOL: <name> <json-args>' only when a provided tool is required.",
                f"External memory context: {memory_text}",
                f"User input: {request.user_input}",
            ]
        )

