import os


class LLMAdapter:
    def call(self, prompt: str) -> str:
        raise NotImplementedError


class MockLLMAdapter(LLMAdapter):
    """Strict mock adapter. It returns schema-compatible protocol text only."""

    def call(self, prompt: str) -> str:
        user_input = self._extract_user_input(prompt)
        lowered = user_input.lower()

        if "clarification:" in lowered:
            return f"ANSWER: Protocol answer for: {user_input}"

        if lowered.startswith("tool "):
            return f"TOOL_CALL: {user_input[5:].strip()}"

        if lowered.startswith("question "):
            return f"QUESTION: {user_input[9:].strip()}"

        return f"ANSWER: Protocol answer for: {user_input}"

    @staticmethod
    def _extract_user_input(prompt):
        marker = "USER_INPUT:"
        if marker not in prompt:
            return ""
        return prompt.rsplit(marker, 1)[-1].strip()


class OpenAIAdapter(LLMAdapter):
    """Optional OpenAI adapter. It only performs inference through call()."""

    def __init__(self, model=None, api_key=None):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def call(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Return exactly one line as 'ANSWER:', 'QUESTION:', 'TOOL_CALL:', or 'GAP:'.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""
