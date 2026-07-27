from __future__ import annotations

import os
from dataclasses import dataclass, field


SEMANTIC_CONTEXT_WINDOW_ENV = "BORIS_SEMANTIC_CONTEXT_WINDOW_TOKENS"


def _semantic_context_window_tokens():
    raw = os.getenv(SEMANTIC_CONTEXT_WINDOW_ENV, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        return 0
    return value if value > 0 else 0


SUPPORTED_PREDICATE_OPERATORS = frozenset({
    "all",
    "all_equal",
    "all_https",
    "all_items_fact",
    "all_references_resolve",
    "allowed_pair",
    "always",
    "any",
    "contains",
    "count_equals",
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
    "not_equals",
    "rank_at_least",
    "reference_resolves",
    "same_cycle",
    "same_subject",
    "schema_valid",
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
    substrate_id: str = "boris-runtime/phase-4s-independent-review"
    capabilities: tuple[str, ...] = (
        "archive_hash_binding",
        "component_hash_verification",
        "content_set_hash_binding",
        "deontic_operation_validation",
        "directory_content_set_binding",
        "draft_2020_12_schema_validation",
        "gate_decision_semantics",
        "immutable_passive_core_surface",
        "independent_review_ind2",
        "no_direct_state_mutation",
        "structured_semantic_calculation",
        "four_valued_predicate_dsl",
        "three_valued_predicate_dsl",
    )
    limitations: tuple[str, ...] = (
        "semantic_evaluation_only",
        "no_policy_kernel_transition",
        "no_external_action",
        "no_runtime_session_integration",
    )
    data_locations: tuple[str, ...] = (
        "in_process_immutable_core_surface",
        "in_process_execution_trace",
        "in_process_independent_review",
    )
    failure_modes: tuple[str, ...] = (
        "invalid_package_rejected",
        "unsupported_contract_rejected",
        "material_unknown_holds",
        "provider_failure_rejected",
        "review_failure_rejected",
    )
    supported_predicate_operators: frozenset[str] = SUPPORTED_PREDICATE_OPERATORS
    supported_deontic_operations: frozenset[str] = SUPPORTED_DEONTIC_OPERATIONS
    supported_gate_results: tuple[str, ...] = SUPPORTED_GATE_RESULTS
    supported_source_norm_types: frozenset[str] = SUPPORTED_SOURCE_NORM_TYPES
    semantic_context_window_tokens: int = field(
        default_factory=_semantic_context_window_tokens
    )
