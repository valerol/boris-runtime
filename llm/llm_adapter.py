import os
import json


class LLMAdapter:
    def call(self, prompt: str) -> str:
        raise NotImplementedError


class MockLLMAdapter(LLMAdapter):
    """Strict mock adapter. It returns schema-compatible protocol text only."""

    adapter_name = "mock"

    def __init__(self, forced_outputs=None):
        self.forced_outputs = list(forced_outputs or [])

    def call(self, prompt: str) -> str:
        if self.forced_outputs:
            return self.forced_outputs.pop(0)

        user_input = self._extract_user_input(prompt)
        lowered = user_input.lower()

        if "clarification:" in lowered:
            return self._response("ANSWER", f"Protocol answer for: {user_input}")

        if lowered.startswith("tool "):
            return self._response("TOOL_CALL", user_input[5:].strip())

        return self._response("ANSWER", f"Protocol answer for: {user_input}")

    @staticmethod
    def _extract_user_input(prompt):
        marker = "USER_INPUT:"
        if marker not in prompt:
            return ""
        return prompt.rsplit(marker, 1)[-1].strip()

    @staticmethod
    def _response(output_type, content, metadata=None):
        return json.dumps({
            "type": output_type,
            "content": content,
            "metadata": metadata or {},
        })


class OpenAIAdapter(LLMAdapter):
    """Optional OpenAI adapter. It only performs inference through call()."""

    adapter_name = "openai"

    def __init__(self, model=None, api_key=None):
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise RuntimeError("BOIS_LLM=openai requires OPENAI_API_KEY")

        from openai import OpenAI

        self.client = OpenAI(api_key=resolved_api_key)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def call(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only one JSON object with type, content, and metadata.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""
