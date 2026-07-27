import os
import json

from llm.errors import LLMConfigurationError, LLMProviderError


REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


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

    def call_structured(self, prompt: str, system_message: str) -> str:
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

    def call_structured(self, prompt: str, system_message: str) -> str:
        return self.call(prompt)

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

    def __init__(
        self,
        model=None,
        api_key=None,
        debug_prompt_enabled=False,
        reasoning_effort=None,
        timeout=None,
    ):
        resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_api_key:
            raise LLMConfigurationError(
                "BOIS_LLM=openai requires OPENAI_API_KEY"
            )

        from openai import OpenAI

        client_arguments = {"api_key": resolved_api_key}
        if timeout is not None:
            client_arguments["timeout"] = timeout
        self.client = OpenAI(**client_arguments)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        configured_effort = reasoning_effort
        if configured_effort is None and self.model.startswith("gpt-5"):
            configured_effort = os.getenv("OPENAI_REASONING_EFFORT")
        if configured_effort is None and self.model.startswith("gpt-5.6"):
            configured_effort = "medium"
        self.reasoning_effort = (
            str(configured_effort).strip().lower()
            if configured_effort is not None
            else None
        )
        if (
            self.reasoning_effort is not None
            and self.reasoning_effort not in REASONING_EFFORTS
        ):
            raise LLMConfigurationError(
                "OPENAI_REASONING_EFFORT must be one of: "
                + ", ".join(sorted(REASONING_EFFORTS))
            )
        self.debug_prompt_enabled = debug_prompt_enabled

    def call(self, prompt: str) -> str:
        return self._call(
            prompt,
            "Return only one JSON object with type, content, and metadata.",
            json_mode=False,
        )

    def call_structured(self, prompt: str, system_message: str) -> str:
        return self._call(prompt, system_message, json_mode=True)

    def _call(self, prompt: str, system_message: str, *, json_mode: bool) -> str:
        messages = [
            {
                "role": "system",
                "content": system_message,
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

        request = {
            "model": self.model,
            "messages": messages,
        }
        if self.reasoning_effort is None:
            request["temperature"] = 0
        else:
            request["reasoning_effort"] = self.reasoning_effort
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        try:
            response = self.client.chat.completions.create(
                **request,
            )
            content = response.choices[0].message.content
        except Exception as exc:
            raise LLMProviderError("The configured LLM provider call failed.") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError(
                "The configured LLM provider returned empty content."
            )
        return content
