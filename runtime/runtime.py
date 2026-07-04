from core.loader import CoreLoader
from llm.llm_adapter import MockLLMAdapter
from prompt.prompt_builder import PromptBuilder
from protocol.boi_parser import BOIParser
from protocol.boris_context import BORISContext
from protocol.sima_analyzer import SIMAAnalyzer
from runtime.executor import DecisionExecutor, ProtocolResponseParser
from runtime.loop import ProtocolRuntimeLoop
from runtime.state import RuntimeState


class BOISRuntime:
    """Phase 1 CLI MVP runtime composition root."""

    def __init__(
        self,
        core_loader=None,
        bois_parser=None,
        sima_analyzer=None,
        boris_context=None,
        prompt_builder=None,
        llm_adapter=None,
        response_parser=None,
        decision_executor=None,
    ):
        self.loop = ProtocolRuntimeLoop(
            core_loader=core_loader or CoreLoader(),
            bois_parser=bois_parser or BOIParser(),
            sima_analyzer=sima_analyzer or SIMAAnalyzer(),
            boris_context=boris_context or BORISContext(),
            prompt_builder=prompt_builder or PromptBuilder(),
            llm_adapter=llm_adapter or MockLLMAdapter(),
            response_parser=response_parser or ProtocolResponseParser(),
            decision_executor=decision_executor or DecisionExecutor(),
        )

    def run(self, user_input, input_provider=None):
        state = RuntimeState(current_input=(user_input or "").strip())
        output = self.loop.run(state, input_provider=input_provider)
        return output.to_dict()

