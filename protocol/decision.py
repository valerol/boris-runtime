from protocol.question_memory import QuestionMemory
from runtime.state import ProtocolOutput


class PostLLMController:
    """Post-LLM protocol controller. It never decides whether to call LLM."""

    def control(self, session, sima_signals, bois_frame, boris_context, parsed_output):
        output = parsed_output
        missing_fields = self._merge_missing_fields(
            output.metadata.get("missing_fields"),
            sima_signals["missing_fields"],
        )
        metadata = {
            **output.metadata,
            "risk": sima_signals["risk"],
            "uncertainty": sima_signals["uncertainty"],
            "missing_fields": missing_fields,
            "clarification_cycles": session.state.clarification_cycles,
            "max_clarification_cycles": session.state.max_clarification_cycles,
            "core_version": output.metadata.get("core_version", session.core["meta"]["version"]),
            "session_id": session.session_id,
            "bois_frame": {"framework": bois_frame.get("framework")},
            "boris_context": {"role": boris_context.get("role")},
        }

        if output.type in {"QUESTION", "GAP"}:
            controlled = self._control_loop_output(session, output, metadata)
        else:
            controlled = ProtocolOutput(output.type, output.content, metadata)

        session.state.last_output_type = controlled.type
        session.state.last_decision = controlled.to_dict()
        return controlled

    @staticmethod
    def record_clarification(session, clarification):
        session.state.record_clarification(clarification)

    def _control_loop_output(self, session, output, metadata):
        memory = QuestionMemory(session.state)
        question = output.content
        gap_key = self._gap_key(output)

        if output.type == "QUESTION":
            if memory.has_asked(question):
                previous = self._previous_question(session, question)
                return ProtocolOutput(
                    "GAP",
                    "Repeated clarification question rejected by protocol controller.",
                    {
                        **metadata,
                        "repeated_question": True,
                        "repeated_after_clarification": session.state.clarification_cycles > 0,
                        "previous_question": previous.get("question", ""),
                        "gap_key": gap_key,
                    },
                )

            if not session.state.can_clarify():
                return ProtocolOutput(
                    "GAP",
                    "Clarification limit reached.",
                    {
                        **metadata,
                        "clarification_limit_reached": True,
                        "gap_key": gap_key,
                    },
                )

            memory.remember(question, gap_key)

        if output.type == "GAP":
            session.state.gap_registry[gap_key] = {
                "question": question,
                "resolved": False,
            }

        return ProtocolOutput(
            output.type,
            output.content,
            {
                **metadata,
                "gap_key": gap_key,
            },
        )

    @staticmethod
    def _gap_key(output):
        return str(output.metadata.get("gap_key") or output.content or "gap")

    @staticmethod
    def _previous_question(session, question):
        for item in reversed(session.state.asked_questions):
            if item.get("question") == question:
                return item
        return session.state.asked_questions[-1] if session.state.asked_questions else {}

    @staticmethod
    def _merge_missing_fields(*field_lists):
        merged = []
        seen = set()
        for fields in field_lists:
            if not isinstance(fields, list):
                continue
            for field in fields:
                value = str(field).strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                merged.append(value)
        return merged


DecisionEngine = PostLLMController
