from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from semantic_executor.models import SemanticView, thaw_value


PHASE_OUTPUT_CONTRACT_VERSION = "boris-phase-output-contract/1.0"


class PhaseOutputContractError(RuntimeError):
    """Raised when the verified Core does not expose one phase output."""


@dataclass(frozen=True, slots=True)
class PhaseOutputIssue:
    code: str
    path: str
    received: Any
    expected: str
    instruction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "path": self.path,
            "received": thaw_value(self.received),
            "expected": self.expected,
            "instruction": self.instruction,
        }


class PhaseOutputValidationError(RuntimeError):
    """Raised when candidate_result violates the current Core phase."""

    def __init__(
        self,
        contract: "PhaseOutputContract",
        issues: Sequence[PhaseOutputIssue],
    ):
        self.contract = contract
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{issue.path}: {issue.expected}"
            for issue in self.issues
        )
        super().__init__(
            f"{contract.phase} candidate_result violates the canonical "
            f"{contract.primary_object} output contract: {summary}"
        )


@dataclass(frozen=True, slots=True)
class PhaseOutputContract:
    phase: str
    primary_object: str
    output_objects: tuple[str, ...]
    schema: Mapping[str, Any]
    gate_context_schema_ref: str

    @classmethod
    def from_view(cls, view: SemanticView) -> "PhaseOutputContract":
        execution_context = thaw_value(view.execution_context)
        if not isinstance(execution_context, Mapping):
            raise PhaseOutputContractError(
                f"Core phase {view.phase} has no executable context."
            )
        capsule = execution_context.get("phase_capsule")
        if not isinstance(capsule, Mapping):
            raise PhaseOutputContractError(
                f"Core phase {view.phase} has no phase capsule."
            )
        if capsule.get("phase_id") != view.phase:
            raise PhaseOutputContractError(
                f"Core phase capsule does not match {view.phase}."
            )
        gate_contract = capsule.get("gate_contract")
        if not isinstance(gate_contract, Mapping):
            raise PhaseOutputContractError(
                f"Core phase {view.phase} has no gate contract."
            )
        projection = gate_contract.get("canonical_object_projection")
        if not isinstance(projection, Mapping):
            raise PhaseOutputContractError(
                f"Core phase {view.phase} has no canonical object projection."
            )
        primary_object = _text(
            projection.get("primary_object"),
            "primary_object",
        )
        output_objects = _text_sequence(
            projection.get("output_objects"),
            "output_objects",
        )
        if _identity(primary_object) not in {
            _identity(value)
            for value in output_objects
        }:
            raise PhaseOutputContractError(
                f"Core phase {view.phase} primary object is not a declared "
                "phase output."
            )
        object_schemas = capsule.get("required_object_schemas")
        if not isinstance(object_schemas, Sequence) or isinstance(
            object_schemas,
            (str, bytes),
        ):
            raise PhaseOutputContractError(
                f"Core phase {view.phase} has no required object schemas."
            )
        matching = [
            value
            for value in object_schemas
            if isinstance(value, Mapping)
            and _identity(value.get("object_type"))
            == _identity(primary_object)
        ]
        if len(matching) != 1:
            raise PhaseOutputContractError(
                f"Core phase {view.phase} does not resolve exactly one schema "
                f"for primary object {primary_object!r}."
            )
        return cls(
            phase=view.phase,
            primary_object=primary_object,
            output_objects=output_objects,
            schema=_object_schema(matching[0]),
            gate_context_schema_ref=_text(
                gate_contract.get("input_schema_ref"),
                "gate input_schema_ref",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": PHASE_OUTPUT_CONTRACT_VERSION,
            "phase": self.phase,
            "semantic_output": {
                "primary_object": self.primary_object,
                "output_objects": list(self.output_objects),
                "schema_source": (
                    "phase_capsule.required_object_schemas"
                ),
                "schema": thaw_value(self.schema),
            },
            "gate_context": {
                "schema_ref": self.gate_context_schema_ref,
                "runtime_owned": True,
                "included_in_semantic_submission": False,
            },
        }

    def validate(self, candidate_result: Any) -> None:
        issues = _validation_issues(
            candidate_result,
            self.schema,
            path="$.candidate_result",
            primary_object=self.primary_object,
        )
        if issues:
            raise PhaseOutputValidationError(self, issues)


def _object_schema(source: Mapping[str, Any]) -> dict[str, Any]:
    required_fields = _text_sequence(
        source.get("required_fields"),
        "required_fields",
    )
    field_types = source.get("field_types")
    if not isinstance(field_types, Mapping):
        raise PhaseOutputContractError(
            "Canonical object schema has no field_types mapping."
        )
    allowed_states = _optional_text_sequence(
        source.get("allowed_states")
    )
    properties = {
        str(name): _field_schema(value)
        for name, value in field_types.items()
        if isinstance(name, str) and name
    }
    if "lifecycle_state" in required_fields:
        properties["lifecycle_state"] = (
            {"type": "string", "enum": list(allowed_states)}
            if allowed_states
            else {"type": "string", "minLength": 1}
        )
    missing_schemas = set(required_fields) - set(properties)
    if missing_schemas:
        raise PhaseOutputContractError(
            "Canonical object schema does not type required fields: "
            f"{sorted(missing_schemas)}"
        )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(required_fields),
        "properties": properties,
    }


