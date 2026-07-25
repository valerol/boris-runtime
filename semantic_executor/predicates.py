from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from semantic_executor.errors import SemanticViewError


TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"
ERROR = "ERROR"
MISSING = object()
DEFAULT_IDENTIFIER_PATTERN = (
    r"^[A-Za-z][A-Za-z0-9]*(?:[-_.:][A-Za-z0-9]+)*$"
)
SUPPORTED_OPERATORS = frozenset({
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


class PredicateEvaluator:
    def __init__(self, surface=None):
        self.surface = surface
        self.identifier_pattern = _identifier_pattern(surface)
        self.reference_resolver = (
            ReferenceResolver.from_surface(surface)
            if surface is not None
            else ReferenceResolver()
        )

    def evaluate(self, expression: Any, context: Mapping[str, Any]) -> str:
        if expression is True:
            return TRUE
        if expression is False:
            return FALSE
        if expression is None:
            return UNKNOWN
        if not isinstance(expression, Mapping):
            raise SemanticViewError(
                "Predicate expression must be an object or truth literal."
            )

        operation = expression.get("op")
        if operation not in SUPPORTED_OPERATORS:
            raise SemanticViewError(
                f"Unsupported Predicate DSL operator: {operation!r}"
            )

        handler = getattr(self, f"_evaluate_{operation}")
        return handler(expression, context)

    def _evaluate_always(self, expression, context):
        self._require_exact_keys(expression, {"op"})
        return TRUE

    def _evaluate_literal(self, expression, context):
        self._require_exact_keys(expression, {"op", "value"})
        value = expression["value"]
        if value is True:
            return TRUE
        if value is False:
            return FALSE
        if value is None:
            return UNKNOWN
        return ERROR

    def _evaluate_exists(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        return (
            TRUE
            if self._resolve(context, expression["path"]) is not MISSING
            else FALSE
        )

    def _evaluate_fact(self, expression, context):
        self._require_exact_keys(expression, {"op", "path", "equals"})
        actual = self._resolve(context, expression["path"])
        if actual is MISSING:
            return UNKNOWN
        return TRUE if _json_equal(actual, expression["equals"]) else FALSE

    def _evaluate_gte(self, expression, context):
        self._require_exact_keys(expression, {"op", "path", "value"})
        actual = self._resolve(context, expression["path"])
        if actual is MISSING:
            return UNKNOWN
        if isinstance(actual, bool) or isinstance(expression["value"], bool):
            return UNKNOWN
        try:
            return TRUE if actual >= expression["value"] else FALSE
        except TypeError:
            return UNKNOWN

    def _evaluate_enum_member(self, expression, context):
        self._require_exact_keys(expression, {"op", "path", "values"})
        values = expression["values"]
        if not _is_sequence(values):
            return ERROR
        actual = self._resolve(context, expression["path"])
        if actual is MISSING:
            return UNKNOWN
        if not _is_scalar(actual):
            return ERROR
        return (
            TRUE
            if any(_json_equal(actual, value) for value in values)
            else FALSE
        )

    def _evaluate_in(self, expression, context):
        allowed_keys = {"op", "path", "value", "values"}
        self._require_allowed_keys(expression, allowed_keys)
        if ("value" in expression) == ("values" in expression):
            raise SemanticViewError(
                "Predicate 'in' requires exactly one of value or values."
            )
        actual = self._resolve(context, expression["path"])
        if actual is MISSING:
            return UNKNOWN
        if "values" in expression:
            values = expression["values"]
            if not _is_sequence(values):
                return ERROR
            return (
                TRUE
                if any(_json_equal(actual, value) for value in values)
                else FALSE
            )
        if isinstance(actual, Mapping):
            return TRUE if expression["value"] in actual else FALSE
        if _is_sequence(actual):
            return (
                TRUE
                if any(
                    _json_equal(item, expression["value"])
                    for item in actual
                )
                else FALSE
            )
        return UNKNOWN

    def _evaluate_equals(self, expression, context):
        return self._evaluate_equality(
            expression,
            context,
            negate=False,
        )

    def _evaluate_equals_path(self, expression, context):
        return self._evaluate_equality(
            expression,
            context,
            negate=False,
        )

    def _evaluate_neq(self, expression, context):
        return self._evaluate_equality(
            expression,
            context,
            negate=True,
        )

    def _evaluate_equality(self, expression, context, *, negate):
        self._require_exact_keys(
            expression,
            {"op", "left_path", "right_path"},
        )
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        equal = _json_equal(left, right)
        if negate:
            equal = not equal
        return TRUE if equal else FALSE

    def _evaluate_all_equal(self, expression, context):
        self._require_exact_keys(expression, {"op", "paths"})
        paths = expression["paths"]
        if not _is_sequence(paths) or len(paths) < 2:
            raise SemanticViewError(
                "Predicate 'all_equal' paths must contain at least two items."
            )
        values = [self._resolve(context, path) for path in paths]
        if MISSING in values:
            return UNKNOWN
        return (
            TRUE
            if all(
                _json_equal(values[0], value)
                for value in values[1:]
            )
            else FALSE
        )

    def _evaluate_same_cycle(self, expression, context):
        self._require_exact_keys(expression, {"op", "paths"})
        paths = expression["paths"]
        if not _is_sequence(paths) or len(paths) < 2:
            raise SemanticViewError(
                "Predicate 'same_cycle' paths must contain at least two items."
            )
        values = [self._resolve(context, path) for path in paths]
        if MISSING in values:
            return UNKNOWN
        if not all(self._is_valid_identifier(value) for value in values):
            return FALSE
        return (
            TRUE
            if all(
                _json_equal(values[0], value)
                for value in values[1:]
            )
            else FALSE
        )

    def _evaluate_same_subject(self, expression, context):
        self._require_exact_keys(
            expression,
            {"op", "left_path", "right_path"},
        )
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        if not self._is_valid_identifier(
            left
        ) or not self._is_valid_identifier(right):
            return FALSE
        return TRUE if _json_equal(left, right) else FALSE

    def _evaluate_valid_identifier(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return FALSE
        return TRUE if self._is_valid_identifier(value) else FALSE

    def _evaluate_nonempty(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if value is MISSING or value is None:
            return FALSE
        if isinstance(value, str):
            return TRUE if value else FALSE
        if isinstance(value, Mapping) or _is_sequence(value):
            return TRUE if len(value) else FALSE
        return ERROR

    def _evaluate_min_items(self, expression, context):
        self._require_exact_keys(expression, {"op", "path", "value"})
        minimum = expression["value"]
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 0
        ):
            return ERROR
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return UNKNOWN
        if not _is_sequence(value):
            return ERROR
        return TRUE if len(value) >= minimum else FALSE

    def _evaluate_nonempty_scope(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if (
            value is MISSING
            or value is None
            or value == ""
            or value == []
        ):
            return FALSE
        normalized = self._normalize_scope(value)
        return ERROR if normalized is None else TRUE

    def _evaluate_scope_contains(self, expression, context):
        return self._evaluate_scope_relation(
            expression,
            context,
            relation="contains",
        )

    def _evaluate_scope_equal(self, expression, context):
        return self._evaluate_scope_relation(
            expression,
            context,
            relation="equal",
        )

    def _evaluate_scope_matches(self, expression, context):
        return self._evaluate_scope_relation(
            expression,
            context,
            relation="equal",
        )

    def _evaluate_scope_match(self, expression, context):
        self._require_exact_keys(
            expression,
            {"op", "left_path", "right_path"},
        )
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        return TRUE if _scope_matches(left, right) else FALSE

    def _evaluate_scope_relation(self, expression, context, *, relation):
        self._require_exact_keys(
            expression,
            {"op", "left_path", "right_path"},
        )
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        left_scope = self._normalize_scope(left)
        right_scope = self._normalize_scope(right)
        if left_scope is None or right_scope is None:
            return ERROR
        if relation == "contains":
            return TRUE if right_scope.issubset(left_scope) else FALSE
        return TRUE if left_scope == right_scope else FALSE

    def _evaluate_unique(self, expression, context):
        self._require_allowed_keys(
            expression,
            {"op", "path", "key_path"},
        )
        if "path" not in expression:
            raise SemanticViewError("Predicate 'unique' requires path.")
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return UNKNOWN
        if not _is_sequence(value):
            return ERROR
        key_path = expression.get("key_path")
        object_items = all(isinstance(item, Mapping) for item in value)
        scalar_items = all(_is_scalar(item) for item in value)
        if object_items:
            if not isinstance(key_path, str) or not key_path:
                return ERROR
            extracted = [self._resolve(item, key_path) for item in value]
            if MISSING in extracted or not all(
                _is_scalar(item)
                for item in extracted
            ):
                return ERROR
            markers = [_canonical_marker(item) for item in extracted]
        elif scalar_items:
            if key_path is not None:
                return ERROR
            markers = [_canonical_marker(item) for item in value]
        else:
            return ERROR
        return TRUE if len(markers) == len(set(markers)) else FALSE

    def _evaluate_reference_resolves(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return UNKNOWN
        return self.reference_resolver.resolve(value)

    def _evaluate_all_references_resolve(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return UNKNOWN
        if not _is_sequence(value):
            return ERROR
        if not value:
            return FALSE
        results = [
            self.reference_resolver.resolve(reference)
            for reference in value
        ]
        if FALSE in results:
            return FALSE
        if ERROR in results:
            return ERROR
        if UNKNOWN in results:
            return UNKNOWN
        return TRUE

    def _evaluate_all(self, expression, context):
        self._require_exact_keys(expression, {"op", "args"})
        saw_error = False
        saw_unknown = False
        for value in self._evaluate_args(expression["args"], context):
            if value == FALSE:
                return FALSE
            saw_error = saw_error or value == ERROR
            saw_unknown = saw_unknown or value == UNKNOWN
        if saw_error:
            return ERROR
        if saw_unknown:
            return UNKNOWN
        return TRUE

    def _evaluate_any(self, expression, context):
        self._require_exact_keys(expression, {"op", "args"})
        saw_error = False
        saw_unknown = False
        for value in self._evaluate_args(expression["args"], context):
            if value == TRUE:
                return TRUE
            saw_error = saw_error or value == ERROR
            saw_unknown = saw_unknown or value == UNKNOWN
        if saw_error:
            return ERROR
        if saw_unknown:
            return UNKNOWN
        return FALSE

    def _evaluate_not(self, expression, context):
        self._require_exact_keys(expression, {"op", "arg"})
        value = self.evaluate(expression["arg"], context)
        if value == TRUE:
            return FALSE
        if value == FALSE:
            return TRUE
        return value

    def _evaluate_args(self, value, context):
        if not _is_sequence(value) or not value:
            raise SemanticViewError(
                "Predicate args must be a non-empty array."
            )
        return [self.evaluate(item, context) for item in value]

    def _is_valid_identifier(self, value):
        return (
            isinstance(value, str)
            and bool(value)
            and self.identifier_pattern.fullmatch(value) is not None
        )

    def _normalize_scope(self, value):
        if isinstance(value, str):
            return (
                frozenset({value})
                if self._is_valid_identifier(value)
                else None
            )
        if not _is_sequence(value) or not value:
            return None
        if not all(self._is_valid_identifier(item) for item in value):
            return None
        normalized = frozenset(value)
        return normalized if len(normalized) == len(value) else None

    @staticmethod
    def _resolve(context, path):
        if not isinstance(path, str) or not path:
            raise SemanticViewError(
                "Predicate path must be a non-empty string."
            )
        current = context
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
                continue
            if _is_sequence(current):
                try:
                    current = current[int(part)]
                    continue
                except (ValueError, IndexError):
                    pass
            return MISSING
        return current

    @staticmethod
    def _require_exact_keys(expression, expected):
        actual = set(expression)
        if actual != expected:
            raise SemanticViewError(
                f"Predicate {expression.get('op')!r} fields mismatch: "
                f"expected={sorted(expected)}, actual={sorted(actual)}"
            )

    @staticmethod
    def _require_allowed_keys(expression, allowed):
        unexpected = set(expression) - allowed
        if unexpected:
            raise SemanticViewError(
                f"Predicate {expression.get('op')!r} has unexpected fields: "
                f"{sorted(unexpected)}"
            )


class ReferenceResolver:
    def __init__(self, registries=()):
        self.registries = tuple(
            Counter(registry)
            for registry in registries
        )

    @classmethod
    def from_surface(cls, surface):
        registries = [
            _tsv_reference_values(
                surface,
                "assurance/REFERENCE_INDEX.tsv",
                ("reference_id",),
                include_formal_selector=True,
            ),
            _tsv_reference_values(
                surface,
                "assurance/OBJECT_CATALOG.tsv",
                ("object_type", "alias", "canonical_type"),
            ),
            _tsv_reference_values(
                surface,
                "assurance/NORM_CATALOG.tsv",
                ("norm_id",),
            ),
            _json_reference_values(
                surface,
                "assurance/TEST_REGISTRY.json",
                "tests",
                "test_id",
            ),
            _json_string_array(
                surface,
                "fixtures/REFERENCE_FIXTURE_REGISTRY.json",
                "declared_ids",
            ),
            _runtime_record_ids(surface),
        ]
        return cls(registries)

    def resolve(self, value):
        if not isinstance(value, str):
            return ERROR
        value = value.strip()
        if not value:
            return FALSE
        counts = [
            registry[value]
            for registry in self.registries
            if registry[value]
        ]
        if any(count == 1 for count in counts):
            return TRUE
        if counts:
            return ERROR
        return FALSE


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and set(left) == set(right)
            and all(
                _json_equal(left[key], right[key])
                for key in left
            )
        )
    if _is_sequence(left) or _is_sequence(right):
        return (
            _is_sequence(left)
            and _is_sequence(right)
            and len(left) == len(right)
            and all(
                _json_equal(left_item, right_item)
                for left_item, right_item in zip(left, right)
            )
        )
    return type(left) is type(right) and left == right


def _scope_matches(left, right):
    if _json_equal(left, right):
        return True
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return all(
            key in left and _scope_matches(left[key], value)
            for key, value in right.items()
        )
    if _is_sequence(left) and _is_sequence(right):
        left_markers = {
            _canonical_marker(item)
            for item in left
        }
        right_markers = {
            _canonical_marker(item)
            for item in right
        }
        return right_markers.issubset(left_markers)
    return False


def _identifier_pattern(surface):
    pattern = DEFAULT_IDENTIFIER_PATTERN
    if surface is not None:
        try:
            declared = surface.read_json(
                "machine/IDENTIFIER_GRAMMAR.json"
            ).get("pattern")
        except (KeyError, UnicodeDecodeError, ValueError, AttributeError):
            declared = None
        if isinstance(declared, str) and declared:
            pattern = declared
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise SemanticViewError(
            "Core identifier grammar is not a valid regular expression."
        ) from exc


def _is_sequence(value):
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes),
    )


def _is_scalar(value):
    return value is None or isinstance(
        value,
        (str, int, float, bool),
    )


def _canonical_marker(value):
    if isinstance(value, Mapping):
        normalized = {
            key: _canonical_value(nested)
            for key, nested in value.items()
        }
        return (
            "object",
            json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    if _is_sequence(value):
        return (
            "array",
            json.dumps(
                [_canonical_value(item) for item in value],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    if value is None:
        return ("null", "")
    if isinstance(value, bool):
        return ("boolean", "true" if value else "false")
    if isinstance(value, (int, float)):
        return ("number", json.dumps(value, separators=(",", ":")))
    if isinstance(value, str):
        return ("string", value)
    return (type(value).__name__, repr(value))


def _canonical_value(value):
    if isinstance(value, Mapping):
        return {
            key: _canonical_value(nested)
            for key, nested in value.items()
        }
    if _is_sequence(value):
        return [_canonical_value(item) for item in value]
    return value


def _tsv_reference_values(
    surface,
    path,
    fields,
    *,
    include_formal_selector=False,
):
    try:
        text = surface.read_bytes(path).decode("utf-8")
    except (KeyError, UnicodeDecodeError):
        return ()
    values = []
    for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
        for field in fields:
            value = (row.get(field) or "").strip()
            if value:
                values.append(value)
        if include_formal_selector:
            target_file = (row.get("target_file") or "").strip()
            target_selector = (row.get("target_selector") or "").strip()
            if target_file:
                values.append(target_file)
            if target_file and target_selector:
                values.append(f"{target_file}#{target_selector}")
    return tuple(values)


def _json_reference_values(surface, path, array_field, id_field):
    try:
        payload = surface.read_json(path)
    except (KeyError, UnicodeDecodeError, ValueError):
        return ()
    records = (
        payload.get(array_field, [])
        if isinstance(payload, Mapping)
        else []
    )
    if not _is_sequence(records):
        return ()
    return tuple(
        value
        for record in records
        if isinstance(record, Mapping)
        for value in [(record.get(id_field) or "").strip()]
        if value
    )


def _json_string_array(surface, path, field):
    try:
        payload = surface.read_json(path)
    except (KeyError, UnicodeDecodeError, ValueError):
        return ()
    values = (
        payload.get(field, [])
        if isinstance(payload, Mapping)
        else []
    )
    if not _is_sequence(values):
        return ()
    return tuple(
        value.strip()
        for value in values
        if isinstance(value, str) and value.strip()
    )


def _runtime_record_ids(surface):
    values = []
    for path in surface.payload_paths:
        if not path.startswith("runtime/") or not path.endswith(".json"):
            continue
        try:
            payload = surface.read_json(path)
        except (UnicodeDecodeError, ValueError):
            continue
        values.extend(_collect_identifier_fields(payload))
    return tuple(values)


def _collect_identifier_fields(value):
    result = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if (
                isinstance(nested, str)
                and str(key).lower().endswith("_id")
                and nested.strip()
            ):
                result.append(nested.strip())
            result.extend(_collect_identifier_fields(nested))
    elif _is_sequence(value):
        for nested in value:
            result.extend(_collect_identifier_fields(nested))
    return result
