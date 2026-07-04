from core.protocol import ProtocolResponse
from runtime.state import ProtocolOutput


class ProtocolLoop:
    """Chooses the protocol envelope after parsing an LLM response."""

    def decide(self, parsed):
        if parsed.kind == "clarification":
            return ProtocolResponse("clarification", parsed.content)

        if parsed.kind == "tool":
            return ProtocolResponse(
                "tool_call",
                "",
                tool_request={
                    "name": parsed.tool_name,
                    "arguments": dict(parsed.tool_args),
                },
            )

        return ProtocolResponse("final", parsed.content)


class ProtocolRuntimeLoop:
    """Explicit Phase 1 INPUT -> PROTOCOL -> PROMPT -> LLM -> PARSER loop."""

    def __init__(
        self,
        core_loader,
        bois_parser,
        sima_analyzer,
        boris_context,
        prompt_builder,
        llm_adapter,
        response_parser,
        decision_executor,
    ):
        self.core_loader = core_loader
        self.bois_parser = bois_parser
        self.sima_analyzer = sima_analyzer
        self.boris_context = boris_context
        self.prompt_builder = prompt_builder
        self.llm_adapter = llm_adapter
        self.response_parser = response_parser
        self.decision_executor = decision_executor

    def run(self, state, input_provider=None):
        while True:
            definitions = self.core_loader.load()

            bois_context = self.bois_parser.parse(definitions)
            sima_analysis = self.sima_analyzer.analyze(state.current_input, state)
            sima_analysis["definition"] = definitions.sima
            sima_analysis["prompt_rule"] = "Use SIMA as analytical risk and uncertainty structure."
            boris_context = self.boris_context.build(definitions, state)

            if sima_analysis["missing_fields"]:
                gap_output = self._handle_gap(state, sima_analysis)
                if input_provider and state.can_clarify():
                    clarification = input_provider(gap_output.to_dict())
                    if clarification:
                        state.record_clarification(clarification)
                        continue
                state.last_output_type = "GAP"
                return gap_output

            prompt = self.prompt_builder.build(
                bois_context,
                sima_analysis,
                boris_context,
                state.current_input,
                state,
            )
            raw_llm_output = self.llm_adapter.call(prompt)
            parsed_output = self.response_parser.parse(raw_llm_output)
            decision = self.decision_executor.evaluate(parsed_output)

            if decision.type == "QUESTION" and input_provider and state.can_clarify():
                clarification = input_provider(decision.to_dict())
                if clarification:
                    state.record_clarification(clarification)
                    continue

            state.last_output_type = decision.type
            return decision

    @staticmethod
    def _handle_gap(state, sima_analysis):
        question = sima_analysis["question"]
        missing_fields = sima_analysis["missing_fields"]
        state.register_gap(missing_fields, question)

        for field_name in missing_fields:
            state.remember_question(field_name, question)

        return ProtocolOutput(
            "GAP",
            question,
            {
                "risk": sima_analysis["risk"],
                "missing_fields": list(missing_fields),
                "gap_registry": dict(state.gap_registry),
                "clarification_cycles": state.clarification_cycles,
                "max_clarification_cycles": state.max_clarification_cycles,
            },
        )