def _field_schema(raw_types: Any) -> dict[str, Any]:
    types = _text_sequence(raw_types, "field_types entry")
    if len(types) == 1:
        descriptor = types[0]
        if descriptor in {
            "array",
            "boolean",
            "integer",
            "number",
            "object",
            "string",
        }:
            schema = {"type": descriptor}
            if descriptor == "string":
                schema["minLength"] = 1
            return schema
        if descriptor.startswith("#/$defs/"):
            return _definition_schema(descriptor.removeprefix("#/$defs/"))
    if all(
        value not in {
            "array",
            "boolean",
            "integer",
            "number",
            "object",
            "string",
        }
        and not value.startswith("#/$defs/")
        for value in types
    ):
        return {"enum": list(types)}
    return {
        "anyOf": [
            _field_schema([value])
            for value in types
        ]
    }


def _definition_schema(name: str) -> dict[str, Any]:
    identifier = {
        "type": "string",
        "minLength": 1,
        "pattern": (
            "^[A-Za-z][A-Za-z0-9]*"
            "(?:[-_.:][A-Za-z0-9]+)*$"
        ),
    }
    definitions = {
        "Identifier": identifier,
        "ObjectReference": identifier,
        "RevisionIdentifier": {
            "type": "string",
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
        },
        "StringOrList": {
            "oneOf": [
                {"type": "string", "minLength": 1},
                {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
            ],
        },
        "CostEstimate": {
            "oneOf": [
                {"type": "number"},
                {"type": "string", "minLength": 1},
            ],
        },
        "SLevel": {"enum": ["S0", "S1", "S2", "S3", "S4"]},
        "ObjectReferenceList": {
            "type": "array",
            "items": identifier,
        },
        "EvidenceReferenceList": {
            "type": "array",
            "items": identifier,
            "minItems": 1,
            "uniqueItems": True,
        },
        "RiskLevel": {
            "enum": ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7"],
        },
        "StateReference": {
            "type": "string",
            "enum": [
                "C00",
                "C01",
                "C02",
                "C03",
                "C04",
                "C05",
                "C06",
                "C07",
                "C08",
                "C09",
                "C10",
                "C11",
                "CLOSED",
            ],
        },
        "IndependenceLevel": {
            "enum": ["IND0", "IND1", "IND2", "IND3", "IND4", "IND_ANY"],
        },
    }
    try:
        return definitions[name]
    except KeyError as exc:
        raise PhaseOutputContractError(
            f"Canonical phase output references unsupported definition {name!r}."
        ) from exc


def _validation_issues(
    value: Any,
    schema: Mapping[str, Any],
    *,
    path: str,
    primary_object: str,
) -> list[PhaseOutputIssue]:
    if not isinstance(value, Mapping):
        return [PhaseOutputIssue(
            code="PHASE_OUTPUT_OBJECT_REQUIRED",
            path=path,
            received=value,
            expected=(
                f"one canonical {primary_object} object for the current phase"
            ),
            instruction=(
                f"Replace candidate_result with the canonical "
                f"{primary_object} object described by phase_output_contract."
            ),
        )]
    issues = []
    required = set(schema.get("required", ()))
    properties = schema.get("properties", {})
    actual = set(value)
    missing = sorted(required - actual)
    if missing:
        issues.append(PhaseOutputIssue(
            code="PHASE_OUTPUT_REQUIRED_FIELDS_MISSING",
            path=path,
            received=sorted(actual),
            expected=f"required fields {sorted(required)}",
            instruction=(
                f"Add the missing canonical {primary_object} fields: {missing}."
            ),
        ))
    if schema.get("additionalProperties") is False:
        extra = sorted(actual - set(properties))
        if extra:
            issues.append(PhaseOutputIssue(
                code="PHASE_OUTPUT_UNDECLARED_FIELDS",
                path=path,
                received=extra,
                expected=f"only fields {sorted(properties)}",
                instruction=(
                    "Remove fields that belong to another phase or to a "
                    f"free-form answer: {extra}."
                ),
            ))
    for name in sorted(actual.intersection(properties)):
        expected = properties[name]
        if not _matches_schema(value[name], expected):
            issues.append(PhaseOutputIssue(
                code="PHASE_OUTPUT_FIELD_INVALID",
                path=f"{path}.{name}",
                received=value[name],
                expected=_schema_expectation(expected),
                instruction=(
                    f"Correct {name!r} to satisfy the canonical "
                    f"{primary_object} field contract."
                ),
            ))
    return issues


def _matches_schema(value: Any, schema: Mapping[str, Any]) -> bool:
    if "enum" in schema and value not in schema["enum"]:
        return False
    branches = schema.get("oneOf") or schema.get("anyOf")
    if branches is not None:
        matches = sum(
            1
            for branch in branches
            if isinstance(branch, Mapping)
            and _matches_schema(value, branch)
        )
        return matches == 1 if "oneOf" in schema else matches >= 1
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(value, Mapping):
        return False
    if expected_type == "array" and (
        not isinstance(value, list)
        or isinstance(value, (str, bytes))
    ):
        return False
    if expected_type == "string" and not isinstance(value, str):
        return False
    if expected_type == "boolean" and not isinstance(value, bool):
        return False
    if expected_type == "integer" and (
        isinstance(value, bool) or not isinstance(value, int)
    ):
        return False
    if expected_type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        return False
    if expected_type == "string":
        if len(value) < int(schema.get("minLength", 0)):
            return False
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return False
    if expected_type == "array":
        if len(value) < int(schema.get("minItems", 0)):
            return False
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping) and any(
            not _matches_schema(item, item_schema)
            for item in value
        ):
            return False
        if schema.get("uniqueItems") and len({
            repr(item)
            for item in value
        }) != len(value):
            return False
    return True


