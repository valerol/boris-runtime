from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import uuid4

from semantic_executor import CoreReference, SemanticInput


CONTINUATION_VERSION = "boris-continuation/1.0"
HOLD_HANDOFF_VERSION = "boris-hold-handoff/1.0"
CONTINUATION_SECRET_ENV = "BORIS_CONTINUATION_SECRET"
CONTINUATION_TTL_ENV = "BORIS_CONTINUATION_TTL_SECONDS"
DEFAULT_CONTINUATION_TTL_SECONDS = 3600
MIN_CONTINUATION_SECRET_BYTES = 32
MAX_CONTINUATION_TOKEN_CHARACTERS = 262144
MAX_OPERATOR_VALUE_CHARACTERS = 2000
SEMANTIC_INPUT_FIELDS = {
    "phenomenon",
    "phase",
    "facts",
    "unknowns",
    "evidence",
    "authority",
    "active_layers",
    "triggers",
    "applicability_scopes",
    "requested_norm_refs",
    "evaluate_inactive",
}


class ContinuationError(RuntimeError):
    """Base error for stateless HOLD continuation."""


class ContinuationUnavailable(ContinuationError):
    """Raised when the server cannot issue or verify continuation tokens."""


class InvalidContinuationToken(ContinuationError):
    """Raised when a continuation token is malformed, invalid, or expired."""


class ContinuationStateMismatch(ContinuationError):
    """Raised when a valid token does not match the current Runtime state."""


class ContinuationCodec:
    def __init__(self, secret: str | bytes, ttl_seconds: int = DEFAULT_CONTINUATION_TTL_SECONDS, clock=None):
        secret_bytes = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(secret_bytes, bytes) or len(secret_bytes) < MIN_CONTINUATION_SECRET_BYTES:
            raise ContinuationUnavailable(
                f"{CONTINUATION_SECRET_ENV} must contain at least "
                f"{MIN_CONTINUATION_SECRET_BYTES} bytes."
            )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or ttl_seconds < 60
            or ttl_seconds > 86400
        ):
            raise ContinuationUnavailable(
                f"{CONTINUATION_TTL_ENV} must be an integer from 60 through 86400."
            )
        self._secret = secret_bytes
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time

    @classmethod
    def from_environment(cls) -> "ContinuationCodec":
        secret = os.getenv(CONTINUATION_SECRET_ENV, "")
        raw_ttl = os.getenv(CONTINUATION_TTL_ENV, "").strip()
        if raw_ttl:
            try:
                ttl_seconds = int(raw_ttl)
            except ValueError as exc:
                raise ContinuationUnavailable(
                    f"{CONTINUATION_TTL_ENV} must be an integer."
                ) from exc
        else:
            ttl_seconds = DEFAULT_CONTINUATION_TTL_SECONDS
        return cls(secret, ttl_seconds=ttl_seconds)

    def issue(self, state: Mapping) -> tuple[str, dict]:
        now = int(self._clock())
        claims = {
            "version": CONTINUATION_VERSION,
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
            "token_id": str(uuid4()),
            **dict(state),
        }
        payload = _canonical_json(claims)
        encoded_payload = _base64url_encode(payload)
        signature = hmac.new(
            self._secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        token = (
            f"v1.{encoded_payload}.{_base64url_encode(signature)}"
        )
        if len(token) > MAX_CONTINUATION_TOKEN_CHARACTERS:
            raise ContinuationUnavailable(
                "Continuation state exceeds the stateless token size limit."
            )
        return token, claims

    def verify(self, token: str) -> dict:
        if not isinstance(token, str) or not token.strip():
            raise InvalidContinuationToken(
                "continuation_token must be a non-empty string."
            )
        if len(token) > MAX_CONTINUATION_TOKEN_CHARACTERS:
            raise InvalidContinuationToken(
                "continuation_token exceeds the size limit."
            )
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            raise InvalidContinuationToken(
                "continuation_token has an unsupported format."
            )
        encoded_payload, encoded_signature = parts[1], parts[2]
        try:
            supplied_signature = _base64url_decode(encoded_signature)
            payload_bytes = _base64url_decode(encoded_payload)
        except (ValueError, UnicodeEncodeError) as exc:
            raise InvalidContinuationToken(
                "continuation_token is not valid base64url data."
            ) from exc
        expected_signature = hmac.new(
            self._secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise InvalidContinuationToken(
                "continuation_token signature is invalid."
            )
        try:
            claims = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidContinuationToken(
                "continuation_token payload is invalid."
            ) from exc
        if not isinstance(claims, dict):
            raise InvalidContinuationToken(
                "continuation_token payload must be an object."
            )
        if claims.get("version") != CONTINUATION_VERSION:
            raise InvalidContinuationToken(
                "continuation_token version is unsupported."
            )
        issued_at = claims.get("issued_at")
        expires_at = claims.get("expires_at")
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or expires_at <= issued_at
        ):
            raise InvalidContinuationToken(
                "continuation_token lifetime is invalid."
            )
        if int(self._clock()) >= expires_at:
            raise InvalidContinuationToken(
                "continuation_token has expired."
            )
        return claims


def continuation_expiry_iso(claims: Mapping) -> str:
    expires_at = claims.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, int):
        raise InvalidContinuationToken(
            "continuation_token expiry is invalid."
        )
    return datetime.fromtimestamp(
        expires_at,
        tz=timezone.utc,
    ).isoformat()


