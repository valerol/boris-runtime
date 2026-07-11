from dataclasses import dataclass

from llm.llm_adapter import MockLLMAdapter
from prompt.prompt_builder import PromptBuilder
from protocol.bois_frame import BOISFrameBuilder
from protocol.boris_context import BORISContext
from protocol.decision import PostLLMController
from protocol.normalization import (
    is_clarification_request_content,
    normalize_protocol_output_type,
)
from protocol.sima_signals import SIMASignalExtractor
from protocol.validator import ProtocolOutputValidator, ProtocolValidationError
from runtime.executor import ProtocolResponseParser
from runtime.state import ProtocolOutput


@dataclass(frozen=True)
class ProtocolFrameContext:
    user_input: str
    sima: dict
    bois_frame: dict
    boris_context: dict
    core_context: dict


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

        frame_context = self.build_frame_context(session, text, mutate_state=True)

        prompt = self.prompt_builder.build(
            session.core,
            frame_context.sima,
            frame_context.bois_frame,
            frame_context.boris_context,
            frame_context.user_input,
            session.state,
            core_context=frame_context.core_context,
        )
        prompt_context = getattr(self.prompt_builder, "last_context", {})
        core_metadata = dict(prompt_context.get("core", {}))
        raw_output = self.llm_adapter.call(prompt)
        parsed = self.parser.parse(raw_output)
        parsed.metadata = {
            **parsed.metadata,
            "llm_called": True,
            "llm_adapter": self.adapter_name,
            **core_metadata,
        }
        parsed = normalize_protocol_output_type(parsed)

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
                    **core_metadata,
                },
            )

        decision = self.controller.control(
            session,
            frame_context.sima,
            frame_context.bois_frame,
            frame_context.boris_context,
            parsed,
        )
        self.validator.validate(decision)
        output = decision.to_dict()
        session.state.processed_inputs[text] = output
        return output

    def build_frame_context(self, session, user_input, mutate_state=False):
        text = (user_input or "").strip()
        effective_input = self._effective_input(session, text, mutate_state=mutate_state)
        signals = self.sima_signals.extract(effective_input, session.state)
        frame = self.bois_frame.build(session.core, effective_input)
        boris = self.boris_context.build(session.core, session.state)
        core_context = self.prompt_builder._build_core_context(session.core, effective_input)
        return ProtocolFrameContext(
            user_input=effective_input,
            sima=signals,
            bois_frame=frame,
            boris_context=boris,
            core_context=core_context,
        )

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

    @staticmethod
    def _previous_answer_requested_clarification(session):
        last_decision = session.state.last_decision or {}
        if last_decision.get("type") != "ANSWER":
            return False
        if session.state.last_output_type in {"QUESTION", "CLARIFIED"}:
            return False
        return is_clarification_request_content(
            last_decision.get("content", ""),
            last_decision.get("metadata", {}),
        )

    def _effective_input(self, session, user_input, mutate_state=False):
        text = (user_input or "").strip()
        if self._previous_answer_requested_clarification(session):
            if mutate_state:
                session.state.record_clarification(text)
                session.state.last_output_type = "CLARIFIED"
                return session.state.current_input
            return f"{session.state.current_input}\nClarification: {text}".strip()

        effective_input = self._combined_input(session, text)
        if mutate_state:
            session.state.current_input = effective_input
        return effective_input
