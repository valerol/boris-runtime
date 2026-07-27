from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from llm.config import build_lazy_llm_adapter
from semantic_executor import LLMSemanticCalculator, SemanticExecutor


SERVER_LLM_PROVIDER = "SERVER_LLM"
CHATGPT_HOST_PROVIDER = "CHATGPT_HOST_ONLY"


@dataclass(frozen=True)
class SemanticProviderResult:
    """Validated output of one provider-owned semantic calculation."""

    semantic_input: Any
    candidate: Any
    stage_timings_ms: dict[str, float]


class SemanticProvider(ABC):
    """Common identity and trust boundary for semantic providers."""

    provider_id: str
    canonical: bool
    interaction_mode: str


class SynchronousSemanticProvider(SemanticProvider):
    """Provider that returns one candidate inside the current Runtime call."""

    @abstractmethod
    def execute(
        self,
        *,
        surface,
        compatibility,
        source_text: str,
        context=None,
        semantic_input=None,
        operator_decision=None,
    ) -> SemanticProviderResult:
        """Return one immutable ExecutionCandidate or fail closed."""


class ServerLLMProvider(SynchronousSemanticProvider):
    """Canonical synchronous provider owned and invoked by BORIS Runtime."""

    provider_id = SERVER_LLM_PROVIDER
    canonical = True
    interaction_mode = "synchronous"

    def __init__(
        self,
        *,
        compiler_factory,
        llm_adapter_factory=build_lazy_llm_adapter,
        calculator_factory=None,
    ):
        self.llm_adapter_factory = llm_adapter_factory
        self.compiler_factory = compiler_factory
        self.calculator_factory = (
            calculator_factory
            or (lambda adapter: LLMSemanticCalculator(adapter))
        )

    def execute(
        self,
        *,
        surface,
        compatibility,
        source_text: str,
        context=None,
        semantic_input=None,
        operator_decision=None,
    ) -> SemanticProviderResult:
        adapter = self.llm_adapter_factory()
        timings: dict[str, float] = {}

        if semantic_input is None:
            compiler = self.compiler_factory(adapter)
            started = perf_counter()
            semantic_input = compiler.compile(
                surface,
                source_text,
                context=context,
            )
            timings["semantic_input_compile"] = _elapsed_ms(started)

        calculator = self.calculator_factory(adapter)
        executor = SemanticExecutor(
            surface,
            calculator,
            compatibility,
        )
        started = perf_counter()
        candidate = executor.execute(
            semantic_input,
            operator_decision=operator_decision,
        )
        timings["semantic_executor"] = _elapsed_ms(started)
        return SemanticProviderResult(
            semantic_input=semantic_input,
            candidate=candidate,
            stage_timings_ms=timings,
        )


class ChatGPTHostProvider(SemanticProvider):
    """Experimental asynchronous adapter for private signed work orders."""

    provider_id = CHATGPT_HOST_PROVIDER
    canonical = False
    interaction_mode = "signed_work_order"

    def __init__(self, *, prepare_callback, submit_callback):
        self._prepare_callback = prepare_callback
        self._submit_callback = submit_callback

    def prepare(self, *args, **kwargs):
        return self._prepare_callback(*args, **kwargs)

    def submit(self, *args, **kwargs):
        return self._submit_callback(*args, **kwargs)


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