def build_hold_handoff(
    codec,
    semantic_input,
    candidate,
    session_id,
    resume_count,
):
    unknowns = _hold_unknowns(candidate)
    required_inputs = candidate.trace.to_dict()["required_inputs"]
    required_operator_input = {
        "question": _hold_question(unknowns, required_inputs),
        "unknowns": unknowns,
        "fields": required_inputs,
        "response_contract": {
            "statement": "Operator clarification in plain text.",
            "values": (
                "Optional path-to-value object. Paths must be listed in fields."
            ),
            "resolved_unknowns": (
                "Optional array containing exact entries from unknowns."
            ),
        },
    }
    token, claims = codec.issue({
        "session_id": session_id,
        "resume_count": resume_count,
        "semantic_input": semantic_input.to_prompt_dict(),
        "core_ref": candidate.core_ref.to_dict(),
        "hold": {
            "unknowns": unknowns,
            "required_inputs": required_inputs,
        },
    })
    return {
        "handoff_version": HOLD_HANDOFF_VERSION,
        "status": "operator_input_required",
        "reason": (
            "Runtime gate is HOLD because material information or a "
            "recoverable precondition remains unresolved."
        ),
        "required_operator_input": required_operator_input,
        "continuation_token": token,
        "expires_at": continuation_expiry_iso(claims),
        "resume_count": resume_count,
    }


def resume_token(resume):
    if not isinstance(resume, Mapping):
        raise InvalidContinuationToken("resume must be an object.")
    token = resume.get("continuation_token")
    if not isinstance(token, str) or not token.strip():
        raise InvalidContinuationToken(
            "resume.continuation_token must be a non-empty string."
        )
    return token.strip()


def continuation_text(state, field):
    value = state.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidContinuationToken(
            f"continuation_token {field} is invalid."
        )
    return value.strip()


