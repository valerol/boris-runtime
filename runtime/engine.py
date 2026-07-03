from runtime.contracts import runtime_response


class BORISRuntimeEngine:

    def __init__(self, kernel, schema, max_steps=32):
        self.kernel = kernel
        self.schema = schema
        self.max_steps = max_steps
        self.state = schema["entrypoint"]

    def run(self, event):
        self.state = self.schema["entrypoint"]
        current = dict(event)
        current["domain"] = self.kernel.domain.snapshot()

        for _ in range(self.max_steps):
            result = self.step(current)

            if self._is_terminal(result):
                return result

            current = result

        self.state = self.schema["entrypoint"]
        return runtime_response(
            "ERROR",
            answer="Runtime stopped after reaching the step limit.",
            trace={"max_steps": self.max_steps},
            state={"runtime_state": "STEP_LIMIT"}
        )

    def step(self, event):
        if self.state not in self.schema["states"]:
            bad_state = self.state
            self.state = self.schema["entrypoint"]
            return runtime_response(
                "ERROR",
                answer=f"Unknown runtime state: {bad_state}",
                state={"runtime_state": bad_state}
            )

        node = self.schema["states"][self.state]

        t = node["type"]

        # 1. INPUT
        if t == "input":
            self.state = node["next"]
            return event

        # 2. MEMORY READ
        if t == "memory_read":
            event["memory"] = self.kernel.memory.read_recent()
            self.state = node["next"]
            return event

        # 3. SIMA
        if t == "analysis":
            out = self.kernel.sima.analyze(event)
            event["sima"] = out
            self.state = node["next"]
            return event

        # 4. BOIS
        if t == "reasoning":
            out = self.kernel.bois.reason(event["sima"], self.kernel.memory)
            event["bois"] = out
            self.state = node["next"]
            return event

        # 5. GAP DETECTION
        if t == "decision":
            gap = self.kernel.gap.detect(event["bois"])

            if gap:
                self.state = node["next_true"]
            else:
                self.state = node["next_false"]

            return event

        # 6. INTERACTION
        if t == "interaction":
            state = self.state
            self.state = node["next"]
            return runtime_response(
                "CLARIFICATION",
                answer=", ".join(event["bois"].get("required_information", [])),
                trace=self._trace(event),
                state={
                    "runtime_state": state,
                    "domain": self._domain_state(event)
                }
            )

        # 7. TOOL ROUTING (stub)
        if t == "routing":
            event["route"] = "local"
            self.state = node["next"]
            return event

        # 8. EXECUTION (stub)
        if t == "action":
            event["action"] = {"status": "no_external_action_required"}
            self.state = node["next"]
            return event

        # 9. LLM RESPONSE
        if t == "generation":
            event["response"] = self.kernel.llm.generate({
                "input": event.get("input", ""),
                "domain": event.get("domain", {}),
                "sima": event.get("sima", {}),
                "bois": event.get("bois", {}),
                "route": event.get("route"),
                "action": event.get("action")
            })
            self.state = node["next"]
            return event

        # 10. MEMORY WRITE
        if t == "memory_write":
            self.kernel.memory.write(self.state, event)
            self.state = node["next"]
            return event

        # 11. RETURN
        if t == "output":
            state = self.state
            self.state = self.schema["entrypoint"]
            return runtime_response(
                "ANSWER",
                answer=event.get("response", ""),
                trace=self._trace(event),
                state={
                    "runtime_state": state,
                    "domain": self._domain_state(event)
                },
                actions=[event["action"]] if "action" in event else []
            )

        bad_type = t
        self.state = self.schema["entrypoint"]
        return runtime_response(
            "ERROR",
            answer=f"Unsupported runtime node type: {bad_type}",
            state={"runtime_state": self.state}
        )

    @staticmethod
    def _is_terminal(result):
        return isinstance(result, dict) and result.get("type") in {
            "ANSWER",
            "CLARIFICATION",
            "TOOL_REQUEST",
            "ERROR"
        }

    @staticmethod
    def _domain_state(event):
        domain = event.get("domain", {})
        return {
            "name": domain.get("name"),
            "learning_policy": domain.get("learning_policy")
        }

    @staticmethod
    def _trace(event):
        return {
            "session_id": event.get("session_id"),
            "source": event.get("meta", {}).get("source"),
            "domain": event.get("domain", {}),
            "sima": event.get("sima", {}),
            "bois": event.get("bois", {}),
            "route": event.get("route"),
            "action": event.get("action")
        }
