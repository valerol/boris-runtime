from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from semantic_executor import CoreReference, SemanticInput
from semantic_executor.uncertainty import OPERATOR_RESOLUTION_CLASS


CONTINUATION_VERSION = "boris-continuation/1.3"
HOLD_HANDOFF_VERSION = "boris-hold-handoff/1.3"
CONTINUATION_SECRET_ENV = "BORIS_CONTINUATION_SECRET"
CONTINUATION_TTL_ENV = "BORIS_CONTINUATION_TTL_SECONDS"
DEFAULT_CONTINUATION_TTL_SECONDS = 3600
MIN_CONTINUATION_SECRET_BYTES = 32
MAX_CONTINUATION_TOKEN_CHARACTERS = 262144
MAX_OPERATOR_VALUE_CHARACTERS = 2000
PROVIDE_INFORMATION = "PROVIDE_INFORMATION"
ALLOW_CONDITIONAL_PROCEEDING = "ALLOW_CONDITIONAL_PROCEEDING"
OPERATOR_RESOLUTION_MODES = frozenset({
    PROVIDE_INFORMATION,
    ALLOW_CONDITIONAL_PROCEEDING,
})
HOLD_RECORD_FIELDS = {
    "cycle_id",
    "return_state",
    "return_gate",
    "hold_reason",
    "scope",
    "source_refs",
    "unknowns",
    "evidence_refs",
    "open_debts",
    "state_hash",
}
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


class IncompleteOperatorResolution(ContinuationError):
    """Raised when operator input leaves a signed HOLD target unresolved."""


@dataclass(frozen=True, slots=True)
class ContinuationResume:
    semantic_input: SemanticInput
    cycle_id: str
    hold_record: Mapping
    precondition_resolution: Mapping


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
            **dict(state),
            "version": CONTINUATION_VERSION,
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
            "token_id": str(uuid4()),
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
        if (
            _base64url_encode(supplied_signature) != encoded_signature
            or _base64url_encode(payload_bytes) != encoded_payload
        ):
            raise InvalidContinuationToken(
                "continuation_token is not canonical base64url data."
            )
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
    cycle_id=None,
):
    required_inputs = candidate.trace.to_dict()["required_inputs"]
    semantic_unknowns = _semantic_unknown_resolutions(
        candidate,
        required_inputs,
    )
    predicate_inputs = _predicate_operator_inputs(required_inputs)
    if not semantic_unknowns and not predicate_inputs:
        raise ContinuationUnavailable(
            "Operator continuation cannot be issued without an "
            "operator-owned resolution target."
        )
    hold_reason = (
        "Runtime gate is HOLD because material information or a "
        "recoverable precondition remains unresolved."
    )
    conditional_proceeding_allowed = (
        _conditional_proceeding_allowed(
            semantic_unknowns,
            predicate_inputs,
        )
    )
    resolution_modes = [{
        "mode": PROVIDE_INFORMATION,
        "available": True,
        "effect": (
            "Add signed operator-supplied facts or observations and resolve "
            "every declared target before the same phase is recalculated."
        ),
        "preserves_unknowns": False,
    }, {
        "mode": ALLOW_CONDITIONAL_PROCEEDING,
        "available": conditional_proceeding_allowed,
        "effect": (
            "Resolve only the operator scope decision, preserve every unknown "
            "and open debt, and recalculate the same phase without forcing PASS."
        ),
        "preserves_unknowns": True,
    }]
    required_operator_input = {
        "question": _hold_question(
            semantic_unknowns,
            predicate_inputs,
            conditional_proceeding_allowed,
        ),
        "resolution_modes": resolution_modes,
        "semantic_unknowns": semantic_unknowns,
        "predicate_inputs": predicate_inputs,
        "response_contract": {
            "resolution_mode": (
                "Required. Use PROVIDE_INFORMATION, or "
                "ALLOW_CONDITIONAL_PROCEEDING only when that signed mode is "
                "available."
            ),
            "statement": (
                "Required for ALLOW_CONDITIONAL_PROCEEDING and for every "
                "resolved semantic unknown without a target_path."
            ),
            "values": (
                "Path-to-value object. Paths must be declared by a semantic "
                "unknown target_path or predicate_inputs. Must be empty for "
                "ALLOW_CONDITIONAL_PROCEEDING."
            ),
            "resolved_unknowns": (
                "Exact unknown_id values resolved by provided information. "
                "Must be empty for ALLOW_CONDITIONAL_PROCEEDING."
            ),
        },
    }
    open_debts = _hold_open_debts(
        candidate,
        required_inputs,
    )
    hold_record = build_hold_record(
        semantic_input=semantic_input,
        core_ref=candidate.core_ref.to_dict(),
        session_id=session_id,
        hold_reason=hold_reason,
        unknowns=candidate.unknowns,
        open_debts=open_debts,
        cycle_id=cycle_id,
    )
    blocking_precondition = _blocking_precondition(
        hold_record,
        resolution_modes,
    )
    token, claims = codec.issue({
        "session_id": session_id,
        "resume_count": resume_count,
        "semantic_input": semantic_input.to_prompt_dict(),
        "core_ref": candidate.core_ref.to_dict(),
        "hold": {
            "hold_record": hold_record,
            "blocking_precondition": blocking_precondition,
            "semantic_unknowns": semantic_unknowns,
            "predicate_inputs": predicate_inputs,
        },
    })
    return {
        "handoff_version": HOLD_HANDOFF_VERSION,
        "status": "operator_input_required",
        "reason": hold_reason,
        "hold_record": hold_record,
        "blocking_precondition": blocking_precondition,
        "required_operator_input": required_operator_input,
        "continuation_token": token,
        "expires_at": continuation_expiry_iso(claims),
        "resume_count": resume_count,
    }


