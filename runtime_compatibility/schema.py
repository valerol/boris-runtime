from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime

from runtime_compatibility.errors import RuntimeContractError


SUPPORTED_SCHEMA_KEYS = frozenset({
    "$ref",
    "additionalProperties",
    "allOf",
    "const",
    "enum",
    "format",
    "if",
    "items",
    "maxProperties",
    "minItems",
    "minLength",
    "minProperties",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "then",
    "type",
    "uniqueItems",
})


def validate_schema_definition(document, definition_name, instance):
    if not isinstance(document, Mapping):
        raise RuntimeContractError("RUNTIME_SCHEMAS.json must contain an object.")
    definitions = document.get("$defs")
    if not isinstance(definitions, Mapping):
        raise RuntimeContractError("RUNTIME_SCHEMAS.json lacks an object $defs.")
    schema = definitions.get(definition_name)
    if not isinstance(schema, Mapping):
        raise RuntimeContractError(
            f"RUNTIME_SCHEMAS.json lacks definition {definition_name!r}."
        )
    _validate_supported_schema(schema, definition_name, document)
    _validate_instance(schema, instance, definition_name, document)


def _validate_supported_schema(schema, path, document, seen_refs=None):
    seen_refs = set(seen_refs or ())
    unexpected = set(schema) - SUPPORTED_SCHEMA_KEYS
    if unexpected:
        raise RuntimeContractError(
            f"Unsupported JSON Schema keywords at {path}: {sorted(unexpected)}"
        )
    reference = schema.get("$ref")
    if reference is not None:
        resolved, reference_name = _resolve_reference(document, reference)
        if reference_name not in seen_refs:
            _validate_supported_schema(
                resolved,
                reference_name,
                document,
                seen_refs | {reference_name},
            )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise RuntimeContractError(f"{path}.properties must be an object.")
    for name, nested in properties.items():
        if not isinstance(nested, Mapping):
            raise RuntimeContractError(f"{path}.properties.{name} must be an object.")
        _validate_supported_schema(nested, f"{path}.{name}", document, seen_refs)
    nested_items = schema.get("items")
    if nested_items is not None:
        if not isinstance(nested_items, Mapping):
            raise RuntimeContractError(f"{path}.items must be an object.")
        _validate_supported_schema(nested_items, f"{path}[]", document, seen_refs)
    additional = schema.get("additionalProperties")
    if isinstance(additional, Mapping):
        _validate_supported_schema(additional, f"{path}.*", document, seen_refs)
    elif additional not in {None, True, False}:
        raise RuntimeContractError(
            f"{path}.additionalProperties must be boolean or an object."
        )
    for keyword in ("allOf", "oneOf"):
        branches = schema.get(keyword)
        if branches is None:
            continue
        if not isinstance(branches, list) or not branches:
            raise RuntimeContractError(f"{path}.{keyword} must be a non-empty array.")
        for index, nested in enumerate(branches):
            if not isinstance(nested, Mapping):
                raise RuntimeContractError(
                    f"{path}.{keyword}[{index}] must be an object."
                )
            _validate_supported_schema(
                nested,
                f"{path}.{keyword}[{index}]",
                document,
                seen_refs,
            )
    for keyword in ("if", "then"):
        nested = schema.get(keyword)
        if nested is None:
            continue
        if not isinstance(nested, Mapping):
            raise RuntimeContractError(f"{path}.{keyword} must be an object.")
        _validate_supported_schema(
            nested,
            f"{path}.{keyword}",
            document,
            seen_refs,
        )


