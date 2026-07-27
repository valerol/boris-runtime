from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from application.phase_output import (
    PhaseOutputContract,
    PhaseOutputContractError,
)
from semantic_executor import SemanticInput
from semantic_executor.calculator import (
    MAX_SEMANTIC_PROMPT_CHARACTERS,
    build_semantic_calculation_prompt,
)
from semantic_executor.models import SemanticView, thaw_value


HOST_WORK_ORDER_VERSION = "boris-semantic-work-order/0.4"
HOST_WORK_ORDER_TOKEN_VERSION = "boris-host-work-order-token/0.3"
HOST_WORK_ORDER_SECRET_ENV = "BORIS_HOST_EXECUTOR_SECRET"
HOST_WORK_ORDER_TTL_ENV = "BORIS_HOST_WORK_ORDER_TTL_SECONDS"
DEFAULT_HOST_WORK_ORDER_TTL_SECONDS = 900
MIN_HOST_WORK_ORDER_SECRET_BYTES = 32
MAX_HOST_WORK_ORDER_TOKEN_CHARACTERS = 16384
MAX_HOST_SEMANTIC_INPUT_CHARACTERS = 1_000_000
MAX_HOST_SEMANTIC_RESULT_CHARACTERS = 4_000_000
MAX_PENDING_HOST_WORK_ORDERS = 128
HOST_SEMANTIC_PROVIDER = "CHATGPT_HOST_ONLY"
COMPILATION_WORK_ORDER = "COMPILATION"
CALCULATION_WORK_ORDER = "CALCULATION"
HOST_EXECUTOR_LIMITATIONS = (
    "contract_isolation_only",
    "chat_context_not_isolated",
    "host_model_identity_not_attested",
    "host_context_capacity_not_attested",
    "single_process_registry",
    "single_use_submission",
)


class HostExecutorError(RuntimeError):
    """Base error for the experimental ChatGPT host executor."""


class HostExecutorUnavailable(HostExecutorError):
    """Raised when the host executor cannot issue or resolve work orders."""


class InvalidHostWorkOrder(HostExecutorError):
    """Raised when a work-order token is malformed, invalid, or expired."""


class HostWorkOrderStateMismatch(HostExecutorError):
    """Raised when submitted work-order material does not match signed state."""


class HostWorkOrderAlreadyConsumed(HostExecutorError):
    """Raised when a work order is submitted more than once."""


@dataclass(slots=True)
class HostWorkOrderState:
    work_order_id: str
    work_order_type: str
    session_id: str
    source_text: str
    resume_count: int
    resumed: bool
    core_ref: Mapping[str, str]
    attestation_sha256: str
    semantic_prompt_sha256: str
    response_schema_sha256: str
    semantic_source_sha256: str
    compiler_catalog_sha256: str
    semantic_input_sha256: str
    semantic_view_sha256: str
    expires_at: int
    semantic_input: SemanticInput | None = None
    source_material: Mapping[str, Any] | None = None
    compiler_catalog: Mapping[str, Any] | None = None
    correction_count: int = 0
    parent_work_order_id: str | None = None
    correction_issues: tuple[Mapping[str, Any], ...] = ()
    consumed: bool = False


