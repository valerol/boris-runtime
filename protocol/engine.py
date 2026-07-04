from prompt.prompt_builder import PromptBuilder
from protocol.bois_frame import BOISFrameBuilder
from protocol.boris_context import BORISContext
from protocol.decision import DecisionEngine
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
        decision_engine=None,
    ):
        self.sima_signals = sima_signals or SIMASignalExtractor()
        self.bois_frame = bois_frame or BOISFrameBuilder()
        self.boris_context = boris_context or BORISContext()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.llm_adapter = llm_adapter
        self.parser = parser or ProtocolResponseParser()
        self.validator = validator or ProtocolOutputValidator()
        self.decision_engine = decision_engine or DecisionEngine()

    def run_turn(self, session, user_input):
        session.state.current_input = self._combined_input(session, user_input)
        signals = self.sima_signals.extract(session.state.current_input, session.state)
        frame = self.bois_frame.build(session.core, session.state.current_input)
        boris = self.boris_context.build(session.core, session.state)

        parsed = ProtocolOutput("GAP", "LLM adapter is not configured.", {})
        if not signals["missing_fields"] and self.llm_adapter:
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

        try:
            self.validator.validate(parsed)
        except ProtocolValidationError as exc:
            parsed = ProtocolOutput(
                "GAP",
                "Parsed output failed protocol validation.",
                {"validation_error": str(exc)},
            )

        decision = self.decision_engine.decide(session, signals, frame, boris, parsed)
        self.validator.validate(decision)
        return decision.to_dict()

    @staticmethod
    def record_clarification(session, clarification):
        DecisionEngine.record_clarification(session, clarification)
        session.state.last_output_type = "CLARIFIED"

    @staticmethod
    def _combined_input(session, user_input):
        text = (user_input or "").strip()
        if session.state.last_output_type == "CLARIFIED":
            return session.state.current_input
        if session.state.current_input and session.state.last_output_type == "QUESTION":
            return f"{session.state.current_input}\nClarification: {text}"
        return text
