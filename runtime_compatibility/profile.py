from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_PREDICATE_OPERATORS = frozenset({
    "all",
    "all_equal",
    "all_references_resolve",
    "always",
    "any",
    "enum_member",
    "equals",
    "equals_path",
    "exists",
    "fact",
    "gte",
    "in",
    "literal",
    "min_items",
    "neq",
    "nonempty",
    "nonempty_scope",
    "not",
    "reference_resolves",
    "same_cycle",
    "same_subject",
    "scope_contains",
    "scope_equal",
    "scope_match",
    "scope_matches",
    "unique",
    "valid_identifier",
})
SUPPORTED_PREDICATE_TRUTH_VALUES = (
    ("TRUE", "FALSE", "UNKNOWN"),
    ("TRUE", "FALSE", "UNKNOWN", "ERROR"),
)
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
        "directory_content_set_binding",
        "gate_decision_semantics",
        "immutable_passive_core_surface",
        "no_direct_state_mutation",
        "structured_semantic_calculation",
        "four_valued_predicate_dsl",
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
