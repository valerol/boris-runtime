from llm.llm_adapter import MockLLMAdapter
from protocol.engine import ProtocolEngine
from runtime.context_packet import build_context_packet
from runtime.loop import ProtocolRuntimeLoop
from runtime.session import create_runtime_session


class BOISRuntime:
    """Runtime composition root using Phase 2 core and Phase 3 engine."""

    def __init__(
        self,
        core_ref="core/definitions",
        session_id=None,
        llm_adapter=None,
    ):
        self.session = create_runtime_session(core_ref, session_id=session_id)
        self.engine = ProtocolEngine(llm_adapter=llm_adapter or MockLLMAdapter())
        self.loop = ProtocolRuntimeLoop(
            protocol_engine=self.engine,
        )

    def run(self, user_input, input_provider=None):
        return self.loop.run(self.session, user_input, input_provider=input_provider)

    def frame(self, user_input):
        frame_context = self.engine.build_frame_context(
            self.session,
            user_input,
            mutate_state=False,
        )
        return build_context_packet(self.session, frame_context)