class HostWorkOrderCodec:
    def __init__(
        self,
        secret: str | bytes,
        ttl_seconds: int = DEFAULT_HOST_WORK_ORDER_TTL_SECONDS,
        clock=None,
    ):
        secret_bytes = (
            secret.encode("utf-8")
            if isinstance(secret, str)
            else secret
        )
        if (
            not isinstance(secret_bytes, bytes)
            or len(secret_bytes) < MIN_HOST_WORK_ORDER_SECRET_BYTES
        ):
            raise HostExecutorUnavailable(
                f"{HOST_WORK_ORDER_SECRET_ENV} must contain at least "
                f"{MIN_HOST_WORK_ORDER_SECRET_BYTES} bytes."
            )
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or ttl_seconds < 60
            or ttl_seconds > 86400
        ):
            raise HostExecutorUnavailable(
                f"{HOST_WORK_ORDER_TTL_ENV} must be an integer from 60 "
                "through 86400."
            )
        self._secret = secret_bytes
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time

    @classmethod
    def from_environment(cls) -> "HostWorkOrderCodec":
        secret = os.getenv(HOST_WORK_ORDER_SECRET_ENV, "")
        raw_ttl = os.getenv(HOST_WORK_ORDER_TTL_ENV, "").strip()
        if raw_ttl:
            try:
                ttl_seconds = int(raw_ttl)
            except ValueError as exc:
                raise HostExecutorUnavailable(
                    f"{HOST_WORK_ORDER_TTL_ENV} must be an integer."
                ) from exc
        else:
            ttl_seconds = DEFAULT_HOST_WORK_ORDER_TTL_SECONDS
        return cls(secret, ttl_seconds=ttl_seconds)

    def issue(self, claims: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        now = int(self._clock())
        signed_claims = {
            "version": HOST_WORK_ORDER_TOKEN_VERSION,
            "issued_at": now,
            "expires_at": now + self.ttl_seconds,
            **dict(claims),
        }
        encoded_payload = _base64url_encode(_canonical_json(signed_claims))
        signature = hmac.new(
            self._secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        token = f"hw1.{encoded_payload}.{_base64url_encode(signature)}"
        if len(token) > MAX_HOST_WORK_ORDER_TOKEN_CHARACTERS:
            raise HostExecutorUnavailable(
                "Host work-order token exceeds the size limit."
            )
        return token, signed_claims

    def verify(self, token: str) -> dict[str, Any]:
        if not isinstance(token, str) or not token.strip():
            raise InvalidHostWorkOrder(
                "work_order_token must be a non-empty string."
            )
        if len(token) > MAX_HOST_WORK_ORDER_TOKEN_CHARACTERS:
            raise InvalidHostWorkOrder(
                "work_order_token exceeds the size limit."
            )
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "hw1":
            raise InvalidHostWorkOrder(
                "work_order_token has an unsupported format."
            )
        encoded_payload, encoded_signature = parts[1], parts[2]
        try:
            supplied_signature = _base64url_decode(encoded_signature)
            payload_bytes = _base64url_decode(encoded_payload)
        except (UnicodeEncodeError, ValueError) as exc:
            raise InvalidHostWorkOrder(
                "work_order_token is not valid base64url data."
            ) from exc
        if (
            _base64url_encode(supplied_signature) != encoded_signature
            or _base64url_encode(payload_bytes) != encoded_payload
        ):
            raise InvalidHostWorkOrder(
                "work_order_token is not canonical base64url data."
            )
        expected_signature = hmac.new(
            self._secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(
            supplied_signature,
            expected_signature,
        ):
            raise InvalidHostWorkOrder(
                "work_order_token signature is invalid."
            )
        try:
            claims = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidHostWorkOrder(
                "work_order_token payload is invalid."
            ) from exc
        if not isinstance(claims, dict):
            raise InvalidHostWorkOrder(
                "work_order_token payload must be an object."
            )
        if claims.get("version") != HOST_WORK_ORDER_TOKEN_VERSION:
            raise InvalidHostWorkOrder(
                "work_order_token version is unsupported."
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
            raise InvalidHostWorkOrder(
                "work_order_token lifetime is invalid."
            )
        if int(self._clock()) >= expires_at:
            raise InvalidHostWorkOrder(
                "work_order_token has expired."
            )
        return claims


class InMemoryHostWorkOrderRegistry:
    """Bounded single-process registry for the host-executor proof of concept."""

    def __init__(
        self,
        *,
        clock=None,
        maximum_entries: int = MAX_PENDING_HOST_WORK_ORDERS,
    ):
        self._clock = clock or time.time
        self._maximum_entries = maximum_entries
        self._entries: dict[str, HostWorkOrderState] = {}
        self._lock = threading.Lock()

    def register(self, state: HostWorkOrderState) -> None:
        with self._lock:
            self._purge_expired()
            if len(self._entries) >= self._maximum_entries:
                raise HostExecutorUnavailable(
                    "The in-memory host work-order registry is full."
                )
            if state.work_order_id in self._entries:
                raise HostExecutorUnavailable(
                    "A duplicate host work-order ID was generated."
                )
            self._entries[state.work_order_id] = state

    def consume(self, work_order_id: str) -> HostWorkOrderState:
        with self._lock:
            state = self._entries.get(work_order_id)
            if state is None:
                self._purge_expired()
                raise InvalidHostWorkOrder(
                    "Host work order is unavailable in this Runtime process."
                )
            if int(self._clock()) >= state.expires_at:
                del self._entries[work_order_id]
                raise InvalidHostWorkOrder(
                    "Host work order has expired."
                )
            if state.consumed:
                raise HostWorkOrderAlreadyConsumed(
                    "Host work order has already been submitted."
                )
            state.consumed = True
            return state

    def _purge_expired(self) -> None:
        now = int(self._clock())
        expired = [
            work_order_id
            for work_order_id, state in self._entries.items()
            if now >= state.expires_at
        ]
        for work_order_id in expired:
            del self._entries[work_order_id]


class SubmittedSemanticCalculator:
    """Calculator port that returns one ChatGPT-hosted submitted result."""

    def __init__(self, semantic_result: Mapping[str, Any]):
        if not isinstance(semantic_result, Mapping):
            raise InvalidHostWorkOrder(
                "semantic_result must be one JSON object."
            )
        self.semantic_result = dict(semantic_result)
        try:
            encoded = _canonical_json(self.semantic_result)
        except (RecursionError, TypeError, ValueError) as exc:
            raise InvalidHostWorkOrder(
                "semantic_result must be JSON-serializable."
            ) from exc
        if len(encoded) > MAX_HOST_SEMANTIC_RESULT_CHARACTERS:
            raise InvalidHostWorkOrder(
                "semantic_result exceeds the host submission size limit."
            )

    def calculate(
        self,
        _view: SemanticView,
        _semantic_input: SemanticInput,
    ) -> dict[str, Any]:
        return self.semantic_result


def validate_host_submission_payload(
    value: Mapping[str, Any],
    *,
    field_name: str,
    maximum_characters: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidHostWorkOrder(
            f"{field_name} must be one JSON object."
        )
    payload = dict(value)
    try:
        encoded = _canonical_json(payload)
    except (RecursionError, TypeError, ValueError) as exc:
        raise InvalidHostWorkOrder(
            f"{field_name} must be JSON-serializable."
        ) from exc
    if len(encoded) > maximum_characters:
        raise InvalidHostWorkOrder(
            f"{field_name} exceeds the host submission size limit."
        )
    return payload


def build_host_compilation_work_order(
    *,
    codec: HostWorkOrderCodec,
    registry: InMemoryHostWorkOrderRegistry,
    source_material: Mapping[str, Any],
    compiler_catalog: Mapping[str, Any],
    semantic_prompt: str,
    response_schema: Mapping[str, Any],
    session_id: str,
    source_text: str,
    core_ref: Mapping[str, str],
    resume_count: int,
    attestation_sha256: str,
) -> dict[str, Any]:
    source_payload = dict(source_material)
    catalog_payload = dict(compiler_catalog)
    schema_payload = dict(response_schema)
    semantic_source_sha256 = canonical_sha256(source_payload)
    compiler_catalog_sha256 = canonical_sha256(catalog_payload)
    semantic_prompt_sha256 = text_sha256(semantic_prompt)
    response_schema_sha256 = canonical_sha256(schema_payload)
    work_order_id = str(uuid4())
    claims = {
        "work_order_id": work_order_id,
        "work_order_type": COMPILATION_WORK_ORDER,
        "session_id": session_id,
        "semantic_provider": HOST_SEMANTIC_PROVIDER,
        "core_ref": dict(core_ref),
        "attestation_sha256": attestation_sha256,
        "semantic_source_sha256": semantic_source_sha256,
        "compiler_catalog_sha256": compiler_catalog_sha256,
        "semantic_prompt_sha256": semantic_prompt_sha256,
        "response_schema_sha256": response_schema_sha256,
    }
    token, signed_claims = codec.issue(claims)
    registry.register(HostWorkOrderState(
        work_order_id=work_order_id,
        work_order_type=COMPILATION_WORK_ORDER,
        session_id=session_id,
        source_text=source_text,
        resume_count=resume_count,
        resumed=False,
        core_ref=dict(core_ref),
        attestation_sha256=attestation_sha256,
        semantic_prompt_sha256=semantic_prompt_sha256,
        response_schema_sha256=response_schema_sha256,
        semantic_source_sha256=semantic_source_sha256,
        compiler_catalog_sha256=compiler_catalog_sha256,
        semantic_input_sha256="",
        semantic_view_sha256="",
        expires_at=signed_claims["expires_at"],
        source_material=source_payload,
        compiler_catalog=catalog_payload,
    ))
    return _host_work_order_envelope(
        work_order_id=work_order_id,
        work_order_type=COMPILATION_WORK_ORDER,
        session_id=session_id,
        core_ref=dict(core_ref),
        signed_claims=signed_claims,
        semantic_prompt=semantic_prompt,
        response_schema=schema_payload,
        bindings={
            "attestation_sha256": attestation_sha256,
            "semantic_source_sha256": semantic_source_sha256,
            "compiler_catalog_sha256": compiler_catalog_sha256,
            "semantic_prompt_sha256": semantic_prompt_sha256,
            "response_schema_sha256": response_schema_sha256,
        },
        token=token,
        submission_field="semantic_input",
    )


def build_host_work_order(
    *,
    codec: HostWorkOrderCodec,
    registry: InMemoryHostWorkOrderRegistry,
    semantic_input: SemanticInput,
    view: SemanticView,
    session_id: str,
    source_text: str,
    resume_count: int,
    resumed: bool,
    attestation_sha256: str,
    correction_count: int = 0,
    parent_work_order_id: str | None = None,
    correction_issues: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    if correction_count not in {0, 1}:
        raise HostExecutorUnavailable(
            "Host semantic submission permits at most one correction."
        )
    if correction_count == 0 and (
        parent_work_order_id is not None or correction_issues
    ):
        raise HostExecutorUnavailable(
            "Initial calculation work order cannot contain correction state."
        )
    if correction_count == 1 and (
        not parent_work_order_id or not correction_issues
    ):
        raise HostExecutorUnavailable(
            "Correction work order requires one parent and explicit issues."
        )
    base_semantic_prompt = build_semantic_calculation_prompt(
        view,
        semantic_input,
    )
    try:
        phase_output_contract = PhaseOutputContract.from_view(view)
    except PhaseOutputContractError as exc:
        raise HostExecutorUnavailable(
            "The verified Core does not expose an unambiguous phase output "
            f"contract for {view.phase}."
        ) from exc
    semantic_prompt = _calculation_prompt(
        base_semantic_prompt,
        phase_output_contract=phase_output_contract,
        correction_count=correction_count,
        parent_work_order_id=parent_work_order_id,
        correction_issues=correction_issues,
    )
    if len(semantic_prompt) > MAX_SEMANTIC_PROMPT_CHARACTERS:
        raise HostExecutorUnavailable(
            "Semantic calculation prompt exceeds the Phase 4F size limit."
        )
    response_schema = semantic_calculation_response_schema(
        view,
        phase_output_contract=phase_output_contract,
    )
    core_ref = view.core_ref.to_dict()
    semantic_input_sha256 = canonical_sha256(
        semantic_input.to_prompt_dict()
    )
    semantic_view_sha256 = canonical_sha256(view.to_prompt_dict())
    semantic_prompt_sha256 = text_sha256(semantic_prompt)
    response_schema_sha256 = canonical_sha256(response_schema)
    work_order_id = str(uuid4())
    claims = {
        "work_order_id": work_order_id,
        "work_order_type": CALCULATION_WORK_ORDER,
        "session_id": session_id,
        "semantic_provider": HOST_SEMANTIC_PROVIDER,
        "phase": view.phase,
        "minimum_context_window_tokens": int(
            view.execution_context.get(
                "minimum_context_window_tokens",
                0,
            )
            or 0
        ),
        "core_ref": core_ref,
        "attestation_sha256": attestation_sha256,
        "semantic_input_sha256": semantic_input_sha256,
        "semantic_view_sha256": semantic_view_sha256,
        "semantic_prompt_sha256": semantic_prompt_sha256,
        "response_schema_sha256": response_schema_sha256,
        "correction_count": correction_count,
    }
    if parent_work_order_id is not None:
        claims["parent_work_order_id"] = parent_work_order_id
    token, signed_claims = codec.issue(claims)
    registry.register(HostWorkOrderState(
        work_order_id=work_order_id,
        work_order_type=CALCULATION_WORK_ORDER,
        session_id=session_id,
        source_text=source_text,
        resume_count=resume_count,
        resumed=resumed,
        core_ref=core_ref,
        attestation_sha256=attestation_sha256,
        semantic_prompt_sha256=semantic_prompt_sha256,
        response_schema_sha256=response_schema_sha256,
        semantic_source_sha256="",
        compiler_catalog_sha256="",
        semantic_input_sha256=semantic_input_sha256,
        semantic_view_sha256=semantic_view_sha256,
        expires_at=signed_claims["expires_at"],
        semantic_input=semantic_input,
        correction_count=correction_count,
        parent_work_order_id=parent_work_order_id,
        correction_issues=tuple(
            dict(issue)
            for issue in correction_issues
        ),
    ))
    return _host_work_order_envelope(
        work_order_id=work_order_id,
        work_order_type=CALCULATION_WORK_ORDER,
        session_id=session_id,
        core_ref=core_ref,
        signed_claims=signed_claims,
        semantic_prompt=semantic_prompt,
        response_schema=response_schema,
        bindings={
            "attestation_sha256": attestation_sha256,
            "semantic_input_sha256": semantic_input_sha256,
            "semantic_view_sha256": semantic_view_sha256,
            "semantic_prompt_sha256": semantic_prompt_sha256,
            "response_schema_sha256": response_schema_sha256,
        },
        token=token,
        submission_field="semantic_result",
        phase=view.phase,
        minimum_context_window_tokens=signed_claims[
            "minimum_context_window_tokens"
        ],
        phase_output_contract=phase_output_contract.to_dict(),
        correction_count=correction_count,
        parent_work_order_id=parent_work_order_id,
        correction_issues=correction_issues,
    )


def _host_work_order_envelope(
    *,
    work_order_id: str,
    work_order_type: str,
    session_id: str,
    core_ref: Mapping[str, str],
    signed_claims: Mapping[str, Any],
    semantic_prompt: str,
    response_schema: Mapping[str, Any],
    bindings: Mapping[str, str],
    token: str,
    submission_field: str,
    phase: str | None = None,
    minimum_context_window_tokens: int = 0,
    phase_output_contract: Mapping[str, Any] | None = None,
    correction_count: int = 0,
    parent_work_order_id: str | None = None,
    correction_issues: tuple[Mapping[str, Any], ...] = (),
) -> dict[str, Any]:
    envelope = {
        "work_order_version": HOST_WORK_ORDER_VERSION,
        "work_order_id": work_order_id,
        "work_order_type": work_order_type,
        "session_id": session_id,
        "status": "semantic_work_order",
        "semantic_provider": HOST_SEMANTIC_PROVIDER,
        "minimum_context_window_tokens": minimum_context_window_tokens,
        "core_ref": dict(core_ref),
        "issued_at": _timestamp_iso(signed_claims["issued_at"]),
        "expires_at": _timestamp_iso(signed_claims["expires_at"]),
        "semantic_prompt": semantic_prompt,
        "response_schema": dict(response_schema),
        "bindings": dict(bindings),
        "submission_contract": {
            "tool": "boris.execute",
            "required_arguments": [
                "work_order_id",
                "work_order_token",
                submission_field,
            ],
            "work_order_token": token,
        },
        "limitations": [
            *HOST_EXECUTOR_LIMITATIONS,
            "not_independently_reviewed",
            "not_policy_admitted",
            "no_state_mutation",
            "no_external_action",
        ],
    }
    if phase is not None:
        envelope["phase"] = phase
    if phase_output_contract is not None:
        envelope["phase_output_contract"] = dict(
            phase_output_contract
        )
    if correction_count:
        envelope["gate"] = "HOLD"
        envelope["correction"] = {
            "correction_count": correction_count,
            "previous_work_order_id": parent_work_order_id,
            "return_state": phase,
            "issues": [
                dict(issue)
                for issue in correction_issues
            ],
            "instruction": (
                "Correct the submitted semantic_result against the unchanged "
                "Core, phase, SemanticInput, response_schema, and "
                "phase_output_contract. This correction remains under HOLD "
                "and is not canonical REPAIR. Submit this signed work order "
                "once."
            ),
        }
    return envelope


def consume_host_work_order(
    *,
    codec: HostWorkOrderCodec,
    registry: InMemoryHostWorkOrderRegistry,
    work_order_id: str,
    work_order_token: str,
    session_id: str | None,
) -> HostWorkOrderState:
    claims = codec.verify(work_order_token)
    signed_work_order_id = _claim_text(claims, "work_order_id")
    if work_order_id != signed_work_order_id:
        raise HostWorkOrderStateMismatch(
            "work_order_id does not match the signed work order."
        )
    signed_session_id = _claim_text(claims, "session_id")
    if session_id is not None and session_id != signed_session_id:
        raise HostWorkOrderStateMismatch(
            "session_id does not match the signed work order."
        )
    if claims.get("semantic_provider") != HOST_SEMANTIC_PROVIDER:
        raise HostWorkOrderStateMismatch(
            "work_order_token is bound to another semantic provider."
        )
    state = registry.consume(work_order_id)
    expected = {
        "work_order_id": state.work_order_id,
        "work_order_type": state.work_order_type,
        "session_id": state.session_id,
        "semantic_provider": HOST_SEMANTIC_PROVIDER,
        "core_ref": dict(state.core_ref),
        "attestation_sha256": state.attestation_sha256,
        "semantic_prompt_sha256": state.semantic_prompt_sha256,
        "response_schema_sha256": state.response_schema_sha256,
    }
    if state.work_order_type == COMPILATION_WORK_ORDER:
        expected.update({
            "semantic_source_sha256": state.semantic_source_sha256,
            "compiler_catalog_sha256": state.compiler_catalog_sha256,
        })
    elif (
        state.work_order_type == CALCULATION_WORK_ORDER
        and state.semantic_input is not None
    ):
        expected.update({
            "phase": state.semantic_input.phase,
            "semantic_input_sha256": state.semantic_input_sha256,
            "semantic_view_sha256": state.semantic_view_sha256,
            "correction_count": state.correction_count,
        })
        if state.parent_work_order_id is not None:
            expected["parent_work_order_id"] = (
                state.parent_work_order_id
            )
    else:
        raise HostWorkOrderStateMismatch(
            "Pending host work-order state has an unsupported type."
        )
    actual = {
        key: claims.get(key)
        for key in expected
    }
    if actual != expected:
        raise HostWorkOrderStateMismatch(
            "Signed host work order does not match the pending Runtime state."
        )
    return state


def require_current_host_scope(
    state: HostWorkOrderState,
    *,
    view: SemanticView,
    attestation_sha256: str,
) -> None:
    if (
        state.work_order_type != CALCULATION_WORK_ORDER
        or state.semantic_input is None
    ):
        raise HostWorkOrderStateMismatch(
            "Host work order is not a calculation order."
        )
    try:
        phase_output_contract = PhaseOutputContract.from_view(view)
    except PhaseOutputContractError as exc:
        raise HostWorkOrderStateMismatch(
            "Current Core no longer exposes the prepared phase output "
            "contract."
        ) from exc
    base_semantic_prompt = build_semantic_calculation_prompt(
        view,
        state.semantic_input,
    )
    current = {
        "core_ref": view.core_ref.to_dict(),
        "attestation_sha256": attestation_sha256,
        "semantic_input_sha256": canonical_sha256(
            state.semantic_input.to_prompt_dict()
        ),
        "semantic_view_sha256": canonical_sha256(view.to_prompt_dict()),
        "semantic_prompt_sha256": text_sha256(_calculation_prompt(
            base_semantic_prompt,
            phase_output_contract=phase_output_contract,
            correction_count=state.correction_count,
            parent_work_order_id=state.parent_work_order_id,
            correction_issues=state.correction_issues,
        )),
        "response_schema_sha256": canonical_sha256(
            semantic_calculation_response_schema(
                view,
                phase_output_contract=phase_output_contract,
            )
        ),
    }
    expected = {
        "core_ref": dict(state.core_ref),
        "attestation_sha256": state.attestation_sha256,
        "semantic_input_sha256": state.semantic_input_sha256,
        "semantic_view_sha256": state.semantic_view_sha256,
        "semantic_prompt_sha256": state.semantic_prompt_sha256,
        "response_schema_sha256": state.response_schema_sha256,
    }
    if current != expected:
        raise HostWorkOrderStateMismatch(
            "Current Core, attestation, phase, or semantic scope no longer "
            "matches the prepared host work order."
        )


def require_current_compilation_scope(
    state: HostWorkOrderState,
    *,
    core_ref: Mapping[str, str],
    attestation_sha256: str,
    source_material: Mapping[str, Any],
    compiler_catalog: Mapping[str, Any],
    semantic_prompt: str,
    response_schema: Mapping[str, Any],
) -> None:
    if state.work_order_type != COMPILATION_WORK_ORDER:
        raise HostWorkOrderStateMismatch(
            "Host work order is not a compilation order."
        )
    current = {
        "core_ref": dict(core_ref),
        "attestation_sha256": attestation_sha256,
        "semantic_source_sha256": canonical_sha256(source_material),
        "compiler_catalog_sha256": canonical_sha256(compiler_catalog),
        "semantic_prompt_sha256": text_sha256(semantic_prompt),
        "response_schema_sha256": canonical_sha256(response_schema),
    }
    expected = {
        "core_ref": dict(state.core_ref),
        "attestation_sha256": state.attestation_sha256,
        "semantic_source_sha256": state.semantic_source_sha256,
        "compiler_catalog_sha256": state.compiler_catalog_sha256,
        "semantic_prompt_sha256": state.semantic_prompt_sha256,
        "response_schema_sha256": state.response_schema_sha256,
    }
    if current != expected:
        raise HostWorkOrderStateMismatch(
            "Current Core, attestation, or compilation scope no longer "
            "matches the prepared host work order."
        )


def semantic_calculation_response_schema(
    view: SemanticView,
    *,
    phase_output_contract: PhaseOutputContract | None = None,
) -> dict[str, Any]:
    try:
        output_contract = (
            phase_output_contract
            or PhaseOutputContract.from_view(view)
        )
    except PhaseOutputContractError as exc:
        raise HostExecutorUnavailable(
            "The verified Core phase output contract is unresolved."
        ) from exc
    norm_refs = [candidate.norm_ref for candidate in view.candidates]
    layers = sorted({
        candidate.layer
        for candidate in view.candidates
    })
    operations = sorted({
        candidate.operation
        for candidate in view.candidates
    })
    catalog_entries = view.uncertainty_resolution_catalog.get(
        "entries",
        (),
    )
    resolution_refs = sorted({
        entry["resolution_ref"]
        for entry in catalog_entries
        if isinstance(entry, Mapping)
        and isinstance(entry.get("resolution_ref"), str)
        and entry["resolution_ref"]
    })
    string_array = {
        "type": "array",
        "items": {"type": "string", "minLength": 1},
        "uniqueItems": True,
    }
    nullable_string = {
        "anyOf": [
            {"type": "null"},
            {"type": "string", "minLength": 1},
        ]
    }
    core_ref = view.core_ref.to_dict()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:boris:semantic-calculation:1",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "core_ref",
            "phase",
            "norm_results",
            "unknowns",
            "uncertainties",
            "conflicts",
            "alternatives",
            "suggested_gate",
            "candidate_result",
        ],
        "properties": {
            "core_ref": {
                "type": "object",
                "additionalProperties": False,
                "required": list(core_ref),
                "properties": {
                    key: {"const": value}
                    for key, value in core_ref.items()
                },
            },
            "phase": {"const": view.phase},
            "norm_results": {
                "type": "array",
                "minItems": len(norm_refs),
                "maxItems": len(norm_refs),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "norm_ref",
                        "layer",
                        "operation",
                        "predicate_result",
                        "applicability",
                        "reason",
                        "unknowns",
                    ],
                    "properties": {
                        "norm_ref": {"enum": norm_refs},
                        "layer": {"enum": layers},
                        "operation": {"enum": operations},
                        "predicate_result": {
                            "enum": ["TRUE", "FALSE", "UNKNOWN", "ERROR"],
                        },
                        "applicability": {
                            "enum": ["TRUE", "FALSE", "UNKNOWN", "ERROR"],
                        },
                        "reason": {"type": "string", "minLength": 1},
                        "unknowns": string_array,
                    },
                },
            },
            "unknowns": string_array,
            "uncertainties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "uncertainty_id",
                        "description",
                        "resolution_class",
                        "target_path",
                        "norm_refs",
                        "core_refs",
                        "operator_question",
                    ],
                    "properties": {
                        "uncertainty_id": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "description": {
                            "type": "string",
                            "minLength": 1,
                        },
                        "resolution_class": {
                            "enum": [
                                "OPERATOR_INPUT",
                                "RUNTIME_DERIVABLE",
                                "FUTURE_CONTINGENT",
                                "MODEL_UNCERTAINTY",
                                "DOWNSTREAM_PRECONDITION",
                                "UNRESOLVABLE_LIMITATION",
                            ],
                        },
                        "target_path": nullable_string,
                        "norm_refs": {
                            **string_array,
                            "items": {"enum": norm_refs},
                        },
                        "core_refs": {
                            **string_array,
                            "items": (
                                {"enum": resolution_refs}
                                if resolution_refs
                                else {"type": "string", "minLength": 1}
                            ),
                        },
                        "operator_question": nullable_string,
                    },
                },
            },
            "conflicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "norm_refs",
                        "kind",
                        "disposition",
                        "reason",
                    ],
                    "properties": {
                        "norm_refs": {
                            **string_array,
                            "items": {"enum": norm_refs},
                            "minItems": 2,
                        },
                        "kind": {"type": "string", "minLength": 1},
                        "disposition": {"enum": ["HOLD", "STOP"]},
                        "reason": {"type": "string", "minLength": 1},
                    },
                },
            },
            "alternatives": {
                "type": "array",
                "items": {"type": "object"},
            },
            "suggested_gate": {
                "enum": ["PASS", "HOLD", "STOP", "REPAIR"],
            },
            "candidate_result": thaw_value(
                output_contract.schema
            ),
        },
        "x-boris-phase-output-contract": (
            output_contract.to_dict()
        ),
        "x-runtime-validation": (
            "SemanticCalculationValidator is authoritative and additionally "
            "checks exact norm coverage, copied formal results, ownership, "
            "unknown coverage, and forbidden execution claims."
        ),
    }