def continuation_count(state):
    value = state.get("resume_count", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidContinuationToken(
            "continuation_token resume_count is invalid."
        )
    return value


def continuation_source_input(state):
    semantic_input = state.get("semantic_input")
    if not isinstance(semantic_input, Mapping):
        raise InvalidContinuationToken(
            "continuation_token semantic_input is invalid."
        )
    phenomenon = semantic_input.get("phenomenon")
    if not isinstance(phenomenon, Mapping):
        raise InvalidContinuationToken(
            "continuation_token phenomenon is invalid."
        )
    value = phenomenon.get("input")
    if not isinstance(value, str) or not value.strip():
        raise InvalidContinuationToken(
            "continuation_token source input is invalid."
        )
    return value.strip()


def require_continuation_core(state, surface):
    core_ref = state.get("core_ref")
    if not isinstance(core_ref, Mapping):
        raise InvalidContinuationToken(
            "continuation_token core_ref is invalid."
        )
    current = CoreReference.from_surface(surface).to_dict()
    if dict(core_ref) != current:
        raise ContinuationStateMismatch(
            "Continuation Core identity no longer matches the loaded Core Surface."
        )


def resume_semantic_input(state, resume):
    snapshot = state.get("semantic_input")
    if not isinstance(snapshot, Mapping) or set(snapshot) != SEMANTIC_INPUT_FIELDS:
        raise InvalidContinuationToken(
            "continuation_token SemanticInput contract is invalid."
        )
    hold = state.get("hold")
    if not isinstance(hold, Mapping):
        raise InvalidContinuationToken(
            "continuation_token HOLD state is invalid."
        )
    target_unknowns = _continuation_string_array(
        hold.get("unknowns", []),
        "hold.unknowns",
    )
    required_inputs = hold.get("required_inputs", [])
    if not isinstance(required_inputs, list):
        raise InvalidContinuationToken(
            "continuation_token required_inputs must be an array."
        )
    allowed_paths = {
        item.get("path")
        for item in required_inputs
        if isinstance(item, Mapping)
        and isinstance(item.get("path"), str)
    }
    operator_input = _normalize_operator_input(
        resume.get("operator_input"),
        target_unknowns,
    )
    unknown_paths = set(operator_input["values"]) - allowed_paths
    if unknown_paths:
        raise InvalidContinuationToken(
            "Operator input contains paths outside the signed HOLD request: "
            f"{sorted(unknown_paths)}"
        )
    unknown_resolutions = (
        set(operator_input["resolved_unknowns"]) - set(target_unknowns)
    )
    if unknown_resolutions:
        raise InvalidContinuationToken(
            "Operator input resolves unknowns outside the signed HOLD request."
        )

    facts = _continuation_object(snapshot.get("facts"), "facts")
    authority = _continuation_object(
        snapshot.get("authority"),
        "authority",
    )
    evidence = _continuation_object_array(
        snapshot.get("evidence"),
        "evidence",
    )
    for path, value in operator_input["values"].items():
        _apply_operator_value(facts, authority, path, value)
    evidence.append({
        "source": "operator",
        "kind": "hold_handoff",
        "statement": operator_input["statement"],
        "values": operator_input["values"],
        "resolved_unknowns": operator_input["resolved_unknowns"],
    })
    remaining_unknowns = [
        item
        for item in _continuation_string_array(
            snapshot.get("unknowns"),
            "unknowns",
        )
        if item not in operator_input["resolved_unknowns"]
    ]
    try:
        return SemanticInput(
            phenomenon=snapshot["phenomenon"],
            phase=snapshot["phase"],
            facts=facts,
            unknowns=remaining_unknowns,
            evidence=evidence,
            authority=authority,
            active_layers=snapshot["active_layers"],
            triggers=snapshot["triggers"],
            applicability_scopes=snapshot["applicability_scopes"],
            requested_norm_refs=snapshot["requested_norm_refs"],
            evaluate_inactive=snapshot["evaluate_inactive"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidContinuationToken(
            "continuation_token SemanticInput values are invalid."
        ) from exc


def trace_handoff(hold):
    if not isinstance(hold, Mapping):
        return None
    return {
        key: value
        for key, value in hold.items()
        if key != "continuation_token"
    }


def _hold_unknowns(candidate):
    values = list(candidate.unknowns)
    values.extend(
        unknown
        for result in candidate.norm_results
        for unknown in result.unknowns
    )
    values.extend(
        issue.message
        for issue in candidate.validation_issues
    )
    values.extend(
        conflict.reason
        for conflict in candidate.conflicts
        if conflict.disposition == "HOLD"
    )
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    if not result:
        result.append(
            "The Semantic Executor returned HOLD without a more specific "
            "material unknown."
        )
    return result


def _hold_question(unknowns, required_inputs):
    parts = []
    if unknowns:
        parts.append(
            "resolve " + "; ".join(unknowns[:5])
        )
    if required_inputs:
        field_labels = []
        for item in required_inputs[:5]:
            path = item["path"]
            expected = _suggested_requirement_value(item)
            if expected is None:
                field_labels.append(path)
            else:
                field_labels.append(
                    f"{path} = {json.dumps(expected, ensure_ascii=False)}"
                )
        parts.append(
            "confirm or provide " + ", ".join(field_labels)
        )
    return "Operator input required: " + "; ".join(parts) + "."


def _suggested_requirement_value(requirement):
    constraints = requirement.get("constraints", [])
    expected = [
        item["expected"]
        for item in constraints
        if isinstance(item, Mapping) and "expected" in item
    ]
    if expected and all(value == expected[0] for value in expected):
        return expected[0]
    return None


def _normalize_operator_input(value, target_unknowns):
    if isinstance(value, str):
        statement = value.strip()
        if not statement:
            raise InvalidContinuationToken(
                "resume.operator_input must not be empty."
            )
        return {
            "statement": statement,
            "values": {},
            "resolved_unknowns": list(target_unknowns),
        }
    if not isinstance(value, Mapping):
        raise InvalidContinuationToken(
            "resume.operator_input must be text or an object."
        )
    allowed_fields = {"statement", "values", "resolved_unknowns"}
    if not set(value).issubset(allowed_fields):
        raise InvalidContinuationToken(
            "resume.operator_input contains unsupported fields."
        )
    statement = value.get("statement", "")
    if not isinstance(statement, str):
        raise InvalidContinuationToken(
            "resume.operator_input.statement must be text."
        )
    statement = statement.strip()
    values = value.get("values", {})
    if not isinstance(values, Mapping):
        raise InvalidContinuationToken(
            "resume.operator_input.values must be an object."
        )
    values = {
        _operator_path(path): _operator_json_value(nested)
        for path, nested in values.items()
    }
    raw_resolved = value.get("resolved_unknowns")
    if raw_resolved is None:
        resolved_unknowns = list(target_unknowns)
    else:
        resolved_unknowns = _continuation_string_array(
            raw_resolved,
            "operator_input.resolved_unknowns",
        )
    if not statement and not values:
        raise InvalidContinuationToken(
            "resume.operator_input requires a statement or a confirmed value."
        )
    return {
        "statement": statement,
        "values": values,
        "resolved_unknowns": resolved_unknowns,
    }


def _operator_path(value):
    if not isinstance(value, str) or not value.strip():
        raise InvalidContinuationToken(
            "Operator input value paths must be non-empty strings."
        )
    parts = value.strip().split(".")
    if any(
        not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", part)
        for part in parts
    ):
        raise InvalidContinuationToken(
            f"Operator input path is invalid: {value!r}."
        )
    return ".".join(parts)


def _operator_json_value(value):
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidContinuationToken(
            "Operator input values must be JSON data."
        ) from exc
    if len(encoded) > MAX_OPERATOR_VALUE_CHARACTERS:
        raise InvalidContinuationToken(
            "An operator input value exceeds the size limit."
        )
    return value


def _apply_operator_value(facts, authority, path, value):
    parts = path.split(".")
    root = parts[0]
    if root in {"authority", "authorization"}:
        _set_nested(authority, parts[1:], value)
        _set_nested(facts, parts, value)
        return
    _set_nested(facts, parts, value)


def _set_nested(target, parts, value):
    if not parts:
        raise InvalidContinuationToken(
            "Operator input cannot replace a complete semantic container."
        )
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if nested is None:
            nested = {}
            current[part] = nested
        if not isinstance(nested, dict):
            raise InvalidContinuationToken(
                "Operator input path conflicts with existing semantic data."
            )
        current = nested
    current[parts[-1]] = value


def _continuation_object(value, label):
    if not isinstance(value, Mapping):
        raise InvalidContinuationToken(
            f"continuation_token {label} must be an object."
        )
    return json.loads(json.dumps(value))


def _continuation_object_array(value, label):
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping)
        for item in value
    ):
        raise InvalidContinuationToken(
            f"continuation_token {label} must be an object array."
        )
    return [
        _continuation_object(item, f"{label} item")
        for item in value
    ]


def _continuation_string_array(value, label):
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip()
        for item in value
    ):
        raise InvalidContinuationToken(
            f"continuation_token {label} must be a string array."
        )
    return list(dict.fromkeys(item.strip() for item in value))


def _canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContinuationUnavailable(
            "Continuation state is not canonical JSON data."
        ) from exc


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.b64decode(
        value + padding,
        altchars=b"-_",
        validate=True,
    )
