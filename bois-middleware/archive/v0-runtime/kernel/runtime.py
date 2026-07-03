"""
Kernel composition root.

This module wires BOIS, SIMA, GAP, Memory, LLM, Domain, and the runtime engine.
The state machine itself lives in runtime/engine.py.
"""

from kernel.sima import SIMA
from kernel.bois import BOIS
from kernel.memory import Memory
from kernel.llm import LLM
from kernel.gap import GapDetector
from kernel.self_introspection import explain_system, is_introspection_query
from core.loader import EpistemicHierarchyLoader, SchemaLoader
from physiology.domain import DEFAULT_DOMAIN
from runtime.contracts import runtime_response
from runtime.engine import BORISRuntimeEngine


def decision_gate(input, sima, bois, memory, domain, epistemic_rules):
    event = input if isinstance(input, dict) else {"input": input}
    user_input = event.get("input", "").strip()
    session_id = event.get("session_id", "default")
    domain_snapshot = domain.snapshot()
    epistemic = {
        "priority_order": epistemic_rules["priority_order"],
        "decisions": []
    }

    if is_introspection_query(user_input):
        result = explain_system(user_input, domain, memory=memory)
        result["trace"]["epistemic"] = epistemic
        return result

    for source in epistemic_rules["priority_order"]:
        decision = _apply_gate_source(
            source,
            user_input,
            session_id,
            sima,
            bois,
            memory,
            epistemic_rules
        )
        epistemic["decisions"].append(decision)

        if decision["decision"] == "CLARIFICATION":
            memory.remember_clarification(
                session_id,
                _topic(user_input),
                decision["answer"]
            )
            return runtime_response(
                "CLARIFICATION",
                answer=decision["answer"],
                trace={
                    "session_id": session_id,
                    "source": event.get("meta", {}).get("source"),
                    "phase": "DECIDE",
                    "domain": domain_snapshot,
                    "sima": sima,
                    "bois": bois,
                    "epistemic": epistemic,
                    "llm_allowed": False,
                    "clarification_reason": decision.get("reason")
                },
                state={
                    "runtime_state": "GAP_DETECTION",
                    "phase": "DECIDE",
                    "clarification_reason": decision.get("reason"),
                    "domain": _domain_state(domain_snapshot)
                }
            )

        if decision["decision"] == "ANSWER":
            llm_allowed = decision.get("llm_allowed", False)
            return _answer_response(
                event,
                sima,
                bois,
                domain_snapshot,
                epistemic,
                decision,
                llm_allowed=llm_allowed
            )

    llm_decision = epistemic["decisions"][-1]
    return _answer_response(
        event,
        sima,
        bois,
        domain_snapshot,
        epistemic,
        llm_decision,
        llm_allowed=llm_decision.get("llm_allowed", False)
    )


def _apply_gate_source(source, user_input, session_id, sima, bois, memory, rules):
    handlers = {
        "DOMAIN": _domain_decision,
        "MEMORY": _memory_decision,
        "RUNTIME_STATE": _runtime_state_decision,
        "LLM": _llm_decision
    }
    return handlers[source](user_input, session_id, sima, bois, memory, rules)


def _domain_decision(user_input, session_id, sima, bois, memory, rules):
    if not user_input:
        rule = rules["rules"]["DOMAIN"]["empty_input"]
        return {
            "source": "DOMAIN",
            "decision": rule["decision"],
            "answer": rule["answer"],
            "reason": "empty_input"
        }

    return {"source": "DOMAIN", "decision": "CONTINUE"}


def _memory_decision(user_input, session_id, sima, bois, memory, rules):
    question = _clarification_answer(user_input)
    topic = _topic(user_input)
    limit = rules["question_memory"]["max_clarifications_per_session_topic"]
    count = memory.clarification_count(session_id, topic)
    duplicate = memory.has_asked_clarification(session_id, topic, question)

    if duplicate or count >= limit:
        rule = rules["rules"]["MEMORY"]["duplicate_clarification"]
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


