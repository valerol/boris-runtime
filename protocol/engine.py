from llm.llm_adapter import MockLLMAdapter
from prompt.prompt_builder import PromptBuilder
from protocol.bois_frame import BOISFrameBuilder
from protocol.boris_context import BORISContext
from protocol.decision import PostLLMController
from protocol.sima_signals import SIMASignalExtractor
from protocol.validator import ProtocolOutputValidator, ProtocolValidationError
from runtime.executor import ProtocolResponseParser
from runtime.state import ProtocolOutput


class ProtocolEngine:
    def __init__(
        self,
        sima_signals=None,
        bois_frame=None,
        boris_context=None,
        prompt_builder=None,
        llm_adapter=None,
        parser=None,
        validator=None,
        controller=None,
    ):
        self.sima_signals = sima_signals or SIMASignalExtractor()
        self.bois_frame = bois_frame or BOISFrameBuilder()
        self.boris_context = boris_context or BORISContext()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_adapter = llm_adapter or MockLLMAdapter()
        self.parser = parser or ProtocolResponseParser()
        self.validator = validator or ProtocolOutputValidator()
        self.controller = controller or PostLLMController()

    def run_turn(self, session, user_input):
        text = (user_input or "").strip()
        if self.is_exit(text):
            return ProtocolOutput(
                "ANSWER",
                "Session terminated.",
                {
                    "exit": True,
                    "llm_called": False,
                    "llm_adapter": self.adapter_name,
                    "session_id": session.session_id,
                },
            ).to_dict()

        cached = session.state.processed_inputs.get(text)
        if cached:
            return {
                "type": cached["type"],
                "content": cached["content"],
                "metadata": {
                    **cached["metadata"],
                    "llm_called": False,
                    "llm_adapter": self.adapter_name,
                    "duplicate": True,
                },
            }

        session.state.current_input = self._combined_input(session, text)
        signals = self.sima_signals.extract(session.state.current_input, session.state)
        frame = self.bois_frame.build(session.core, session.state.current_input)
        boris = self.boris_context.build(session.core, session.state)

        prompt = self.prompt_builder.build(
            session.core,
            signals,
            frame,
            boris,
            session.state.current_input,
            session.state,
        )
        raw_output = self.llm_adapter.call(prompt)
        parsed = self.parser.parse(raw_output)
        parsed.metadata = {
            **parsed.metadata,
            "llm_called": True,
            "llm_adapter": self.adapter_name,
        }

        try:
            self.validator.validate(parsed)
        except ProtocolValidationError as exc:
            parsed = ProtocolOutput(
                "GAP",
                "Parsed output failed protocol validation.",
                {
                    "validation_error": str(exc),
                    "llm_called": True,
                    "llm_adapter": self.adapter_name,
                },
            )

        decision = self.controller.control(session, signals, frame, boris, parsed)
        self.validator.validate(decision)
        output = decision.to_dict()
        session.state.processed_inputs[text] = output
        return output

    @staticmethod
    def record_clarification(session, clarification):
        PostLLMController.record_clarification(session, clarification)
        session.state.last_output_type = "CLARIFIED"

    @staticmethod
    def is_exit(user_input):
        return (user_input or "").strip().lower() in {"exit", "quit", "/exit", "/quit"}

    @property
    def adapter_name(self):
        return getattr(self.llm_adapter, "adapter_name", "mock")

    @staticmethod
    def _combined_input(session, user_input):
        text = (user_input or "").strip()
        if session.state.last_output_type == "CLARIFIED":
            return session.state.current_input
        if session.state.current_input and session.state.last_output_type == "QUESTION":
            return f"{session.state.current_input}\nClarification: {text}"
        return text
