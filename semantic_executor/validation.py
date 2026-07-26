from __future__ import annotations

import json
import re
from collections.abc import Mapping

from semantic_executor.errors import SemanticCalculationError
from semantic_executor.models import (
    APPLICABILITY_RESULTS,
    ConflictCalculation,
    CoreReference,
    GATE_RESULTS,
    NormCalculation,
    PREDICATE_RESULTS,
    SemanticCalculation,
    SemanticInput,
    SemanticUncertainty,
    SemanticView,
)
from semantic_executor.uncertainty import (
    OPERATOR_RESOLUTION_CLASS,
    UNCERTAINTY_RESOLUTION_CLASSES,
    resolution_catalog_index,
)


TOP_LEVEL_FIELDS = {
    "core_ref",
    "phase",
    "norm_results",
    "unknowns",
    "uncertainties",
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
UNCERTAINTY_FIELDS = {
    "uncertainty_id",
    "description",
    "resolution_class",
    "target_path",
    "norm_refs",
    "core_refs",
    "operator_question",
}
SEMANTIC_PATH_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9_-]*"
    r"(?:\.[A-Za-z][A-Za-z0-9_-]*)*"
)


class SemanticCalculationValidator:
    def validate(
        self,
        raw_output,
        view: SemanticView,
        semantic_input: SemanticInput | None = None,
    ) -> SemanticCalculation:
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
        uncertainties = self._parse_uncertainties(
            payload["uncertainties"],
            view,
        )
        self._require_uncertainty_coverage(
            unknowns,
            norm_results,
            uncertainties,
            semantic_input,
        )
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
            uncertainties=uncertainties,
            conflicts=conflicts,
            alternatives=alternatives,
            suggested_gate=suggested_gate,
            candidate_result=candidate_result,
        )

    def _parse_core_ref(self, value):
        value = self._object(value, "core_ref")
        self._require_exact_fields(value, CORE_REF_FIELDS, "core_ref")
        source_kind = self._text(
            value["source_kind"],
            "core_ref.source_kind",
        )
        archive_sha256 = value["archive_sha256"]
        if not isinstance(archive_sha256, str):
            raise SemanticCalculationError(
                "core_ref.archive_sha256 must be a string."
            )
        archive_sha256 = archive_sha256.strip()
        if source_kind == "archive" and not archive_sha256:
            raise SemanticCalculationError(
                "core_ref.archive_sha256 must be non-empty for an archive source."
            )
        if source_kind == "directory" and archive_sha256:
            raise SemanticCalculationError(
                "core_ref.archive_sha256 must be empty for a directory source."
            )
        return CoreReference(
            package_id=self._text(value["package_id"], "core_ref.package_id"),
            artifact_version=self._text(
                value["artifact_version"],
                "core_ref.artifact_version",
            ),
            source_kind=source_kind,
            archive_sha256=archive_sha256,
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
            predicate_result = self._predicate_result(
                item["predicate_result"],
                f"{label}.predicate_result",
            )
            applicability = self._applicability(
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
            if candidate.predicate_mode == "legacy_formal":
                if predicate_result != candidate.formal_predicate_result:
                    raise SemanticCalculationError(
                        f"{norm_ref} formal predicate mismatch: expected "
                        f"{candidate.formal_predicate_result}, got "
                        f"{predicate_result}."
                    )
            elif candidate.predicate_mode == "runtime_typed":
                if predicate_result != candidate.formal_predicate_result:
                    raise SemanticCalculationError(
                        f"{norm_ref} typed violation result mismatch: expected "
                        f"{candidate.formal_predicate_result}, got "
                        f"{predicate_result}."
                    )
                if applicability != candidate.formal_applicability_result:
                    raise SemanticCalculationError(
                        f"{norm_ref} typed applicability result mismatch: "
                        f"expected {candidate.formal_applicability_result}, "
                        f"got {applicability}."
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

    def _parse_uncertainties(self, value, view):
        if not isinstance(value, list):
            raise SemanticCalculationError(
                "uncertainties must be an array."
            )
        selected = {
            candidate.norm_ref
            for candidate in view.candidates
        }
        catalog = resolution_catalog_index(
            view.uncertainty_resolution_catalog
        )
        parsed = []
        seen = set()
        for index, raw in enumerate(value):
            label = f"uncertainties[{index}]"
            item = self._object(raw, label)
            self._require_exact_fields(
                item,
                UNCERTAINTY_FIELDS,
                label,
            )
            uncertainty_id = self._text(
                item["uncertainty_id"],
                f"{label}.uncertainty_id",
            )
            if uncertainty_id in seen:
                raise SemanticCalculationError(
                    f"Duplicate uncertainty ID: {uncertainty_id}"
                )
            seen.add(uncertainty_id)
            resolution_class = self._text(
                item["resolution_class"],
                f"{label}.resolution_class",
            )
            if resolution_class not in UNCERTAINTY_RESOLUTION_CLASSES:
                raise SemanticCalculationError(
                    f"{label}.resolution_class is unsupported."
                )
            target_path = self._nullable_text(
                item["target_path"],
                f"{label}.target_path",
            )
            if (
                target_path is not None
                and not SEMANTIC_PATH_PATTERN.fullmatch(target_path)
            ):
                raise SemanticCalculationError(
                    f"{label}.target_path is invalid."
                )
            norm_refs = self._string_array(
                item["norm_refs"],
                f"{label}.norm_refs",
            )
            unknown_norm_refs = set(norm_refs) - selected
            if unknown_norm_refs:
                raise SemanticCalculationError(
                    f"{label} references unselected norms: "
                    f"{sorted(unknown_norm_refs)}"
                )
            core_refs = self._string_array(
                item["core_refs"],
                f"{label}.core_refs",
            )
            missing_core_refs = set(core_refs) - set(catalog)
            if missing_core_refs:
                raise SemanticCalculationError(
                    f"{label} references unknown Core resolution entries: "
                    f"{sorted(missing_core_refs)}"
                )
            if resolution_class in {
                "RUNTIME_DERIVABLE",
                "DOWNSTREAM_PRECONDITION",
            }:
                if not core_refs:
                    raise SemanticCalculationError(
                        f"{label}.core_refs is required for "
                        f"{resolution_class}."
                    )
                mismatched = [
                    core_ref
                    for core_ref in core_refs
                    if catalog[core_ref]["resolution_class"]
                    != resolution_class
                ]
                if mismatched:
                    raise SemanticCalculationError(
                        f"{label}.core_refs contradict "
                        f"{resolution_class}: {sorted(mismatched)}"
                    )
            if resolution_class == OPERATOR_RESOLUTION_CLASS:
                if (
                    target_path is not None
                    and target_path.startswith("violation.")
                ):
                    raise SemanticCalculationError(
                        f"{label} cannot assign an internal violation "
                        "selector to the operator."
                    )
                if any(
                    catalog[core_ref]["source_class"]
                    == "CURRENT_RUNTIME"
                    for core_ref in core_refs
                ):
                    raise SemanticCalculationError(
                        f"{label} cannot assign a CURRENT_RUNTIME Core "
                        "requirement to the operator."
                    )
                operator_question = self._nullable_text(
                    item["operator_question"],
                    f"{label}.operator_question",
                )
                if operator_question is None:
                    raise SemanticCalculationError(
                        f"{label}.operator_question is required for "
                        "OPERATOR_INPUT."
                    )
            else:
                operator_question = self._nullable_text(
                    item["operator_question"],
                    f"{label}.operator_question",
                )
                if operator_question is not None:
                    raise SemanticCalculationError(
                        f"{label}.operator_question is allowed only for "
                        "OPERATOR_INPUT."
                    )
            parsed.append(SemanticUncertainty(
                uncertainty_id=uncertainty_id,
                description=self._text(
                    item["description"],
                    f"{label}.description",
                ),
                resolution_class=resolution_class,
                target_path=target_path,
                norm_refs=norm_refs,
                core_refs=core_refs,
                operator_question=operator_question,
            ))
        return tuple(parsed)

    @staticmethod
    def _require_uncertainty_coverage(
        unknowns,
        norm_results,
        uncertainties,
        semantic_input,
    ):
        descriptions = {
            uncertainty.description
            for uncertainty in uncertainties
        }
        disclosed = {
            *unknowns,
            *(
                unknown
                for result in norm_results
                for unknown in result.unknowns
            ),
        }
        missing = disclosed - descriptions
        if missing:
            raise SemanticCalculationError(
                "Every disclosed unknown must have one typed uncertainty "
                f"record: {sorted(missing)}"
            )
        undisclosed = descriptions - disclosed
        if undisclosed:
            raise SemanticCalculationError(
                "Every typed uncertainty must be disclosed in unknowns or "
                f"a norm result: {sorted(undisclosed)}"
            )
        if semantic_input is not None:
            omitted = set(semantic_input.unknowns) - set(unknowns)
            if omitted:
                raise SemanticCalculationError(
                    "Semantic calculation omitted supplied unknowns: "
                    f"{sorted(omitted)}"
                )

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

    @staticmethod
    def _nullable_text(value, label):
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise SemanticCalculationError(
                f"{label} must be null or a non-empty string."
            )
        return value.strip()

    def _predicate_result(self, value, label):
        value = self._text(value, label)
        if value not in PREDICATE_RESULTS:
            raise SemanticCalculationError(
                f"{label} must be TRUE, FALSE, UNKNOWN, or ERROR."
            )
        return value

    def _applicability(self, value, label):
        value = self._text(value, label)
        if value not in APPLICABILITY_RESULTS:
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
