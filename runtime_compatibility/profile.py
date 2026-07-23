from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_PREDICATE_OPERATORS = frozenset({
    "all",
    "always",
    "any",
    "exists",
    "fact",
    "gte",
    "in",
    "neq",
    "not",
    "scope_match",
    "unique",
})
SUPPORTED_DEONTIC_OPERATIONS = frozenset({
    "HOLD",
    "PERMIT",
    "PROHIBIT",
    "REPAIR",
    "REQUIRE",
    "STOP",
})
SUPPORTED_GATE_RESULTS = ("REPAIR", "STOP", "HOLD", "PASS")
SUPPORTED_SOURCE_NORM_TYPES = frozenset({
    "INVARIANT",
    "MANDATORY_RULE",
    "CONDITIONAL_RULE",
})


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    substrate_id: str = "boris-runtime/phase-4r-semantic-evaluation"
    capabilities: tuple[str, ...] = (
        "archive_hash_binding",
        "component_hash_verification",
        "content_set_hash_binding",
        "deontic_operation_validation",
        "gate_decision_semantics",
        "immutable_passive_core_surface",
        "no_direct_state_mutation",
        "structured_semantic_calculation",
        "three_valued_predicate_dsl",
    )
    limitations: tuple[str, ...] = (
        "semantic_evaluation_only",
        "no_independent_reviewer",
        "no_policy_kernel_transition",
        "no_external_action",
        "no_runtime_session_integration",
    )
    data_locations: tuple[str, ...] = (
        "in_process_immutable_core_surface",
        "in_process_execution_trace",
    )
    failure_modes: tuple[str, ...] = (
        "invalid_package_rejected",
        "unsupported_contract_rejected",
        "material_unknown_holds",
        "provider_failure_rejected",
    )
    supported_predicate_operators: frozenset[str] = SUPPORTED_PREDICATE_OPERATORS
    supported_deontic_operations: frozenset[str] = SUPPORTED_DEONTIC_OPERATIONS
    supported_gate_results: tuple[str, ...] = SUPPORTED_GATE_RESULTS
    supported_source_norm_types: frozenset[str] = SUPPORTED_SOURCE_NORM_TYPES
