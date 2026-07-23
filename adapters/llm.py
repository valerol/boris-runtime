"""Compatibility names backed by the canonical ``llm`` port."""

from llm.llm_adapter import (
    LLMAdapter as CanonicalLLMAdapter,
    MockLLMAdapter as CanonicalMockLLMAdapter,
    OpenAIAdapter,
)


class LLMAdapter(CanonicalLLMAdapter):
    def complete(self, prompt, context=None):
        return self.call(prompt)


class MockLLMAdapter(CanonicalMockLLMAdapter):
    def complete(self, prompt, context=None):
        return self.call(prompt)


class OpenAIChatAdapter(OpenAIAdapter):
    def complete(self, prompt, context=None):
        return self.call(prompt)
