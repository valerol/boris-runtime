from runtime.state import ProtocolOutput
from protocol.question_memory import QuestionMemory


class DecisionEngine:
    def decide(self, session, sima_signals, bois_frame, boris_context, parsed_output):
        state = session.state
        question_memory = QuestionMemory(state)
        missing_fields = sima_signals["missing_fields"]

        if missing_fields:
            question = self._clarification_question(sima_signals)
            gap_key = ",".join(missing_fields)
            self._register_gap(state, gap_key, question, sima_signals)

            if state.can_clarify() and not question_memory.has_asked(question):
                question_memory.remember(question, gap_key)
                return self._output(
                    session,
                    "QUESTION",
                    question,
                    sima_signals,
                    {"gap_key": gap_key, "decision_reason": "clarification_available"},
                )

            if state.can_clarify():
                return self._output(
                    session,
                    "ANSWER",
                    "I do not have the missing context, so I will answer with explicit uncertainty.",
                    sima_signals,
                    {"gap_key": gap_key, "decision_reason": "repeated_question_prevented"},
                )

            return self._output(
                session,
                "GAP",
                "Clarification limit reached before the missing information was resolved.",
                sima_signals,
                {"gap_key": gap_key, "decision_reason": "clarification_limit_reached"},
            )

        output = parsed_output
        metadata = {
            **output.metadata,
            "bois_frame": {"framework": bois_frame.get("framework")},
            "boris_context": {"role": boris_context.get("role")},
        }
        return self._output(session, output.type, output.content, sima_signals, metadata)

    @staticmethod
    def record_clarification(session, clarification):
        session.state.record_clarification(clarification)

    @staticmethod
    def _register_gap(state, gap_key, question, sima_signals):
        state.gap_registry[gap_key] = {
            "question": question,
            "missing_fields": list(sima_signals["missing_fields"]),
            "resolved": False,
        }

    @staticmethod
    def _clarification_question(sima_signals):
        if "observable_context" in sima_signals["missing_fields"]:
            return "I cannot determine that without visual context. Please provide an image or describe the pants."
        if "request" in sima_signals["missing_fields"]:
            return "What request should the middleware process?"
        return "Please provide the missing information."

    def _output(self, session, output_type, content, sima_signals, metadata):
        merged_metadata = {
            "risk": sima_signals["risk"],
            "uncertainty": sima_signals["uncertainty"],
            "missing_fields": list(sima_signals["missing_fields"]),
            "clarification_cycles": session.state.clarification_cycles,
            "max_clarification_cycles": session.state.max_clarification_cycles,
            "core_version": session.core["meta"]["version"],
            "session_id": session.session_id,
            **metadata,
        }
        session.state.last_output_type = output_type
        session.state.last_decision = {
            "type": output_type,
            "content": content,
            "metadata": merged_metadata,
        }
        return ProtocolOutput(output_type, content, merged_metadata)
