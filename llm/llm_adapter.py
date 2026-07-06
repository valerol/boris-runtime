import os
import json


class LLMAdapter:
    debug_prompt_enabled = False

    def debug_prompt(self, final_prompt: str) -> None:
        if not self.debug_prompt_enabled:
            return

        print("========== BOIS PROMPT (DEV MODE) ==========")
        print(final_prompt)
        print("============================================")

    def call(self, prompt: str) -> str:
        raise NotImplementedError


class MockLLMAdapter(LLMAdapter):
    """Strict mock adapter. It returns schema-compatible protocol text only."""

    adapter_name = "mock"

    def __init__(self, forced_outputs=None, debug_prompt_enabled=False):
        self.forced_outputs = list(forced_outputs or [])
        self.debug_prompt_enabled = debug_prompt_enabled

    def call(self, prompt: str) -> str:
        self.debug_prompt(prompt)

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

    def __init__(self, model=None, api_key=None, debug_prompt_enabled=False):
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise RuntimeError("BOIS_LLM=openai requires OPENAI_API_KEY")

        from openai import OpenAI

        self.client = OpenAI(api_key=resolved_api_key)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.debug_prompt_enabled = debug_prompt_enabled

    def call(self, prompt: str) -> str:
        messages = [
            {
                "role": "system",
                "content": "Return only one JSON object with type, content, and metadata.",
            },
            {"role": "user", "content": prompt},
        ]
        if self.debug_prompt_enabled:
            print("========== BOIS PROMPT (DEV MODE) ==========")
            print("SYSTEM_MESSAGE:")
            print(messages[0]["content"])
            print("")
            print("USER_MESSAGE:")
            print(prompt)
            print("============================================")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
        )
        return response.choices[0].message.content or ""