def _schema_expectation(schema: Mapping[str, Any]) -> str:
    if "enum" in schema:
        return f"one of {list(schema['enum'])}"
    if "oneOf" in schema or "anyOf" in schema:
        branches = schema.get("oneOf") or schema.get("anyOf") or ()
        return " or ".join(
            _schema_expectation(branch)
            for branch in branches
            if isinstance(branch, Mapping)
        )
    expected_type = schema.get("type", "declared Core type")
    if expected_type == "string" and schema.get("minLength"):
        return "non-empty string"
    return str(expected_type)


def _identity(value: Any) -> str:
    return "".join(
        character.lower()
        for character in str(value or "")
        if character.isalnum()
    )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PhaseOutputContractError(
            f"Canonical phase output {label} is invalid."
        )
    return value.strip()


def _text_sequence(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PhaseOutputContractError(
            f"Canonical phase output {label} must be an array."
        )
    result = tuple(_text(item, label) for item in value)
    if not result or len(result) != len(set(result)):
        raise PhaseOutputContractError(
            f"Canonical phase output {label} is empty or contains duplicates."
        )
    return result


def _optional_text_sequence(value: Any) -> tuple[str, ...]:
    if value is None or value == [] or value == ():
        return ()
    return _text_sequence(value, "allowed_states")
