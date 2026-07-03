import os


class LLMAdapter:
    def complete(self, prompt, context=None):
        raise NotImplementedError


class MockLLMAdapter(LLMAdapter):
    """Deterministic local adapter for CLI validation and tests."""

    def complete(self, prompt, context=None):
        user_input = prompt.rsplit("User input:", 1)[-1].strip()
        lowered = user_input.lower()

        if "clarify" in lowered or "?" == user_input:
            return "CLARIFY: What specific outcome do you want?"

        if lowered.startswith("tool "):
            return 'TOOL: echo {"text": "%s"}' % user_input[5:].replace('"', "'")

        return f"FINAL: Protocol response for: {user_input}"


class OpenAIChatAdapter(LLMAdapter):
    """Optional OpenAI adapter; external dependency is loaded only when used."""

    def __init__(self, model=None, api_key=None):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def complete(self, prompt, context=None):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return only the middleware response contract."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return response.choices[0].message.content or ""