def _validate_instance(schema, value, path, document):
    reference = schema.get("$ref")
    if reference is not None:
        resolved, reference_name = _resolve_reference(document, reference)
        _validate_instance(resolved, value, reference_name, document)

    for index, nested in enumerate(schema.get("allOf", ())):
        _validate_instance(nested, value, f"{path}.allOf[{index}]", document)

    one_of = schema.get("oneOf")
    if one_of is not None:
        matches = 0
        for index, nested in enumerate(one_of):
            try:
                _validate_instance(
                    nested,
                    value,
                    f"{path}.oneOf[{index}]",
                    document,
                )
            except RuntimeContractError:
                continue
            matches += 1
        if matches != 1:
            raise RuntimeContractError(
                f"{path} must match exactly one oneOf branch; matched {matches}."
            )

    condition = schema.get("if")
    if condition is not None and "then" in schema:
        try:
            _validate_instance(condition, value, f"{path}.if", document)
        except RuntimeContractError:
            pass
        else:
            _validate_instance(schema["then"], value, f"{path}.then", document)

    expected_type = schema.get("type")
    if expected_type is not None:
        _validate_type(expected_type, value, path)
    if "const" in schema and value != schema["const"]:
        raise RuntimeContractError(
            f"{path} must equal {schema['const']!r}, got {value!r}."
        )
    if "enum" in schema and value not in schema["enum"]:
        raise RuntimeContractError(
            f"{path} must be one of {schema['enum']!r}, got {value!r}."
        )
    if isinstance(value, str):
        minimum = schema.get("minLength")
        if minimum is not None and len(value) < minimum:
            raise RuntimeContractError(
                f"{path} must contain at least {minimum} characters."
            )
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            raise RuntimeContractError(
                f"{path} does not match the required pattern {pattern!r}."
            )
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise RuntimeContractError(
                    f"{path} must contain an ISO 8601 date-time."
                ) from exc
        elif schema.get("format") not in {None, "date-time"}:
            raise RuntimeContractError(
                f"Unsupported JSON Schema format at {path}: "
                f"{schema['format']!r}"
            )
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise RuntimeContractError(f"{path}.required must be an array.")
        missing = set(required) - set(value)
        if missing:
            raise RuntimeContractError(
                f"{path} is missing required fields: {sorted(missing)}"
            )
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for name, nested in value.items():
            if name in properties:
                _validate_instance(
                    properties[name],
                    nested,
                    f"{path}.{name}",
                    document,
                )
            elif additional is False:
                raise RuntimeContractError(
                    f"{path} contains unsupported field {name!r}."
                )
            elif isinstance(additional, Mapping):
                _validate_instance(additional, nested, f"{path}.{name}", document)
        minimum = schema.get("minProperties")
        maximum = schema.get("maxProperties")
        if minimum is not None and len(value) < minimum:
            raise RuntimeContractError(
                f"{path} must contain at least {minimum} properties."
            )
        if maximum is not None and len(value) > maximum:
            raise RuntimeContractError(
                f"{path} must contain at most {maximum} properties."
            )
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_instance(
                schema["items"],
                item,
                f"{path}[{index}]",
                document,
            )
    if isinstance(value, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(value) < minimum:
            raise RuntimeContractError(
                f"{path} must contain at least {minimum} items."
            )
        if schema.get("uniqueItems") is True:
            canonical = [
                json.dumps(item, sort_keys=True, separators=(",", ":"))
                for item in value
            ]
            if len(canonical) != len(set(canonical)):
                raise RuntimeContractError(f"{path} must contain unique items.")


def _validate_type(expected_type, value, path):
    matches = {
        "array": lambda item: isinstance(item, list),
        "boolean": lambda item: isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "null": lambda item: item is None,
        "number": lambda item: (
            isinstance(item, (int, float)) and not isinstance(item, bool)
        ),
        "object": lambda item: isinstance(item, Mapping),
        "string": lambda item: isinstance(item, str),
    }
    validator = matches.get(expected_type)
    if validator is None:
        raise RuntimeContractError(
            f"Unsupported JSON Schema type at {path}: {expected_type!r}"
        )
    if not validator(value):
        raise RuntimeContractError(f"{path} must be of type {expected_type}.")


def _resolve_reference(document, reference):
    prefix = "#/$defs/"
    if not isinstance(reference, str) or not reference.startswith(prefix):
        raise RuntimeContractError(
            f"Unsupported JSON Schema reference: {reference!r}"
        )
    name = reference[len(prefix):]
    definitions = document.get("$defs")
    resolved = definitions.get(name) if isinstance(definitions, Mapping) else None
    if not isinstance(resolved, Mapping):
        raise RuntimeContractError(
            f"RUNTIME_SCHEMAS.json lacks referenced definition {name!r}."
        )
    return resolved, name
