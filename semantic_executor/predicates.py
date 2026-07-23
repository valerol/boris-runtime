from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from semantic_executor.errors import SemanticViewError


TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"
MISSING = object()
SUPPORTED_OPERATORS = frozenset({
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


class PredicateEvaluator:
    def evaluate(self, expression: Any, context: Mapping[str, Any]) -> str:
        if expression is True:
            return TRUE
        if expression is False:
            return FALSE
        if expression is None:
            return UNKNOWN
        if not isinstance(expression, Mapping):
            raise SemanticViewError("Predicate expression must be an object or truth literal.")

        operation = expression.get("op")
        if operation not in SUPPORTED_OPERATORS:
            raise SemanticViewError(f"Unsupported Predicate DSL operator: {operation!r}")

        handler = getattr(self, f"_evaluate_{operation}")
        return handler(expression, context)

    def _evaluate_always(self, expression, context):
        self._require_exact_keys(expression, {"op"})
        return TRUE

    def _evaluate_exists(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        return TRUE if self._resolve(context, expression["path"]) is not MISSING else FALSE

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

    def _evaluate_in(self, expression, context):
        allowed_keys = {"op", "path", "value", "values"}
        self._require_allowed_keys(expression, allowed_keys)
        if ("value" in expression) == ("values" in expression):
            raise SemanticViewError("Predicate 'in' requires exactly one of value or values.")
        actual = self._resolve(context, expression["path"])
        if actual is MISSING:
            return UNKNOWN
        if "values" in expression:
            values = expression["values"]
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                return UNKNOWN
            return TRUE if any(_json_equal(actual, value) for value in values) else FALSE
        if isinstance(actual, Mapping):
            return TRUE if expression["value"] in actual else FALSE
        if isinstance(actual, Sequence) and not isinstance(actual, (str, bytes)):
            return (
                TRUE
                if any(_json_equal(item, expression["value"]) for item in actual)
                else FALSE
            )
        return UNKNOWN

    def _evaluate_neq(self, expression, context):
        self._require_exact_keys(expression, {"op", "left_path", "right_path"})
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        return FALSE if _json_equal(left, right) else TRUE

    def _evaluate_scope_match(self, expression, context):
        self._require_exact_keys(expression, {"op", "left_path", "right_path"})
        left = self._resolve(context, expression["left_path"])
        right = self._resolve(context, expression["right_path"])
        if MISSING in (left, right):
            return UNKNOWN
        return TRUE if _scope_matches(left, right) else FALSE

    def _evaluate_unique(self, expression, context):
        self._require_exact_keys(expression, {"op", "path"})
        value = self._resolve(context, expression["path"])
        if value is MISSING:
            return UNKNOWN
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return UNKNOWN
        markers = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
        return TRUE if len(markers) == len(set(markers)) else FALSE

    def _evaluate_all(self, expression, context):
        self._require_exact_keys(expression, {"op", "args"})
        values = self._evaluate_args(expression["args"], context)
        if FALSE in values:
            return FALSE
        if values and all(value == TRUE for value in values):
            return TRUE
        return UNKNOWN

    def _evaluate_any(self, expression, context):
        self._require_exact_keys(expression, {"op", "args"})
        values = self._evaluate_args(expression["args"], context)
        if TRUE in values:
            return TRUE
        if values and all(value == FALSE for value in values):
            return FALSE
        return UNKNOWN

    def _evaluate_not(self, expression, context):
        self._require_exact_keys(expression, {"op", "arg"})
        value = self.evaluate(expression["arg"], context)
        if value == TRUE:
            return FALSE
        if value == FALSE:
            return TRUE
        return UNKNOWN

    def _evaluate_args(self, value, context):
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes))
            or not value
        ):
            raise SemanticViewError("Predicate args must be a non-empty array.")
        return [self.evaluate(item, context) for item in value]

    @staticmethod
    def _resolve(context, path):
        if not isinstance(path, str) or not path:
            raise SemanticViewError("Predicate path must be a non-empty string.")
        current = context
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
                continue
            if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
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


def _json_equal(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def _scope_matches(left, right):
    if _json_equal(left, right):
        return True
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return all(
            key in left and _scope_matches(left[key], value)
            for key, value in right.items()
        )
    if (
        isinstance(left, Sequence)
        and isinstance(right, Sequence)
        and not isinstance(left, (str, bytes))
        and not isinstance(right, (str, bytes))
    ):
        left_markers = {
            json.dumps(item, sort_keys=True, separators=(",", ":"))
            for item in left
        }
        right_markers = {
            json.dumps(item, sort_keys=True, separators=(",", ":"))
            for item in right
        }
        return right_markers.issubset(left_markers)
    return False
