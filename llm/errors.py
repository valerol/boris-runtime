class LLMError(RuntimeError):
    """Base error for the canonical Runtime LLM port."""


class LLMConfigurationError(LLMError):
    """The configured LLM adapter cannot be constructed."""


class LLMProviderError(LLMError):
    """The external LLM provider call failed or returned no usable content."""
