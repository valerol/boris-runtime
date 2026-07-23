from __future__ import annotations

import json
from collections.abc import Mapping

from semantic_executor.errors import SemanticCalculationError
from semantic_executor.models import (
    ConflictCalculation,
    CoreReference,
    GATE_RESULTS,
    NormCalculation,
    SemanticCalculation,
    SemanticView,
    TRUTH_VALUES,
)


TOP_LEVEL_FIELDS = {
    "core_ref",
    "phase",
    "norm_results",
    "unknowns",
    "conflicts",
    "alternatives",
    "suggested_gate",
    "candidate_result",
}
CORE_REF_FIELDS = {
    "package_id",
    "artifact_version",
    "source_kind",
    "archive_sha256",
    "content_set_sha256",
    "manifest_sha256",
}
NORM_RESULT_FIELDS = {
    "norm_ref",
    "layer",
    "operation",
    "predicate_result",
    "applicability",
    "reason",
    "unknowns",
}
CONFLICT_FIELDS = {"norm_refs", "kind", "disposition", "reason"}


class SemanticCalculationValidator:
    def validate(self, raw_output, view: SemanticView) -> SemanticCalculation:
        payload = self._decode(raw_output)
        self._require_exact_fields(payload, TOP_LEVEL_FIELDS, "calculation")
        core_ref = self._parse_core_ref(payload["core_ref"])
        if core_ref != view.core_ref:
            raise SemanticCalculationError(
                "Semantic calculation core_ref does not match the immutable Core Surface."
            )
        phase = self._text(payload["phase"], "phase")
        if phase != view.phase:
            raise SemanticCalculationError(
                f"Semantic calculation phase mismatch: expected {view.phase}, got {phase}."
            )

        norm_results = self._parse_norm_results(payload["norm_results"], view)
        unknowns = self._string_array(payload["unknowns"], "unknowns")
        conflicts = self._parse_conflicts(payload["conflicts"], view)
        alternatives = self._parse_alternatives(payload["alternatives"])
        suggested_gate = self._text(payload["suggested_gate"], "suggested_gate")
        if suggested_gate not in GATE_RESULTS:
            raise SemanticCalculationError(
                f"Unsupported suggested_gate: {suggested_gate!r}"
            )
        candidate_result = payload["candidate_result"]
        if not isinstance(candidate_result, Mapping):
            raise SemanticCalculationError("candidate_result must be an object.")
        forbidden_result_fields = {
            "executed",
            "execution_status",
            "state_event",
            "state_transition",
            "tool_call",
        }
        if _contains_forbidden_key(candidate_result, forbidden_result_fields):
            raise SemanticCalculationError(
                "candidate_result attempts to represent execution or a state transition."
            )

        return SemanticCalculation(
            core_ref=core_ref,
            phase=phase,
            norm_results=norm_results,
            unknowns=unknowns,
            conflicts=conflicts,
            alternatives=alternatives,
            suggested_gate=suggested_gate,
            candidate_result=candidate_result,
        )

    def _parse_core_ref(self, value):
        value = self._object(value, "core_ref")
        self._require_exact_fields(value, CORE_REF_FIELDS, "core_ref")
        return CoreReference(
            package_id=self._text(value["package_id"], "core_ref.package_id"),
            artifact_version=self._text(
                value["artifact_version"],
                "core_ref.artifact_version",
            ),
            source_kind=self._text(
                value["source_kind"],
                "core_ref.source_kind",
            ),
            archive_sha256=self._text(
                value["archive_sha256"],
                "core_ref.archive_sha256",
            ),
            content_set_sha256=self._text(
                value["content_set_sha256"],
                "core_ref.content_set_sha256",
            ),
            manifest_sha256=self._text(
                value["manifest_sha256"],
                "core_ref.manifest_sha256",
            ),
        )

    def _parse_norm_results(self, value, view):
        if not isinstance(value, list):
            raise SemanticCalculationError("norm_results must be an array.")
        candidates = {
            candidate.norm_ref: candidate
            for candidate in view.candidates
        }
        parsed = []
        seen = set()
        for index, item in enumerate(value):
            label = f"norm_results[{index}]"
            item = self._object(item, label)
            self._require_exact_fields(item, NORM_RESULT_FIELDS, label)
            norm_ref = self._text(item["norm_ref"], f"{label}.norm_ref")
            if norm_ref in seen:
                raise SemanticCalculationError(f"Duplicate norm result: {norm_ref}")
            seen.add(norm_ref)
            if norm_ref not in candidates:
                raise SemanticCalculationError(
                    f"Semantic calculation references an unselected norm: {norm_ref}"
                )
            candidate = candidates[norm_ref]
            layer = self._text(item["layer"], f"{label}.layer")
            operation = self._text(item["operation"], f"{label}.operation")
            predicate_result = self._truth(
                item["predicate_result"],
                f"{label}.predicate_result",
            )
            applicability = self._truth(
                item["applicability"],
                f"{label}.applicability",
            )
            if layer != candidate.layer:
                raise SemanticCalculationError(
                    f"{norm_ref} layer mismatch: expected {candidate.layer}, got {layer}."
                )
            if operation != candidate.operation:
                raise SemanticCalculationError(
                    f"{norm_ref} operation mismatch: "
                    f"expected {candidate.operation}, got {operation}."
                )
            if predicate_result != candidate.formal_predicate_result:
                raise SemanticCalculationError(
                    f"{norm_ref} formal predicate mismatch: expected "
                    f"{candidate.formal_predicate_result}, got {predicate_result}."
                )
            parsed.append(NormCalculation(
                norm_ref=norm_ref,
                layer=layer,
                operation=operation,
                predicate_result=predicate_result,
                applicability=applicability,
                reason=self._text(item["reason"], f"{label}.reason"),
                unknowns=self._string_array(
                    item["unknowns"],
                    f"{label}.unknowns",
                ),
            ))

        missing = set(candidates) - seen
        if missing:
            raise SemanticCalculationError(
                f"Semantic calculation omitted selected norms: {sorted(missing)}"
            )
        return tuple(parsed)

    def _parse_conflicts(self, value, view):
        if not isinstance(value, list):
            raise SemanticCalculationError("conflicts must be an array.")
        selected = {candidate.norm_ref for candidate in view.candidates}
        parsed = []
        for index, item in enumerate(value):
            label = f"conflicts[{index}]"
            item = self._object(item, label)
            self._require_exact_fields(item, CONFLICT_FIELDS, label)
            norm_refs = self._string_array(item["norm_refs"], f"{label}.norm_refs")
            if len(norm_refs) < 2 or len(norm_refs) != len(set(norm_refs)):
                raise SemanticCalculationError(
                    f"{label}.norm_refs must contain at least two unique refs."
                )
            unknown_refs = set(norm_refs) - selected
            if unknown_refs:
                raise SemanticCalculationError(
                    f"{label} references unselected norms: {sorted(unknown_refs)}"
                )
            disposition = self._text(
                item["disposition"],
                f"{label}.disposition",
            )
            if disposition not in {"HOLD", "STOP"}:
                raise SemanticCalculationError(
                    f"{label}.disposition must be HOLD or STOP."
                )
            parsed.append(ConflictCalculation(
                norm_refs=norm_refs,
                kind=self._text(item["kind"], f"{label}.kind"),
                disposition=disposition,
                reason=self._text(item["reason"], f"{label}.reason"),
            ))
        return tuple(parsed)

    @staticmethod
    def _parse_alternatives(value):
        if not isinstance(value, list):
            raise SemanticCalculationError("alternatives must be an array.")
        result = []
        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                raise SemanticCalculationError(
                    f"alternatives[{index}] must be an object."
                )
            if _contains_forbidden_key(
                item,
                {
                    "executed",
                    "execution_status",
                    "state_event",
                    "state_transition",
                    "tool_call",
                },
            ):
                raise SemanticCalculationError(
                    f"alternatives[{index}] attempts to represent execution."
                )
            result.append(item)
        return tuple(result)

    @staticmethod
    def _decode(raw_output):
        if isinstance(raw_output, str):
            try:
                raw_output = json.loads(raw_output)
            except json.JSONDecodeError as exc:
                raise SemanticCalculationError(
                    "Semantic calculator returned invalid JSON."
                ) from exc
        if not isinstance(raw_output, Mapping):
            raise SemanticCalculationError(
                "Semantic calculator output must be one JSON object."
            )
        return raw_output

    @staticmethod
    def _require_exact_fields(value, expected, label):
        actual = set(value)
        if actual != expected:
            raise SemanticCalculationError(
                f"{label} fields mismatch: expected={sorted(expected)}, "
                f"actual={sorted(actual)}"
            )

    @staticmethod
    def _object(value, label):
        if not isinstance(value, Mapping):
            raise SemanticCalculationError(f"{label} must be an object.")
        return value

    @staticmethod
    def _text(value, label):
        if not isinstance(value, str) or not value.strip():
            raise SemanticCalculationError(f"{label} must be a non-empty string.")
        return value.strip()

    def _truth(self, value, label):
        value = self._text(value, label)
        if value not in TRUTH_VALUES:
            raise SemanticCalculationError(
                f"{label} must be TRUE, FALSE, or UNKNOWN."
            )
        return value

    def _string_array(self, value, label):
        if not isinstance(value, list):
            raise SemanticCalculationError(f"{label} must be a string array.")
        result = tuple(self._text(item, f"{label}[]") for item in value)
        if len(result) != len(set(result)):
            raise SemanticCalculationError(f"{label} contains duplicate values.")
        return result


def _contains_forbidden_key(value, forbidden):
    if isinstance(value, Mapping):
        if forbidden.intersection(
            str(key).strip().lower()
            for key in value
        ):
            return True
        return any(
            _contains_forbidden_key(nested, forbidden)
            for nested in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False
