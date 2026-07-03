from runtime.contracts import runtime_response
from kernel.self_introspection import explain_system
from kernel.semantic import llm_semantic_interpretation_with


PHASE_INPUT = "INPUT"
PHASE_ANALYZE = "ANALYZE"
PHASE_DECIDE = "DECIDE"
PHASE_FINALIZE = "FINALIZE"


class BORISRuntimeEngine:
    """Schema-driven state machine engine."""

    def __init__(self, kernel, schema, max_steps=32, epistemic_hierarchy=None):
        self.kernel = kernel
        self.schema = schema
        self.max_steps = max_steps
        self.epistemic_hierarchy = epistemic_hierarchy or {}
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
            event["phase"] = PHASE_INPUT
            self.state = node["next"]
            return event

        # 2. MEMORY READ
        if t == "memory_read":
            event["memory"] = self.kernel.memory.read_recent()
            self.kernel.memory.remember_input(
                event.get("session_id", "default"),
                event.get("input", "")
            )
            self.state = node["next"]
            return event

        # 3. LLM SEMANTIC INTERPRETATION
        if t == "semantic_interpretation":
            event["semantic_interpretation"] = llm_semantic_interpretation_with(
                self.kernel.llm,
                event.get("input", "")
            )
            self.state = node["next"]
            return event

        # 4. BOIS
        if t == "reasoning":
            out = self.kernel.bois.reason(event, self.kernel.memory)
            event["bois"] = out
            self.state = node["next"]
            return event

        # 5. SIMA
        if t == "analysis":
            event["phase"] = PHASE_ANALYZE
            out = self.kernel.sima.analyze(event)
            event["sima"] = out
            self.state = node["next"]
            return event

        # 6. GAP DETECTION
        if t == "decision":
            event["phase"] = PHASE_DECIDE
            decision = self.decision_gate(event)

            if self._is_terminal(decision):
                self.state = self.schema["entrypoint"]
                return decision

            self.state = node["next"]
            return event

        # 7. INTERACTION
        if t == "interaction":
            self.state = self.schema["entrypoint"]
            return runtime_response(
                "ERROR",
                answer="Interaction state is disabled; decisions must pass through decision_gate.",
                trace=self._trace(event),
                state={
                    "runtime_state": "INTERACTION_DISABLED",
                    "domain": self._domain_state(event)
                }
            )

        # 8. TOOL ROUTING (stub)
        if t == "routing":
            event["route"] = "local"
            self.state = node["next"]
            return event

        # 9. EXECUTION (stub)
        if t == "action":
            event["action"] = {"status": "no_external_action_required"}
            self.state = node["next"]
            return event

        # 10. LLM RESPONSE
        if t == "generation":
            event["phase"] = PHASE_FINALIZE
            gate = event.get("decision_gate", {})

            if gate.get("type") != "ANSWER":
                return runtime_response(
                    "ERROR",
                    answer="Runtime reached generation without an ANSWER decision.",
                    trace=self._trace(event),
                    state={"runtime_state": "DECISION_GATE_REQUIRED"}
                )

            if gate.get("answer"):
                event["response"] = gate["answer"]
            elif gate.get("llm_allowed", False):
                event["response"] = self.kernel.llm.generate({
                    "input": event.get("input", ""),
                    "semantic_interpretation": event.get("semantic_interpretation", {}),
                    "domain": event.get("domain", {}),
                    "sima": event.get("sima", {}),
                    "bois": event.get("bois", {}),
                    "route": event.get("route"),
                    "action": event.get("action")
                })
            else:
                event["response"] = self._llm_fallback_answer()
            self.state = node["next"]
            return event

        # 11. MEMORY WRITE
        if t == "memory_write":
            self.kernel.memory.write(self.state, event)
            self.state = node["next"]
            return event

        # 12. RETURN
        if t == "output":
            gate = event.get("decision_gate", {})

            if gate.get("type") != "ANSWER":
                self.state = self.schema["entrypoint"]
                return runtime_response(
                    "ERROR",
                    answer="Runtime reached output without an ANSWER decision.",
                    trace=self._trace(event),
                    state={"runtime_state": "DECISION_GATE_REQUIRED"}
                )

            state = self.state
            self.state = self.schema["entrypoint"]
            return runtime_response(
                "ANSWER",
                answer=event.get("response", ""),
                trace=self._trace(event),
                state={
                    "runtime_state": state,
                    "phase": event.get("phase"),
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

    def decision_gate(self, event):
        event["epistemic"] = {
            "priority_order": self.epistemic_hierarchy["priority_order"],
            "decisions": []
        }

        self_description = self._self_description_response(event)

        if self_description:
            return self_description

        for source in self.epistemic_hierarchy["priority_order"]:
            decision = self._apply_epistemic_source(source, event)
            event["epistemic"]["decisions"].append(decision)

            if decision["decision"] == "CLARIFICATION":
                return self._clarification_response(event, decision)

            if decision["decision"] == "ANSWER":
                event["decision_gate"] = {
                    "type": "ANSWER",
                    "answer": decision.get("answer", ""),
                    "source": decision["source"],
                    "llm_allowed": False
                }
                return {"type": "CONTINUE"}

        event["decision_gate"] = {
            "type": "ANSWER",
            "answer": "",
            "source": "DECISION_GATE",
            "llm_allowed": event.get("llm_allowed", False)
        }
        return {"type": "CONTINUE"}

    def _apply_epistemic_source(self, source, event):
        handlers = {
            "DOMAIN": self._apply_domain_source,
            "MEMORY": self._apply_memory_source,
            "RUNTIME_STATE": self._apply_runtime_state_source,
            "LLM": self._apply_llm_source
        }
        handler = handlers[source]
        return handler(event)

    def _apply_domain_source(self, event):
        user_input = event.get("input", "").strip()

        if not user_input:
            rule = self.epistemic_hierarchy["rules"]["DOMAIN"]["empty_input"]
            return {
                "source": "DOMAIN",
                "decision": rule["decision"],
                "answer": rule["answer"],
                "reason": "empty_input"
            }

        return {"source": "DOMAIN", "decision": "CONTINUE"}

    def _apply_memory_source(self, event):
        question = self._clarification_answer(event)
        session_id = event.get("session_id", "default")
        topic = self._topic(event)
        limit = self.epistemic_hierarchy["question_memory"][
            "max_clarifications_per_session_topic"
        ]
        count = self.kernel.memory.clarification_count(session_id, topic)
        duplicate = self.kernel.memory.has_asked_clarification(
            session_id,
            topic,
            question
        )

        if duplicate or count >= limit:
            rule = self.epistemic_hierarchy["rules"]["MEMORY"]["duplicate_clarification"]
            return {
                "source": "MEMORY",
                "decision": rule["decision"],
                "answer": rule["answer"],
                "reason": "duplicate_or_limit",
                "clarification_count": count,
                "max_clarifications": limit
            }

        return {
            "source": "MEMORY",
            "decision": "CONTINUE",
            "clarification_count": count,
            "max_clarifications": limit
        }

    def _apply_runtime_state_source(self, event):
        uncertainty = event.get("sima", {}).get("uncertainty", 0)
        threshold = self.epistemic_hierarchy["thresholds"][
            "sima_uncertainty_clarification"
        ]
        required_information = event.get("bois", {}).get("required_information", [])

        if uncertainty > threshold and required_information:
            rule = self.epistemic_hierarchy["rules"]["RUNTIME_STATE"]["uncertainty_gap"]
            return {
                "source": "RUNTIME_STATE",
                "decision": rule["decision"],
                "answer": rule["answer_template"].format(
                    input=event.get("input", "").strip()
                ),
                "reason": required_information,
                "uncertainty": uncertainty,
                "threshold": threshold
            }

        return {
            "source": "RUNTIME_STATE",
            "decision": "CONTINUE",
            "uncertainty": uncertainty,
            "threshold": threshold
        }

    def _apply_llm_source(self, event):
        uncertainty = event.get("sima", {}).get("uncertainty", 0)
        threshold = self.epistemic_hierarchy["thresholds"]["llm_uncertainty_threshold"]
        event["llm_allowed"] = uncertainty > threshold

        return {
            "source": "LLM",
            "decision": "FORMAT_ONLY",
            "llm_allowed": event["llm_allowed"],
            "uncertainty": uncertainty,
            "threshold": threshold
        }

    def _clarification_response(self, event, decision):
        session_id = event.get("session_id", "default")
        topic = self._topic(event)
        self.kernel.memory.remember_clarification(
            session_id,
            topic,
            decision["answer"]
        )
        return runtime_response(
            "CLARIFICATION",
            answer=decision["answer"],
            trace={
                **self._trace(event),
                "clarification_reason": decision.get("reason"),
                "epistemic": event.get("epistemic", {})
            },
            state={
                "runtime_state": "GAP_DETECTION",
                "phase": PHASE_DECIDE,
                "clarification_reason": decision.get("reason"),
                "domain": self._domain_state(event)
            }
        )

    @staticmethod
    def _is_terminal(result):
        return isinstance(result, dict) and result.get("type") in {
            "ANSWER",
            "CLARIFICATION",
            "SELF_DESCRIPTION",
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
            "phase": event.get("phase"),
            "domain": event.get("domain", {}),
            "semantic_interpretation": event.get("semantic_interpretation", {}),
            "sima": event.get("sima", {}),
            "bois": event.get("bois", {}),
            "route": event.get("route"),
            "action": event.get("action"),
            "epistemic": event.get("epistemic", {}),
            "llm_allowed": event.get("llm_allowed")
        }

    @staticmethod
    def _clarification_answer(event):
        user_input = event.get("input", "").strip()

        if user_input:
            return f'Please clarify what you want me to do with: "{user_input}".'

        return "Please clarify what you want to do."

    def _llm_fallback_answer(self):
        return self.epistemic_hierarchy["rules"]["LLM"]["fallback_answer"]

    @staticmethod
    def _topic(event):
        return event.get("input", "").strip().lower()

    def _self_description_response(self, event):
        if not self._semantic_indicates_self_description(event):
            return None

        if self._domain_allows_introspection(event):
            result = explain_system(
                event.get("input", ""),
                self.kernel.domain,
                memory=self.kernel.memory
            )
            result["trace"]["epistemic"] = event.get("epistemic", {})
            result["trace"]["semantic_interpretation"] = event.get(
                "semantic_interpretation",
                {}
            )
            return result

        return runtime_response(
            "CLARIFICATION",
            answer="Please clarify what system information you want.",
            trace={
                **self._trace(event),
                "epistemic": event.get("epistemic", {}),
                "clarification_reason": "domain_disallows_introspection"
            },
            state={
                "runtime_state": "GAP_DETECTION",
                "phase": PHASE_DECIDE,
                "clarification_reason": "domain_disallows_introspection",
                "domain": self._domain_state(event)
            }
        )

    @staticmethod
    def _domain_allows_introspection(event):
        domain = event.get("domain", {})
        capabilities = domain.get("capabilities", [])
        return (
            "self-introspection" in capabilities
            or "runtime state machine execution" in capabilities
            or "text reasoning" in capabilities
        )

    @staticmethod
    def _semantic_indicates_self_description(event):
        semantic = event.get("semantic_interpretation", {})
        if not isinstance(semantic, dict):
            return False

        text = " ".join([
            semantic.get("semantic_summary", ""),
            semantic.get("user_intent_hypothesis", "")
        ]).lower()
        return (
            "boris runtime itself" in text
            or "about the system" in text
            or "system information" in text
            or "capabilities" in text
            or "limitations" in text
        )
