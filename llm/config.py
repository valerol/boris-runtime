import os
from pathlib import Path

from application.runtime_mode import developer_mode_enabled
from llm.errors import LLMConfigurationError
from llm.llm_adapter import MockLLMAdapter, OpenAIAdapter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILES = (".env", ".env.local")


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

    def call_structured(self, prompt, system_message):
        if self._adapter is None:
            self._adapter = self._factory()
        return self._adapter.call_structured(prompt, system_message)


def load_env_file(path=None):
    env_paths = (
        (Path(path),)
        if path
        else tuple(PROJECT_ROOT / name for name in DEFAULT_ENV_FILES)
    )
    protected_keys = set(os.environ)

    for env_path in env_paths:
        _load_env_path(env_path, protected_keys)


def _load_env_path(env_path, protected_keys):
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

        if key and key not in protected_keys:
            os.environ[key] = value


def prompt_debug_enabled():
    return developer_mode_enabled()


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
