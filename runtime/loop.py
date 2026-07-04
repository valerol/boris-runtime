from core.protocol import ProtocolResponse


class ProtocolLoop:
    """Compatibility envelope chooser retained for the earlier SDK API."""

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
    """Compatibility shell that delegates Phase 3 execution to ProtocolEngine."""

    def __init__(self, protocol_engine):
        self.protocol_engine = protocol_engine

    def run(self, session, user_input, input_provider=None):
        while True:
            output = self.protocol_engine.run_turn(session, user_input)

            if output["metadata"].get("exit"):
                return output

            if output["type"] in {"QUESTION", "GAP"} and input_provider and session.state.can_clarify():
                clarification = input_provider(output)
                if self.protocol_engine.is_exit(clarification):
                    return {
                        "type": "ANSWER",
                        "content": "Session terminated.",
                        "metadata": {
                            "exit": True,
                            "session_id": session.session_id,
                        },
                    }
                if clarification:
                    self.protocol_engine.record_clarification(session, clarification)
                    user_input = clarification
                    continue

            return output