def hold_requires_operator_input(candidate):
    if any(
        uncertainty.resolution_class == OPERATOR_RESOLUTION_CLASS
        for uncertainty in candidate.uncertainties
    ):
        return True
    return any(
        item.get("resolution_class") == OPERATOR_RESOLUTION_CLASS
        for item in candidate.trace.to_dict()["required_inputs"]
    )


def build_non_operator_hold(
    candidate,
    semantic_input,
    session_id,
    resume_count,
    cycle_id=None,
):
    grouped = {}
    for uncertainty in candidate.uncertainties:
        if uncertainty.resolution_class == OPERATOR_RESOLUTION_CLASS:
            continue
        grouped.setdefault(uncertainty.resolution_class, []).append(
            uncertainty.to_dict()
        )
    for item in candidate.trace.to_dict()["required_inputs"]:
        resolution_class = item.get("resolution_class")
        if resolution_class == OPERATOR_RESOLUTION_CLASS:
            continue
        grouped.setdefault(resolution_class, []).append({
            "target_path": item.get("path"),
            "norm_refs": item.get("norm_refs", []),
            "constraints": item.get("constraints", []),
            "uncertainty_ids": item.get("uncertainty_ids", []),
        })
    reason = (
        "Runtime gate is HOLD, but no unresolved target is owned by the "
        "operator. The conditional semantic candidate remains available."
    )
    required_inputs = candidate.trace.to_dict()["required_inputs"]
    hold_record = build_hold_record(
        semantic_input=semantic_input,
        core_ref=candidate.core_ref.to_dict(),
        session_id=session_id,
        hold_reason=reason,
        unknowns=candidate.unknowns,
        open_debts=_hold_open_debts(candidate, required_inputs),
        cycle_id=cycle_id,
    )
    blocking_precondition = _blocking_precondition(
        hold_record,
        [],
    )
    return {
        "handoff_version": HOLD_HANDOFF_VERSION,
        "status": "resolution_not_operator_owned",
        "reason": reason,
        "hold_record": hold_record,
        "blocking_precondition": blocking_precondition,
        "required_operator_input": None,
        "resolution_summary": {
            key: values
            for key, values in sorted(grouped.items())
            if key and values
        },
        "resume_count": resume_count,
    }