def _calculation_prompt(
    base_prompt: str,
    *,
    phase_output_contract: PhaseOutputContract,
    correction_count: int,
    parent_work_order_id: str | None,
    correction_issues: tuple[Mapping[str, Any], ...],
) -> str:
    contract_payload = phase_output_contract.to_dict()
    prompt = (
        f"{base_prompt}\n\n"
        "PHASE_OUTPUT_CONTRACT:\n"
        f"{json.dumps(contract_payload, ensure_ascii=False, sort_keys=True)}"
        "\n\ncandidate_result must be exactly the semantic_output.primary_object "
        "described by PHASE_OUTPUT_CONTRACT. Do not submit the gate context, "
        "a final answer from another phase, or free-form replacement fields."
    )
    if correction_count == 0:
        return prompt
    correction_payload = {
        "gate": "HOLD",
        "return_state": phase_output_contract.phase,
        "correction_count": correction_count,
        "previous_work_order_id": parent_work_order_id,
        "issues": [
            dict(issue)
            for issue in correction_issues
        ],
    }
    return (
        f"{prompt}\n\n"
        "HOLD_CORRECTION:\n"
        f"{json.dumps(correction_payload, ensure_ascii=False, sort_keys=True)}"
        "\n\nThe previous submission was not accepted. Correct every listed "
        "path while preserving the signed Core identity, phase, SemanticInput, "
        "selected norms, formal predicate results, and provenance. This is the "
        "single requested correction under HOLD. It is not canonical REPAIR, "
        "which requires a new revision and new cycle. Return only the corrected "
        "object matching response_schema."
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        thaw_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("base64url value must be non-empty")
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _timestamp_iso(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _claim_text(claims: Mapping[str, Any], name: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidHostWorkOrder(
            f"work_order_token claim {name} is invalid."
        )
    return value
