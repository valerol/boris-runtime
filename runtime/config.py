import os
from pathlib import Path

from llm.llm_adapter import MockLLMAdapter, OpenAIAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LLMConfigurationError(RuntimeError):
    """Raised when the configured external LLM adapter cannot be created."""


class LazyLLMAdapter:
    """Thread-confined lazy adapter; construction happens only on first call()."""

    def __init__(self, factory):
        self._factory = factory
        self._adapter = None

    @property
    def adapter_name(self):
        if self._adapter is not None:
            return getattr(self._adapter, "adapter_name", "mock")

        mode = os.getenv("BOIS_LLM", "").strip().lower()
        return mode or "mock"

    def call(self, prompt):
        if self._adapter is None:
            self._adapter = self._factory()
        return self._adapter.call(prompt)


def load_env_file(path=None):
    env_path = Path(path) if path else PROJECT_ROOT / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def prompt_debug_enabled():
    return (
        os.getenv("BORIS_RUNTIME_MODE", "").strip().lower() == "dev"
        or os.getenv("BOIS_DEBUG_PROMPT", "").strip().lower() == "true"
    )


def build_llm_adapter():
    mode = os.getenv("BOIS_LLM", "").strip().lower()

    if mode == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMConfigurationError("BOIS_LLM=openai requires OPENAI_API_KEY")
        return OpenAIAdapter(debug_prompt_enabled=prompt_debug_enabled())

    if mode in {"", "mock"}:
        return MockLLMAdapter(debug_prompt_enabled=prompt_debug_enabled())

    raise LLMConfigurationError(f"Unsupported BOIS_LLM mode: {mode}")


def build_lazy_llm_adapter():
    return LazyLLMAdapter(build_llm_adapter)


def build_validator_llm_adapter():
    mode = os.getenv("BORIS_VALIDATOR_LLM", os.getenv("BOIS_LLM", "")).strip().lower()

    if mode == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMConfigurationError("BORIS_VALIDATOR_LLM=openai requires OPENAI_API_KEY")
        model = os.getenv("BORIS_VALIDATOR_MODEL") or os.getenv("OPENAI_MODEL")
        return OpenAIAdapter(model=model, debug_prompt_enabled=prompt_debug_enabled())

    if mode in {"", "mock"}:
        return MockLLMAdapter(debug_prompt_enabled=prompt_debug_enabled())

    raise LLMConfigurationError(f"Unsupported BORIS_VALIDATOR_LLM mode: {mode}")


def build_lazy_validator_llm_adapter():
    return LazyLLMAdapter(build_validator_llm_adapter)