def build_hold_record(
    *,
    semantic_input,
    core_ref,
    session_id,
    hold_reason,
    unknowns,
    open_debts,
    cycle_id=None,
):
    resolved_cycle_id = (
        str(cycle_id).strip()
        if cycle_id is not None
        else str(uuid4())
    )
    if not resolved_cycle_id:
        raise ContinuationUnavailable(
            "HOLD cycle_id must be a non-empty string."
        )
    scope = list(
        semantic_input.applicability_scopes
        or (semantic_input.phase,)
    )
    source_refs = _declared_refs(
        semantic_input.to_prompt_dict()["phenomenon"],
        {"source_ref", "source_refs"},
    )
    evidence_refs = _declared_refs(
        semantic_input.to_prompt_dict()["evidence"],
        {
            "evidence_id",
            "evidence_ref",
            "evidence_refs",
            "source_ref",
        },
    )
    material = {
        "cycle_id": resolved_cycle_id,
        "return_state": semantic_input.phase,
        "return_gate": semantic_input.phase,
        "hold_reason": str(hold_reason).strip(),
        "scope": scope,
        "source_refs": source_refs,
        "unknowns": list(dict.fromkeys(str(item) for item in unknowns)),
        "evidence_refs": evidence_refs,
        "open_debts": list(
            dict.fromkeys(str(item) for item in open_debts)
        ),
    }
    state_material = {
        "core_ref": dict(core_ref),
        "semantic_input": semantic_input.to_prompt_dict(),
        "hold_record": material,
    }
    return {
        **material,
        "state_hash": hashlib.sha256(
            _canonical_json(state_material)
        ).hexdigest(),
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


def resume_hold(state, resume):
    snapshot = state.get("semantic_input")
    if not isinstance(snapshot, Mapping) or set(snapshot) != SEMANTIC_INPUT_FIELDS:
        raise InvalidContinuationToken(
            "continuation_token SemanticInput contract is invalid."
        )
    hold = state.get("hold")
    if not isinstance(hold, Mapping) or set(hold) != {
        "hold_record",
        "blocking_precondition",
        "semantic_unknowns",
        "predicate_inputs",
    }:
        raise InvalidContinuationToken(
            "continuation_token HOLD state is invalid."
        )
    hold_record = _continuation_hold_record(
        hold.get("hold_record"),
        snapshot,
        state.get("core_ref"),
    )
    blocking_precondition = _continuation_blocking_precondition(
        hold.get("blocking_precondition"),
        hold_record,
    )
    semantic_unknowns = _continuation_resolution_array(
        hold.get("semantic_unknowns", []),
        "hold.semantic_unknowns",
    )
    predicate_inputs = _continuation_predicate_input_array(
        hold.get("predicate_inputs", []),
        "hold.predicate_inputs",
    )
    allowed_paths = {
        item["target_path"]
        for item in (*semantic_unknowns, *predicate_inputs)
        if item.get("target_path") is not None
    }
    operator_input = _normalize_operator_input(
        resume.get("operator_input"),
    )
    unknown_paths = set(operator_input["values"]) - allowed_paths
    if unknown_paths:
        raise InvalidContinuationToken(
            "Operator input contains paths outside the signed HOLD request: "
            f"{sorted(unknown_paths)}"
        )
    unknown_resolutions = (
        set(operator_input["resolved_unknowns"])
        - {item["unknown_id"] for item in semantic_unknowns}
    )
    if unknown_resolutions:
        raise InvalidContinuationToken(
            "Operator input resolves unknowns outside the signed HOLD request."
        )
    resolution_mode = operator_input["resolution_mode"]
    available_modes = set(
        blocking_precondition["resolution_options"]
    )
    if resolution_mode not in available_modes:
        raise IncompleteOperatorResolution(
            f"{resolution_mode} is not available for this signed HOLD "
            "precondition."
        )
    if resolution_mode == PROVIDE_INFORMATION:
        _require_complete_operator_resolution(
            semantic_unknowns,
            predicate_inputs,
            operator_input,
        )
    else:
        _require_conditional_proceeding_resolution(
            semantic_unknowns,
            predicate_inputs,
            operator_input,
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
    if resolution_mode == PROVIDE_INFORMATION:
        for path, value in operator_input["values"].items():
            _apply_operator_value(facts, authority, path, value)
        evidence.append({
            "source": "operator",
            "kind": "hold_information_resolution",
            "resolution_mode": resolution_mode,
            "blocking_precondition_id": blocking_precondition[
                "precondition_id"
            ],
            "statement": operator_input["statement"],
            "values": operator_input["values"],
            "resolved_unknowns": operator_input["resolved_unknowns"],
            "hold_record": hold_record,
        })
        resolved_descriptions = {
            item["description"]
            for item in semantic_unknowns
            if item["unknown_id"] in operator_input["resolved_unknowns"]
        }
        resolved_descriptions.update(
            description
            for item in predicate_inputs
            if item["target_path"] in operator_input["values"]
            for description in item["uncertainty_descriptions"]
        )
    else:
        preserved_unknown_ids = [
            item["unknown_id"]
            for item in semantic_unknowns
        ]
        evidence.append({
            "source": "operator",
            "kind": "hold_precondition_resolution",
            "resolution_mode": resolution_mode,
            "blocking_precondition_id": blocking_precondition[
                "precondition_id"
            ],
            "statement": operator_input["statement"],
            "unknowns_preserved": preserved_unknown_ids,
            "hold_record": hold_record,
            "does_not_establish_facts": True,
            "does_not_force_gate": "PASS",
        })
        resolved_descriptions = set()
    remaining_unknowns = [
        item
        for item in _continuation_string_array(
            snapshot.get("unknowns"),
            "unknowns",
        )
        if item not in resolved_descriptions
    ]
    try:
        semantic_input = SemanticInput(
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
    return ContinuationResume(
        semantic_input=semantic_input,
        cycle_id=hold_record["cycle_id"],
        hold_record=hold_record,
        precondition_resolution={
            "precondition_id": blocking_precondition[
                "precondition_id"
            ],
            "resolution_mode": resolution_mode,
            "statement": operator_input["statement"],
            "preserved_unknowns": (
                list(hold_record["unknowns"])
                if resolution_mode == ALLOW_CONDITIONAL_PROCEEDING
                else list(remaining_unknowns)
            ),
            "return_state": hold_record["return_state"],
            "return_gate": hold_record["return_gate"],
            "preserved_hold_record": hold_record,
            "gate_recheck_required": True,
            "gate_forced": False,
        },
    )


def trace_handoff(hold):
    if not isinstance(hold, Mapping):
        return None
    return {
        key: value
        for key, value in hold.items()
        if key != "continuation_token"
    }


def _semantic_unknown_resolutions(candidate, required_inputs):
    result = []
    predicate_paths = {
        item.get("path")
        for item in required_inputs
        if item.get("resolution_class") == OPERATOR_RESOLUTION_CLASS
    }
    for uncertainty in candidate.uncertainties:
        if uncertainty.resolution_class != OPERATOR_RESOLUTION_CLASS:
            continue
        target_path = uncertainty.target_path
        if target_path in predicate_paths:
            continue
        result.append({
            "unknown_id": uncertainty.uncertainty_id,
            "description": uncertainty.description,
            "target_path": target_path,
            "resolution_kind": (
                "operator_value"
                if target_path is not None
                else "operator_statement"
            ),
            "expected_type": (
                _expected_path_type(target_path, required_inputs)
                if target_path is not None
                else "text"
            ),
            "norm_refs": list(uncertainty.norm_refs),
            "core_refs": list(uncertainty.core_refs),
            "question": uncertainty.operator_question,
        })
    return result


def _predicate_operator_inputs(required_inputs):
    result = []
    for item in required_inputs:
        if (
            item.get("resolution_class")
            != OPERATOR_RESOLUTION_CLASS
        ):
            continue
        path = _operator_path(item.get("path"))
        constraints = item.get("constraints", [])
        if not isinstance(constraints, list):
            raise ContinuationUnavailable(
                "Semantic Executor required_inputs constraints are invalid."
            )
        result.append({
            "input_id": path,
            "target_path": path,
            "resolution_kind": "operator_observation",
            "expected_type": _constraint_type(constraints),
            "norm_refs": list(item.get("norm_refs", [])),
            "constraints": constraints,
            "uncertainty_ids": list(
                item.get("uncertainty_ids", [])
            ),
            "uncertainty_descriptions": list(
                item.get("uncertainty_descriptions", [])
            ),
            "question": (
                f"Provide the observed value for Core selector {path}. "
                "The value that makes a predicate true is not assumed."
            ),
        })
    return result


def _conditional_proceeding_allowed(
    semantic_unknowns,
    predicate_inputs,
):
    return (
        bool(semantic_unknowns)
        and not predicate_inputs
        and all(
            item["target_path"] is None
            and not item["norm_refs"]
            and not item["core_refs"]
            for item in semantic_unknowns
        )
    )


def _hold_open_debts(candidate, required_inputs):
    return list(dict.fromkeys((
        *(
            f"uncertainty:{uncertainty.uncertainty_id}"
            for uncertainty in candidate.uncertainties
        ),
        *(
            f"required_input:{item.get('path')}"
            for item in required_inputs
            if item.get("path")
        ),
    )))


def _blocking_precondition(hold_record, resolution_modes):
    available_modes = [
        item["mode"]
        for item in resolution_modes
        if item.get("available")
    ]
    digest = hashlib.sha256(_canonical_json({
        "cycle_id": hold_record["cycle_id"],
        "return_state": hold_record["return_state"],
        "state_hash": hold_record["state_hash"],
        "resolution_options": available_modes,
    })).hexdigest()[:24]
    return {
        "precondition_id": f"hold-precondition-{digest}",
        "condition": "RECOVERABLE_PRECONDITION_UNRESOLVED",
        "status": "UNRESOLVED",
        "description": hold_record["hold_reason"],
        "resolution_options": available_modes,
    }


def _hold_question(
    semantic_unknowns,
    predicate_inputs,
    conditional_proceeding_allowed,
):
    parts = []
    if semantic_unknowns:
        parts.append(
            "resolve "
            + "; ".join(
                item["description"]
                for item in semantic_unknowns[:5]
            )
        )
    if predicate_inputs:
        parts.append(
            "provide observed Core selector values for "
            + ", ".join(
                item["target_path"]
                for item in predicate_inputs[:5]
            )
        )
    question = "Operator input required: " + "; ".join(parts) + "."
    if conditional_proceeding_allowed:
        question += (
            " You may instead authorize bounded conditional recalculation; "
            "this preserves every unknown and does not force PASS."
        )
    return question


def _declared_refs(value, accepted_keys):
    result = []

    def visit(item):
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if key in accepted_keys:
                    if isinstance(nested, str) and nested.strip():
                        result.append(nested.strip())
                    elif isinstance(nested, list):
                        result.extend(
                            ref.strip()
                            for ref in nested
                            if isinstance(ref, str) and ref.strip()
                        )
                else:
                    visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return list(dict.fromkeys(result))


def _normalize_operator_input(value):
    if not isinstance(value, Mapping):
        raise InvalidContinuationToken(
            "resume.operator_input must be an object."
        )
    allowed_fields = {
        "resolution_mode",
        "statement",
        "values",
        "resolved_unknowns",
    }
    if not set(value).issubset(allowed_fields):
        raise InvalidContinuationToken(
            "resume.operator_input contains unsupported fields."
        )
    resolution_mode = value.get("resolution_mode")
    if resolution_mode not in OPERATOR_RESOLUTION_MODES:
        raise InvalidContinuationToken(
            "resume.operator_input.resolution_mode is invalid."
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
        resolved_unknowns = []
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
        "resolution_mode": resolution_mode,
        "statement": statement,
        "values": values,
        "resolved_unknowns": resolved_unknowns,
    }


def _require_complete_operator_resolution(
    semantic_unknowns,
    predicate_inputs,
    operator_input,
):
    resolved_unknowns = set(operator_input["resolved_unknowns"])
    supplied_paths = set(operator_input["values"])
    missing = []
    for item in semantic_unknowns:
        unknown_id = item["unknown_id"]
        if unknown_id not in resolved_unknowns:
            missing.append(f"semantic_unknown:{unknown_id}")
            continue
        target_path = item["target_path"]
        if target_path is not None and target_path not in supplied_paths:
            missing.append(f"value:{target_path}")
        if target_path is None and not operator_input["statement"]:
            missing.append(f"statement:{unknown_id}")
    for item in predicate_inputs:
        target_path = item["target_path"]
        if target_path not in supplied_paths:
            missing.append(f"predicate_input:{target_path}")
    if missing:
        raise IncompleteOperatorResolution(
            "Operator input does not close every signed HOLD target: "
            f"{sorted(set(missing))}"
        )


def _require_conditional_proceeding_resolution(
    semantic_unknowns,
    predicate_inputs,
    operator_input,
):
    if predicate_inputs or any(
        item["target_path"] is not None
        or item["norm_refs"]
        or item["core_refs"]
        for item in semantic_unknowns
    ):
        raise IncompleteOperatorResolution(
            "Conditional proceeding cannot replace a signed value, authority, "
            "Core reference, or norm-linked evidence requirement."
        )
    if not operator_input["statement"]:
        raise IncompleteOperatorResolution(
            "Conditional proceeding requires an explicit operator statement."
        )
    if operator_input["values"] or operator_input["resolved_unknowns"]:
        raise InvalidContinuationToken(
            "Conditional proceeding must not provide values or mark unknowns "
            "resolved."
        )


def _expected_path_type(path, required_inputs):
    matching = [
        item.get("constraints", [])
        for item in required_inputs
        if item.get("path") == path
    ]
    if not matching:
        return "json"
    return _constraint_type(matching[0])


def _constraint_type(constraints):
    values = []
    for constraint in constraints:
        if not isinstance(constraint, Mapping):
            continue
        if "expected" in constraint:
            values.append(constraint["expected"])
        elif "allowed_values" in constraint:
            allowed = constraint["allowed_values"]
            if isinstance(allowed, list):
                values.extend(allowed)
        elif "minimum" in constraint:
            values.append(constraint["minimum"])
    value_types = {
        _json_type_name(value)
        for value in values
    }
    return value_types.pop() if len(value_types) == 1 else "json"


def _json_type_name(value):
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return "json"


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


def _continuation_resolution_array(value, label):
    items = _continuation_object_array(value, label)
    required = {
        "unknown_id",
        "description",
        "target_path",
        "resolution_kind",
        "expected_type",
        "norm_refs",
        "core_refs",
        "question",
    }
    result = []
    seen = set()
    for index, item in enumerate(items):
        if set(item) != required:
            raise InvalidContinuationToken(
                f"continuation_token {label}[{index}] fields are invalid."
            )
        unknown_id = continuation_text(item, "unknown_id")
        if unknown_id in seen:
            raise InvalidContinuationToken(
                f"continuation_token {label} contains duplicate unknown_id."
            )
        seen.add(unknown_id)
        target_path = item["target_path"]
        if target_path is not None:
            target_path = _operator_path(target_path)
        result.append({
            **item,
            "unknown_id": unknown_id,
            "description": continuation_text(item, "description"),
            "target_path": target_path,
            "resolution_kind": continuation_text(
                item,
                "resolution_kind",
            ),
            "expected_type": continuation_text(item, "expected_type"),
            "norm_refs": _continuation_string_array(
                item["norm_refs"],
                f"{label}[{index}].norm_refs",
            ),
            "core_refs": _continuation_string_array(
                item["core_refs"],
                f"{label}[{index}].core_refs",
            ),
            "question": continuation_text(item, "question"),
        })
    return result


def _continuation_hold_record(value, semantic_input, core_ref):
    if not isinstance(value, Mapping) or set(value) != HOLD_RECORD_FIELDS:
        raise InvalidContinuationToken(
            "continuation_token hold.hold_record fields are invalid."
        )
    record = {
        "cycle_id": continuation_text(value, "cycle_id"),
        "return_state": continuation_text(value, "return_state"),
        "return_gate": continuation_text(value, "return_gate"),
        "hold_reason": continuation_text(value, "hold_reason"),
        "scope": _continuation_string_array(
            value["scope"],
            "hold.hold_record.scope",
        ),
        "source_refs": _continuation_string_array(
            value["source_refs"],
            "hold.hold_record.source_refs",
        ),
        "unknowns": _continuation_string_array(
            value["unknowns"],
            "hold.hold_record.unknowns",
        ),
        "evidence_refs": _continuation_string_array(
            value["evidence_refs"],
            "hold.hold_record.evidence_refs",
        ),
        "open_debts": _continuation_string_array(
            value["open_debts"],
            "hold.hold_record.open_debts",
        ),
        "state_hash": continuation_text(value, "state_hash"),
    }
    if (
        record["return_state"] != semantic_input.get("phase")
        or record["return_gate"] != semantic_input.get("phase")
    ):
        raise InvalidContinuationToken(
            "continuation_token HOLD return state or gate is invalid."
        )
    if not isinstance(core_ref, Mapping):
        raise InvalidContinuationToken(
            "continuation_token core_ref is invalid."
        )
    state_material = {
        "core_ref": dict(core_ref),
        "semantic_input": dict(semantic_input),
        "hold_record": {
            key: nested
            for key, nested in record.items()
            if key != "state_hash"
        },
    }
    expected_hash = hashlib.sha256(
        _canonical_json(state_material)
    ).hexdigest()
    if not hmac.compare_digest(record["state_hash"], expected_hash):
        raise InvalidContinuationToken(
            "continuation_token HOLD state_hash is invalid."
        )
    return record


def _continuation_blocking_precondition(value, hold_record):
    required = {
        "precondition_id",
        "condition",
        "status",
        "description",
        "resolution_options",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise InvalidContinuationToken(
            "continuation_token blocking precondition fields are invalid."
        )
    condition = continuation_text(value, "condition")
    status = continuation_text(value, "status")
    description = continuation_text(value, "description")
    options = _continuation_string_array(
        value["resolution_options"],
        "hold.blocking_precondition.resolution_options",
    )
    if (
        condition != "RECOVERABLE_PRECONDITION_UNRESOLVED"
        or status != "UNRESOLVED"
        or description != hold_record["hold_reason"]
        or not set(options).issubset(OPERATOR_RESOLUTION_MODES)
    ):
        raise InvalidContinuationToken(
            "continuation_token blocking precondition is invalid."
        )
    return {
        "precondition_id": continuation_text(
            value,
            "precondition_id",
        ),
        "condition": condition,
        "status": status,
        "description": description,
        "resolution_options": options,
    }


def _continuation_predicate_input_array(value, label):
    items = _continuation_object_array(value, label)
    required = {
        "input_id",
        "target_path",
        "resolution_kind",
        "expected_type",
        "norm_refs",
        "constraints",
        "uncertainty_ids",
        "uncertainty_descriptions",
        "question",
    }
    result = []
    seen = set()
    for index, item in enumerate(items):
        if set(item) != required:
            raise InvalidContinuationToken(
                f"continuation_token {label}[{index}] fields are invalid."
            )
        target_path = _operator_path(item["target_path"])
        input_id = continuation_text(item, "input_id")
        if input_id != target_path:
            raise InvalidContinuationToken(
                f"continuation_token {label}[{index}] input_id is invalid."
            )
        if input_id in seen:
            raise InvalidContinuationToken(
                f"continuation_token {label} contains duplicate input_id."
            )
        seen.add(input_id)
        constraints = item["constraints"]
        if not isinstance(constraints, list) or not all(
            isinstance(constraint, Mapping)
            for constraint in constraints
        ):
            raise InvalidContinuationToken(
                f"continuation_token {label}[{index}].constraints is invalid."
            )
        result.append({
            **item,
            "input_id": input_id,
            "target_path": target_path,
            "resolution_kind": continuation_text(
                item,
                "resolution_kind",
            ),
            "expected_type": continuation_text(item, "expected_type"),
            "norm_refs": _continuation_string_array(
                item["norm_refs"],
                f"{label}[{index}].norm_refs",
            ),
            "uncertainty_ids": _continuation_string_array(
                item["uncertainty_ids"],
                f"{label}[{index}].uncertainty_ids",
            ),
            "uncertainty_descriptions": _continuation_string_array(
                item["uncertainty_descriptions"],
                f"{label}[{index}].uncertainty_descriptions",
            ),
            "question": continuation_text(item, "question"),
        })
    return result


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
