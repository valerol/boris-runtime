from __future__ import annotations

import re
from collections.abc import Mapping

from runtime_compatibility.errors import RuntimeContractError


SUPPORTED_SCHEMA_KEYS = frozenset({
    "additionalProperties",
    "const",
    "enum",
    "items",
    "minLength",
    "pattern",
    "properties",
    "required",
    "type",
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
    _validate_supported_schema(schema, definition_name)
    _validate_instance(schema, instance, definition_name)


def _validate_supported_schema(schema, path):
    unexpected = set(schema) - SUPPORTED_SCHEMA_KEYS
    if unexpected:
        raise RuntimeContractError(
            f"Unsupported JSON Schema keywords at {path}: {sorted(unexpected)}"
        )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise RuntimeContractError(f"{path}.properties must be an object.")
    for name, nested in properties.items():
        if not isinstance(nested, Mapping):
            raise RuntimeContractError(f"{path}.properties.{name} must be an object.")
        _validate_supported_schema(nested, f"{path}.{name}")
    nested_items = schema.get("items")
    if nested_items is not None:
        if not isinstance(nested_items, Mapping):
            raise RuntimeContractError(f"{path}.items must be an object.")
        _validate_supported_schema(nested_items, f"{path}[]")
    additional = schema.get("additionalProperties")
    if isinstance(additional, Mapping):
        _validate_supported_schema(additional, f"{path}.*")
    elif additional not in {None, True, False}:
        raise RuntimeContractError(
            f"{path}.additionalProperties must be boolean or an object."
        )


def _validate_instance(schema, value, path):
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
                _validate_instance(properties[name], nested, f"{path}.{name}")
            elif additional is False:
                raise RuntimeContractError(
                    f"{path} contains unsupported field {name!r}."
                )
            elif isinstance(additional, Mapping):
                _validate_instance(additional, nested, f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_instance(schema["items"], item, f"{path}[{index}]")


def _validate_type(expected_type, value, path):
    matches = {
        "array": lambda item: isinstance(item, list),
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