def _runtime_state_decision(user_input, session_id, sima, bois, memory, rules):
    uncertainty = sima.get("uncertainty", 0)
    threshold = rules["thresholds"]["sima_uncertainty_clarification"]
    required_information = bois.get("required_information", [])

    if uncertainty > threshold and required_information:
        rule = rules["rules"]["RUNTIME_STATE"]["uncertainty_gap"]
        return {
            "source": "RUNTIME_STATE",
            "decision": rule["decision"],
            "answer": rule["answer_template"].format(input=user_input),
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


def _llm_decision(user_input, session_id, sima, bois, memory, rules):
    uncertainty = sima.get("uncertainty", 0)
    threshold = rules["thresholds"]["llm_uncertainty_threshold"]
    return {
        "source": "LLM",
        "decision": "ANSWER",
        "answer": "",
        "llm_allowed": uncertainty > threshold,
        "fallback_answer": rules["rules"]["LLM"]["fallback_answer"],
        "uncertainty": uncertainty,
        "threshold": threshold
    }


def _answer_response(event, sima, bois, domain, epistemic, decision, llm_allowed):
    answer = decision.get("answer") or (
        "" if llm_allowed else decision.get("fallback_answer", "")
    )
    return runtime_response(
        "ANSWER",
        answer=answer,
        trace={
            "session_id": event.get("session_id"),
            "source": event.get("meta", {}).get("source"),
            "phase": "FINALIZE",
            "domain": domain,
            "sima": sima,
            "bois": bois,
            "route": "local",
            "action": {"status": "no_external_action_required"},
            "epistemic": epistemic,
            "llm_allowed": llm_allowed,
            "answer_decision_source": decision["source"]
        },
        state={
            "runtime_state": "RETURN",
            "phase": "FINALIZE",
            "domain": _domain_state(domain)
        },
        actions=[{"status": "no_external_action_required"}]
    )


def _domain_state(domain):
    return {
        "name": domain.get("name"),
        "learning_policy": domain.get("learning_policy")
    }


def _topic(user_input):
    return user_input.strip().lower()


def _clarification_answer(user_input):
    if user_input:
        return f'Please clarify what you want me to do with: "{user_input}".'

    return "Please clarify what you want to do."


class BORISKernel:

    def __init__(
        self,
        memory=None,
        sima=None,
        bois=None,
        gap=None,
        llm=None,
        domain=None,
        schema_loader=None,
        epistemic_loader=None,
        engine=None
    ):
        self.memory = memory or Memory()
        self.sima = sima or SIMA()
        self.bois = bois or BOIS()
        self.gap = gap or GapDetector()
        self.llm = llm or LLM()
        self.domain = domain or DEFAULT_DOMAIN
        self.schema_loader = schema_loader or SchemaLoader()
        self.epistemic_loader = epistemic_loader or EpistemicHierarchyLoader()
        self.engine = engine or BORISRuntimeEngine(
            self,
            self.schema_loader.schema,
            epistemic_hierarchy=self.epistemic_loader.hierarchy
        )

    def run(self, event: dict):
        user_input = event.get("input", "")

        if is_introspection_query(user_input):
            return decision_gate(
                event,
                {},
                {},
                self.memory,
                self.domain,
                self.epistemic_loader.hierarchy
            )

        self.memory.remember_input(event.get("session_id", "default"), user_input)
        sima_out = self.sima.analyze(event)
        bois_out = self.bois.reason(sima_out, self.memory)
        result = decision_gate(
            event,
            sima_out,
            bois_out,
            self.memory,
            self.domain,
            self.epistemic_loader.hierarchy
        )

        if (
            result["type"] == "ANSWER"
            and result["trace"].get("llm_allowed")
            and not result["answer"]
        ):
            answer = self.llm.generate({
                "input": user_input,
                "domain": self.domain.snapshot(),
                "sima": sima_out,
                "bois": bois_out,
                "route": result["trace"].get("route"),
                "action": result["trace"].get("action")
            })
            result["answer"] = answer
            result["content"] = answer

        if result["type"] == "ANSWER":
            self.memory.write("WRITE_MEMORY", result)

        return result
