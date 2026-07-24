import re
from uuid import UUID

from application.context_packet import (
    BORIS_CONTEXT_PUBLIC_FIELDS,
    BORIS_SESSION_PUBLIC_FIELDS,
    BOIS_FRAME_PUBLIC_FIELDS,
    FORBIDDEN_PUBLIC_KEYS,
    MAX_CHUNK_CHARACTERS,
    MAX_CHUNKS,
    MAX_TOTAL_CHARACTERS,
    PACKET_VERSION,
    RUNTIME_MODE,
    _known_secret_values,
    _normalize_public_key,
)
from application.semantic_validation import (
    SemanticAnswerValidator,
    SemanticValidationOutputError,
)
from llm.errors import LLMConfigurationError


VALIDATION_VERSION = "boris-validation/1.0"
VALIDATION_MODES = {"deterministic", "semantic", "hybrid"}
VERDICTS = {"PASS", "REVISE", "FAIL", "INDETERMINATE"}
SEVERITIES = {"low", "medium", "high", "critical"}
MAX_PASS_RISK = 0.30
MAX_PASS_UNCERTAINTY = 0.30
MAX_PASS_AMBIGUITY = 0.30
MAX_ANSWER_CHARACTERS = 20000
MAX_PACKET_TEXT_CHARACTERS = 60000

REQUIRED_PACKET_FIELDS = {
    "packet_version",
    "frame_id",
    "session_id",
    "input",
    "runtime_mode",
    "llm_called",
    "bois_frame",
    "sima",
    "boris_context",
    "projected_core",
    "projection_metadata",
    "answer_instructions",
    "runtime_generated_prompt",
}
SIMA_FIELDS = {"risk", "uncertainty", "missing_fields", "ambiguity_score"}
PROJECTED_CHUNK_FIELDS = {"chunk_id", "section", "title", "text", "relevance"}
PROJECTION_METADATA_FIELDS = {
    "returned_chunks",
    "total_characters",
    "truncated",
    "max_chunks",
    "max_chunk_characters",
    "max_total_characters",
}


class SemanticValidationUnavailable(RuntimeError):
    """Raised when semantic validation is required but no validator is available."""


class ValidationEngine:
    def __init__(self, validator_adapter_factory=None):
        self.validator_adapter_factory = validator_adapter_factory

    def validate(self, answer: str, context_packet: dict, validation_mode: str = "deterministic"):
        report = _base_report(context_packet, validation_mode)
        preflight = PacketPreflightValidator().validate(context_packet)
        report["frame_id"] = preflight["frame_id"]
        report["preflight"] = {
            "status": "completed" if not preflight["issues"] else "failed",
            "issues": preflight["issues"],
        }

        if preflight["issues"]:
            report["verdict"] = "FAIL"
            report["issues"] = _dedupe_issues(preflight["issues"])
            report["recommendations"] = _dedupe_recommendations(
                _recommendations_for_issues(preflight["issues"])
            )
            return report

        size_issues = _validation_input_size_issues(answer, context_packet)
        if size_issues:
            report["preflight"] = {
                "status": "failed",
                "issues": size_issues,
            }
            report["verdict"] = "FAIL" if any(issue["code"] == "PACKET_TOO_LARGE" for issue in size_issues) else "REVISE"
            report["issues"] = _dedupe_issues(size_issues)
            report["recommendations"] = _dedupe_recommendations(
                _recommendations_for_issues(size_issues)
            )
            return report

        if validation_mode == "deterministic":
            deterministic = DeterministicAnswerValidator().validate(answer, context_packet)
            report["deterministic"] = deterministic
            report["verdict"] = deterministic["verdict"]
            _aggregate(report)
            return report

        if validation_mode == "semantic":
            semantic, llm_called = self._run_semantic(answer, context_packet)
            report["semantic"] = semantic
            report["llm_called"] = llm_called
            report["verdict"] = semantic["verdict"]
            _aggregate(report)
            return report

        deterministic = DeterministicAnswerValidator().validate(answer, context_packet)
        report["deterministic"] = deterministic

        if deterministic["verdict"] == "FAIL":
            report["verdict"] = "FAIL"
            _aggregate(report)
            return report

        if not _should_escalate_to_semantic(deterministic):
            report["verdict"] = deterministic["verdict"]
            _aggregate(report)
            return report

        try:
            semantic, llm_called = self._run_semantic(answer, context_packet)
            report["semantic"] = semantic
            report["llm_called"] = llm_called
            report["verdict"] = _merge_verdicts(deterministic["verdict"], semantic["verdict"])
        except LLMConfigurationError:
            report["semantic"] = {
                "status": "unavailable",
                "verdict": "INDETERMINATE",
                "issues": [],
                "recommendations": ["Configure a validator LLM to complete semantic validation."],
            }
            report["verdict"] = "INDETERMINATE"
            report["llm_called"] = False
        except SemanticValidationOutputError:
            report["semantic"] = {
                "status": "invalid_output",
                "verdict": "INDETERMINATE",
                "issues": [],
                "recommendations": ["Retry later or inspect the validator configuration; the semantic validator returned invalid structured output."],
            }
            report["verdict"] = "INDETERMINATE"
            report["llm_called"] = True

        _aggregate(report)
        return report

    def _run_semantic(self, answer: str, context_packet: dict):
        if self.validator_adapter_factory is None:
            raise LLMConfigurationError("Semantic validator adapter is not configured")
        adapter = self.validator_adapter_factory()
        return SemanticAnswerValidator(adapter).validate(answer, context_packet)


class PacketPreflightValidator:
    def validate(self, packet: dict):
        issues = []
        frame_id = None

        if not isinstance(packet, dict):
            return {"frame_id": None, "issues": [_issue("PACKET_NOT_OBJECT", "critical", "The context packet must be a JSON object.", "context_packet", "preflight", False)]}

        raw_frame_id = packet.get("frame_id")
        if isinstance(raw_frame_id, str):
            try:
                frame_id = str(UUID(raw_frame_id))
            except (TypeError, ValueError):
                frame_id = None

        unexpected = sorted(set(packet) - REQUIRED_PACKET_FIELDS)
        missing = sorted(REQUIRED_PACKET_FIELDS - set(packet))
        for field in missing:
            issues.append(_issue("PACKET_MISSING_FIELD", "critical", f"The context packet is missing required field '{field}'.", field, "preflight", False))
        for field in unexpected:
            issues.append(_issue("PACKET_UNEXPECTED_FIELD", "critical", f"The context packet contains unexpected top-level field '{field}'.", field, "preflight", False))

        if missing or unexpected:
            return {"frame_id": frame_id, "issues": issues + self._leakage_issues(packet)}

        if not _non_empty_string(packet.get("packet_version")):
            issues.append(_issue("PACKET_FIELD_TYPE_INVALID", "critical", "packet_version must be a non-empty string.", "packet_version", "preflight", False))
        elif packet.get("packet_version") != PACKET_VERSION:
            issues.append(_issue("PACKET_VERSION_UNSUPPORTED", "critical", "The packet version is unsupported for validation.", "packet_version", "preflight", False))
        if frame_id is None:
            issues.append(_issue("FRAME_ID_INVALID", "critical", "The packet frame_id must be a valid UUID.", "frame_id", "preflight", False))
        if not _non_empty_string(packet.get("session_id")):
            issues.append(_issue("SESSION_ID_INVALID", "high", "The packet session_id must be a non-empty string.", "session_id", "preflight", False))
        if not isinstance(packet.get("input"), str):
            issues.append(_issue("INPUT_INVALID", "high", "The packet input must be a string.", "input", "preflight", False))
        if not isinstance(packet.get("runtime_mode"), str):
            issues.append(_issue("RUNTIME_MODE_INVALID", "critical", "The packet runtime_mode must be a string.", "runtime_mode", "preflight", False))
        elif packet.get("runtime_mode") != RUNTIME_MODE:
            issues.append(_issue("RUNTIME_MODE_INVALID", "critical", "The packet runtime_mode must be context_provider.", "runtime_mode", "preflight", False))
        if packet.get("llm_called") is not False:
            issues.append(_issue("LLM_CALLED_INVALID", "critical", "The context packet must declare llm_called as false.", "llm_called", "preflight", False))

        issues.extend(self._validate_bois_frame(packet.get("bois_frame"), packet.get("input")))
        issues.extend(self._validate_sima(packet.get("sima")))
        issues.extend(self._validate_boris_context(packet.get("boris_context"), packet.get("session_id")))
        issues.extend(
            self._validate_projected_core(
                packet.get("projected_core"),
                packet.get("projection_metadata"),
            )
        )
        issues.extend(self._validate_answer_instructions(packet.get("answer_instructions")))
        issues.extend(self._validate_runtime_generated_prompt(packet.get("runtime_generated_prompt")))
        issues.extend(self._leakage_issues(packet))
        return {"frame_id": frame_id, "issues": issues}

    def _validate_mapping_fields(self, value, allowed_fields, path, code):
        if not isinstance(value, dict):
            return [_issue(code, "critical", f"{path} must be a JSON object.", path, "preflight", False)]
        return [
            _issue(code, "critical", f"{path} contains unexpected field '{field}'.", f"{path}.{field}", "preflight", False)
            for field in sorted(set(value) - allowed_fields)
        ]

    def _validate_bois_frame(self, bois_frame, packet_input):
        issues = self._validate_mapping_fields(bois_frame, set(BOIS_FRAME_PUBLIC_FIELDS), "bois_frame", "BOIS_FRAME_INVALID")
        if issues:
            return issues

        if "framework" in bois_frame:
            if not isinstance(bois_frame["framework"], str):
                issues.append(_issue("BOIS_FRAME_TYPE_INVALID", "high", "bois_frame.framework must be a string.", "bois_frame.framework", "preflight", False))
            elif bois_frame["framework"] != "BOIS":
                issues.append(_issue("BOIS_FRAMEWORK_INVALID", "high", "bois_frame.framework must be BOIS.", "bois_frame.framework", "preflight", False))
        if "core" in bois_frame and not isinstance(bois_frame["core"], dict):
            issues.append(_issue("BOIS_FRAME_TYPE_INVALID", "high", "bois_frame.core must be an object.", "bois_frame.core", "preflight", False))
        if "input" in bois_frame:
            if not isinstance(bois_frame["input"], str):
                issues.append(_issue("BOIS_FRAME_TYPE_INVALID", "high", "bois_frame.input must be a string.", "bois_frame.input", "preflight", False))
            elif isinstance(packet_input, str) and bois_frame["input"] != packet_input:
                issues.append(_issue("BOIS_INPUT_MISMATCH", "high", "bois_frame.input must match packet.input.", "bois_frame.input", "preflight", False))
        if "constraints" in bois_frame:
            constraints = bois_frame["constraints"]
            if not isinstance(constraints, list):
                issues.append(_issue("BOIS_FRAME_TYPE_INVALID", "high", "bois_frame.constraints must be a list of strings.", "bois_frame.constraints", "preflight", False))
            elif any(not isinstance(item, str) for item in constraints):
                issues.append(_issue("BOIS_FRAME_TYPE_INVALID", "high", "bois_frame.constraints must contain only strings.", "bois_frame.constraints", "preflight", False))
        return issues

    def _validate_sima(self, sima):
        issues = self._validate_mapping_fields(sima, SIMA_FIELDS, "sima", "SIMA_INVALID")
        if issues:
            return issues
        for field in ("risk", "uncertainty", "ambiguity_score"):
            value = sima.get(field)
            if not _is_strict_number(value):
                issues.append(_issue("SIMA_TYPE_INVALID", "high", f"sima.{field} must be a number.", f"sima.{field}", "preflight", False))
            elif not 0.0 <= float(value) <= 1.0:
                issues.append(_issue("SIMA_RANGE_INVALID", "high", f"sima.{field} must be between 0.0 and 1.0.", f"sima.{field}", "preflight", False))
        missing_fields = sima.get("missing_fields")
        if not isinstance(missing_fields, list) or any(not isinstance(item, str) for item in missing_fields):
            issues.append(_issue("SIMA_TYPE_INVALID", "high", "sima.missing_fields must be a list of strings.", "sima.missing_fields", "preflight", False))
        return issues

    def _validate_boris_context(self, boris_context, packet_session_id):
        issues = self._validate_mapping_fields(boris_context, set(BORIS_CONTEXT_PUBLIC_FIELDS), "boris_context", "BORIS_CONTEXT_INVALID")
        if issues:
            return issues
        if "name" in boris_context:
            if not isinstance(boris_context["name"], str):
                issues.append(_issue("BORIS_CONTEXT_TYPE_INVALID", "high", "boris_context.name must be a string.", "boris_context.name", "preflight", False))
            elif boris_context["name"] != "BORIS":
                issues.append(_issue("BORIS_NAME_INVALID", "high", "boris_context.name must be BORIS.", "boris_context.name", "preflight", False))
        if "role" in boris_context and not isinstance(boris_context["role"], str):
            issues.append(_issue("BORIS_CONTEXT_TYPE_INVALID", "high", "boris_context.role must be a string.", "boris_context.role", "preflight", False))
        if "context" in boris_context and not isinstance(boris_context["context"], dict):
            issues.append(_issue("BORIS_CONTEXT_TYPE_INVALID", "high", "boris_context.context must be an object.", "boris_context.context", "preflight", False))
        if "definition" in boris_context and not isinstance(boris_context["definition"], (dict, str)):
            issues.append(_issue("BORIS_CONTEXT_TYPE_INVALID", "high", "boris_context.definition must be an object or a string.", "boris_context.definition", "preflight", False))
        session = boris_context.get("session")
        if session is not None:
            issues.extend(self._validate_boris_session(session))
            session_id = session.get("session_id") if isinstance(session, dict) else None
            if _non_empty_string(session_id) and _non_empty_string(packet_session_id) and session_id != packet_session_id:
                issues.append(_issue("BORIS_SESSION_ID_MISMATCH", "high", "boris_context.session.session_id must match packet.session_id.", "boris_context.session.session_id", "preflight", False))
        return issues

    def _validate_boris_session(self, session):
        issues = self._validate_mapping_fields(session, set(BORIS_SESSION_PUBLIC_FIELDS), "boris_context.session", "BORIS_SESSION_INVALID")
        if issues:
            return issues
        session_id = session.get("session_id")
        if "session_id" in session and not _non_empty_string(session_id):
            issues.append(_issue("BORIS_SESSION_TYPE_INVALID", "high", "boris_context.session.session_id must be a non-empty string.", "boris_context.session.session_id", "preflight", False))
        for field in ("clarification_cycles", "max_clarification_cycles"):
            if field in session:
                value = session.get(field)
                if not _is_strict_int(value):
                    issues.append(_issue("BORIS_SESSION_TYPE_INVALID", "high", f"boris_context.session.{field} must be an integer.", f"boris_context.session.{field}", "preflight", False))
                elif value < 0:
                    issues.append(_issue("CLARIFICATION_CYCLES_INVALID", "high", f"boris_context.session.{field} must be non-negative.", f"boris_context.session.{field}", "preflight", False))
        cycles = session.get("clarification_cycles")
        max_cycles = session.get("max_clarification_cycles")
        if _is_strict_int(cycles) and _is_strict_int(max_cycles) and cycles > max_cycles:
            issues.append(_issue("CLARIFICATION_CYCLES_INVALID", "high", "clarification_cycles cannot exceed max_clarification_cycles.", "boris_context.session.clarification_cycles", "preflight", False))
        return issues

    def _validate_projected_core(self, projected_core, metadata):
        issues = []
        if not isinstance(projected_core, list):
            return [_issue("PROJECTED_CORE_INVALID", "critical", "projected_core must be a list.", "projected_core", "preflight", False)]
        if not isinstance(metadata, dict):
            return [_issue("PROJECTION_METADATA_INVALID", "critical", "projection_metadata must be a JSON object.", "projection_metadata", "preflight", False)]

        unexpected = sorted(set(metadata) - PROJECTION_METADATA_FIELDS)
        missing = sorted(PROJECTION_METADATA_FIELDS - set(metadata))
        for field in missing:
            issues.append(_issue("PROJECTION_METADATA_INVALID", "critical", f"projection_metadata is missing '{field}'.", f"projection_metadata.{field}", "preflight", False))
        for field in unexpected:
            issues.append(_issue("PROJECTION_METADATA_INVALID", "critical", f"projection_metadata contains unexpected field '{field}'.", f"projection_metadata.{field}", "preflight", False))
        if missing or unexpected:
            return issues

        expected_limits = {
            "max_chunks": MAX_CHUNKS,
            "max_chunk_characters": MAX_CHUNK_CHARACTERS,
            "max_total_characters": MAX_TOTAL_CHARACTERS,
        }
        for field, expected in expected_limits.items():
            if not _is_strict_int(metadata.get(field)):
                issues.append(_issue("PROJECTION_METADATA_TYPE_INVALID", "critical", f"projection_metadata.{field} must be an integer.", f"projection_metadata.{field}", "preflight", False))
            elif metadata.get(field) != expected:
                issues.append(_issue("PROJECTION_LIMIT_INVALID", "critical", f"projection_metadata.{field} must be {expected}.", f"projection_metadata.{field}", "preflight", False))
        for field in ("returned_chunks", "total_characters"):
            value = metadata.get(field)
            if not _is_strict_int(value):
                issues.append(_issue("PROJECTION_METADATA_TYPE_INVALID", "critical", f"projection_metadata.{field} must be an integer.", f"projection_metadata.{field}", "preflight", False))
            elif value < 0:
                issues.append(_issue("PROJECTION_METADATA_TYPE_INVALID", "critical", f"projection_metadata.{field} must be non-negative.", f"projection_metadata.{field}", "preflight", False))
        if not isinstance(metadata.get("truncated"), bool):
            issues.append(_issue("PROJECTION_METADATA_INVALID", "high", "projection_metadata.truncated must be a boolean.", "projection_metadata.truncated", "preflight", False))
        if len(projected_core) > MAX_CHUNKS:
            issues.append(_issue("PROJECTION_LIMIT_EXCEEDED", "critical", "projected_core contains more than 6 chunks.", "projected_core", "preflight", False))

        total = 0
        chunk_ids = set()
        for index, chunk in enumerate(projected_core):
            path = f"projected_core.{index}"
            if not isinstance(chunk, dict):
                issues.append(_issue("PROJECTED_CHUNK_INVALID", "critical", "Each projected_core item must be a JSON object.", path, "preflight", False))
                continue
            for field in sorted(set(chunk) - PROJECTED_CHUNK_FIELDS):
                issues.append(_issue("PROJECTED_CHUNK_INVALID", "critical", f"Projected chunk contains unexpected field '{field}'.", f"{path}.{field}", "preflight", False))
            chunk_id = chunk.get("chunk_id")
            if not _non_empty_string(chunk_id):
                issues.append(_issue("PROJECTED_CHUNK_ID_INVALID", "critical", "Projected chunk IDs must be non-empty strings.", f"{path}.chunk_id", "preflight", False))
            elif chunk_id in chunk_ids:
                issues.append(_issue("DUPLICATE_CHUNK_ID", "critical", "Projected chunk IDs must be unique.", f"{path}.chunk_id", "preflight", False))
            else:
                chunk_ids.add(chunk_id)
            text = chunk.get("text")
            for field in ("section", "title"):
                if not isinstance(chunk.get(field), str):
                    issues.append(_issue("PROJECTED_CHUNK_TYPE_INVALID", "critical", f"Projected chunk {field} must be a string.", f"{path}.{field}", "preflight", False))
            if not isinstance(text, str):
                issues.append(_issue("PROJECTED_CHUNK_TYPE_INVALID", "critical", "Projected chunk text must be a string.", f"{path}.text", "preflight", False))
            else:
                total += len(text)
                if len(text) > MAX_CHUNK_CHARACTERS:
                    issues.append(_issue("PROJECTION_LIMIT_EXCEEDED", "critical", "Projected chunk text exceeds 3000 characters.", f"{path}.text", "preflight", False))
            if not _is_strict_number(chunk.get("relevance")):
                issues.append(_issue("PROJECTED_CHUNK_TYPE_INVALID", "critical", "Projected chunk relevance must be a number.", f"{path}.relevance", "preflight", False))
        if total > MAX_TOTAL_CHARACTERS:
            issues.append(_issue("PROJECTION_LIMIT_EXCEEDED", "critical", "Projected chunk text exceeds the 12000 character total limit.", "projected_core", "preflight", False))
        if metadata.get("returned_chunks") != len(projected_core):
            issues.append(_issue("PROJECTION_METADATA_MISMATCH", "critical", "projection_metadata.returned_chunks does not match projected_core length.", "projection_metadata.returned_chunks", "preflight", False))
        if metadata.get("total_characters") != total:
            issues.append(_issue("PROJECTION_METADATA_MISMATCH", "critical", "projection_metadata.total_characters does not match projected chunk text length.", "projection_metadata.total_characters", "preflight", False))
        if _is_strict_int(metadata.get("returned_chunks")) and _is_strict_int(metadata.get("max_chunks")) and metadata["returned_chunks"] > metadata["max_chunks"]:
            issues.append(_issue("PROJECTION_METADATA_MISMATCH", "critical", "projection_metadata.returned_chunks cannot exceed max_chunks.", "projection_metadata.returned_chunks", "preflight", False))
        if _is_strict_int(metadata.get("total_characters")) and _is_strict_int(metadata.get("max_total_characters")) and metadata["total_characters"] > metadata["max_total_characters"]:
            issues.append(_issue("PROJECTION_METADATA_MISMATCH", "critical", "projection_metadata.total_characters cannot exceed max_total_characters.", "projection_metadata.total_characters", "preflight", False))
        return issues

    def _validate_answer_instructions(self, instructions):
        if not isinstance(instructions, list):
            return [_issue("ANSWER_INSTRUCTIONS_INVALID", "high", "answer_instructions must be a list.", "answer_instructions", "preflight", False)]
        if any(not isinstance(item, str) for item in instructions):
            return [_issue("ANSWER_INSTRUCTIONS_INVALID", "high", "Each answer instruction must be a string.", "answer_instructions", "preflight", False)]
        return []

    def _validate_runtime_generated_prompt(self, prompt):
        if not _non_empty_string(prompt):
            return [_issue("RUNTIME_GENERATED_PROMPT_INVALID", "high", "runtime_generated_prompt must be a non-empty string.", "runtime_generated_prompt", "preflight", False)]
        return []

    def _leakage_issues(self, packet):
        issues = []
        for path, key in _walk_keys(packet, skip_paths={"input"}):
            normalized = _normalize_public_key(key)
            if normalized in FORBIDDEN_PUBLIC_KEYS:
                issues.append(_issue("FORBIDDEN_PACKET_FIELD", "critical", f"The packet contains forbidden public field '{key}'.", path, "preflight", False))
        for path, value in _walk_strings(packet, skip_paths={"input"}):
            lowered = value.lower()
            if "traceback (most recent call last)" in lowered:
                issues.append(_issue("TRACEBACK_LEAK", "critical", "The packet contains traceback text.", path, "preflight", False))
            for secret in _known_secret_values():
                if secret in value:
                    issues.append(_issue("PACKET_SECRET_LEAK", "critical", "The packet contains a configured secret value.", path, "preflight", False))
        return issues


class DeterministicAnswerValidator:
    def validate(self, answer: str, packet: dict):
        checks = []
        issues = []
        recommendations = []
        normalized_answer = " ".join(answer.split())

        if not normalized_answer:
            _add_check(checks, issues, "ANSWER_EMPTY", "REVISE", "high", "The answer is empty after normalization.", "answer", False)
        else:
            checks.append(_check("ANSWER_PRESENT", "PASS", "low", "The answer is present after normalization.", "answer", False))

        if len(answer) > MAX_ANSWER_CHARACTERS:
            _add_check(checks, issues, "ANSWER_TOO_LARGE", "REVISE", "medium", "The answer exceeds the validation size bound.", "answer", False)
        else:
            checks.append(_check("ANSWER_SIZE_WITHIN_LIMIT", "PASS", "low", "The answer is within the validation size bound.", "answer", False))

        for secret in _known_secret_values():
            if secret and secret in answer:
                _add_check(checks, issues, "ANSWER_SECRET_LEAK", "FAIL", "critical", "The answer exposes a configured secret value.", "answer", False)
                recommendations.append("Obtain a new answer that does not expose configured secret values.")
                break

        if _has_duplicate_questions(answer):
            _add_check(checks, issues, "DUPLICATE_CLARIFICATION_QUESTION", "REVISE", "medium", "The answer repeats a clarification question verbatim.", "answer", False)
            recommendations.append("Remove duplicate clarification questions.")

        sima = packet.get("sima", {})
        missing_fields = sima.get("missing_fields", [])
        if missing_fields and not _addresses_missing_fields(answer, missing_fields):
            _add_check(checks, issues, "MISSING_FIELDS_NOT_ADDRESSED", "REVISE", "medium", "The answer does not visibly address declared missing fields.", "sima.missing_fields", True)
            recommendations.append("Address the missing fields or ask a necessary clarification question.")

        risk = float(sima.get("risk", 0.0))
        uncertainty = float(sima.get("uncertainty", 0.0))
        ambiguity = float(sima.get("ambiguity_score", 0.0))
        if risk > MAX_PASS_RISK and not _contains_any(answer, ("risk", "caution", "careful", "unsafe", "harm", "safety")):
            _add_check(checks, issues, "RISK_DISCLOSURE_REQUIRED", "REVISE", "medium", "Elevated SIMA risk is not acknowledged where formally detectable.", "sima.risk", True)
            recommendations.append("Acknowledge the relevant risk before giving guidance.")
        if uncertainty > MAX_PASS_UNCERTAINTY and not _contains_any(answer, ("uncertain", "uncertainty", "unknown", "not sure", "may", "might", "likely")):
            _add_check(checks, issues, "UNCERTAINTY_DISCLOSURE_REQUIRED", "REVISE", "medium", "Elevated SIMA uncertainty is not acknowledged where formally detectable.", "sima.uncertainty", True)
            recommendations.append("Disclose uncertainty instead of presenting uncertain claims as established facts.")
        if ambiguity > MAX_PASS_AMBIGUITY and not _contains_any(answer, ("ambiguous", "ambiguity", "unclear", "could mean", "clarify")):
            _add_check(checks, issues, "AMBIGUITY_DISCLOSURE_REQUIRED", "REVISE", "medium", "Elevated SIMA ambiguity is not acknowledged where formally detectable.", "sima.ambiguity_score", True)
            recommendations.append("Acknowledge ambiguity or ask a clarifying question.")

        _add_alignment_checks(checks, issues, packet, answer)

        verdict = _deterministic_verdict(checks, issues, sima)
        return {
            "status": "completed",
            "verdict": verdict,
            "checks": checks,
            "issues": issues,
            "recommendations": _dedupe_recommendations(recommendations),
        }


def _base_report(packet, mode):
    return {
        "validation_version": VALIDATION_VERSION,
        "frame_id": packet.get("frame_id") if isinstance(packet, dict) and isinstance(packet.get("frame_id"), str) else None,
        "validation_mode": mode,
        "verdict": "INDETERMINATE",
        "llm_called": False,
        "preflight": {"status": "completed", "issues": []},
        "deterministic": {
            "status": "not_run",
            "verdict": "INDETERMINATE",
            "checks": [],
            "issues": [],
            "recommendations": [],
        },
        "semantic": {
            "status": "not_run",
            "verdict": "INDETERMINATE",
            "issues": [],
            "recommendations": [],
        },
        "issues": [],
        "recommendations": [],
    }


def _issue(code, severity, message, path, source, semantic_required):
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "source": source,
        "semantic_required": semantic_required,
    }


def _check(code, status, severity, message, path, semantic_required):
    return {
        "code": code,
        "status": status,
        "severity": severity,
        "message": message,
        "path": path,
        "semantic_required": semantic_required,
    }


def _add_check(checks, issues, code, status, severity, message, path, semantic_required):
    checks.append(_check(code, status, severity, message, path, semantic_required))
    issues.append(_issue(code, severity, message, path, "deterministic", semantic_required))


def _add_alignment_checks(checks, issues, packet, answer):
    if _lexical_overlap(packet.get("input", ""), answer):
        checks.append(_check("ANSWER_RELEVANCE_REQUIRES_SEMANTIC", "PASS", "medium", "No deterministic relevance defect was found; semantic validation can provide stronger assurance.", "input", False))
    else:
        _add_check(checks, issues, "ANSWER_RELEVANCE_REQUIRES_SEMANTIC", "INDETERMINATE", "medium", "Semantic verification is required to confirm answer relevance.", "input", True)

    bois_frame = packet.get("bois_frame", {})
    if bois_frame.get("core") or bois_frame.get("constraints"):
        _add_check(checks, issues, "BOIS_ALIGNMENT_REQUIRES_SEMANTIC", "INDETERMINATE", "medium", "Semantic verification is required to confirm BOIS frame alignment.", "bois_frame", True)
    else:
        checks.append(_check("BOIS_ALIGNMENT_REQUIRES_SEMANTIC", "PASS", "medium", "No BOIS core or constraints were supplied for semantic alignment.", "bois_frame", False))

    boris_context = packet.get("boris_context", {})
    if boris_context.get("context") or boris_context.get("definition"):
        _add_check(checks, issues, "BORIS_ALIGNMENT_REQUIRES_SEMANTIC", "INDETERMINATE", "medium", "Semantic verification is required to confirm BORIS context alignment.", "boris_context", True)
    else:
        checks.append(_check("BORIS_ALIGNMENT_REQUIRES_SEMANTIC", "PASS", "medium", "No BORIS context or definition was supplied for semantic alignment.", "boris_context", False))

    if packet.get("projected_core"):
        _add_check(checks, issues, "CORE_ALIGNMENT_REQUIRES_SEMANTIC", "INDETERMINATE", "medium", "Semantic verification is required to confirm projected core usage.", "projected_core", True)
    else:
        checks.append(_check("CORE_ALIGNMENT_REQUIRES_SEMANTIC", "PASS", "medium", "No projected core chunks were supplied for semantic alignment.", "projected_core", False))


def _deterministic_verdict(checks, issues, sima):
    statuses = {check["status"] for check in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "REVISE" in statuses:
        return "REVISE"
    if "INDETERMINATE" in statuses:
        return "INDETERMINATE"
    if (
        float(sima.get("risk", 0.0)) <= MAX_PASS_RISK
        and float(sima.get("uncertainty", 0.0)) <= MAX_PASS_UNCERTAINTY
        and float(sima.get("ambiguity_score", 0.0)) <= MAX_PASS_AMBIGUITY
        and not sima.get("missing_fields")
        and not issues
    ):
        return "PASS"
    return "INDETERMINATE"


def _should_escalate_to_semantic(deterministic):
    verdict = deterministic["verdict"]
    if verdict == "FAIL":
        return False
    if verdict == "INDETERMINATE":
        return True
    if verdict == "REVISE":
        return any(check.get("semantic_required") for check in deterministic.get("checks", []) if check.get("status") in {"REVISE", "INDETERMINATE"})
    return False


def _merge_verdicts(deterministic_verdict, semantic_verdict):
    if deterministic_verdict == "FAIL":
        return "FAIL"
    if semantic_verdict == "INDETERMINATE":
        return "INDETERMINATE"
    if deterministic_verdict == "REVISE":
        if semantic_verdict == "FAIL":
            return "FAIL"
        if semantic_verdict in {"PASS", "REVISE"}:
            return "REVISE"
    if deterministic_verdict == "PASS":
        return semantic_verdict
    if deterministic_verdict == "INDETERMINATE":
        return semantic_verdict
    return "INDETERMINATE"


def _aggregate(report):
    issues = []
    recommendations = []
    issues.extend(report["preflight"].get("issues", []))
    for layer in ("deterministic", "semantic"):
        if report[layer].get("status") in {"completed", "invalid_output", "unavailable"}:
            issues.extend(report[layer].get("issues", []))
            recommendations.extend(report[layer].get("recommendations", []))
    report["issues"] = _dedupe_issues(issues)
    report["recommendations"] = _dedupe_recommendations(
        recommendations + _recommendations_for_issues(report["issues"])
    )


def _dedupe_issues(issues):
    seen = set()
    result = []
    for issue in issues:
        key = (
            str(issue.get("code", "")).strip().lower(),
            str(issue.get("path", "")).strip().lower(),
            str(issue.get("message", "")).strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _dedupe_recommendations(recommendations):
    seen = set()
    result = []
    for recommendation in recommendations:
        text = str(recommendation or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _recommendations_for_issues(issues):
    recommendations = []
    for issue in issues:
        if issue["code"] == "ANSWER_TOO_LARGE":
            recommendations.append("Revise the answer so it stays within the validation size bound.")
            continue
        if issue["code"] == "PACKET_TOO_LARGE":
            recommendations.append("Request a new bounded boris.frame context packet before relying on this answer.")
            continue
        if issue["source"] == "preflight":
            recommendations.append("Request a new boris.frame context packet before relying on this answer.")
    return recommendations


def _non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _is_strict_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_strict_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validation_input_size_issues(answer, packet):
    issues = []
    if len(answer) > MAX_ANSWER_CHARACTERS:
        issues.append(_issue("ANSWER_TOO_LARGE", "medium", "The answer exceeds the validation size bound.", "answer", "preflight", False))
    if _packet_text_size(packet) > MAX_PACKET_TEXT_CHARACTERS:
        issues.append(_issue("PACKET_TOO_LARGE", "critical", "The packet text exceeds the validation size bound.", "context_packet", "preflight", False))
    return issues


def _walk_keys(value, path="", skip_paths=None):
    skip_paths = skip_paths or set()
    if path in skip_paths:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, key
            yield from _walk_keys(item, child_path, skip_paths)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            yield from _walk_keys(item, child_path, skip_paths)


def _walk_strings(value, path="", skip_paths=None):
    skip_paths = skip_paths or set()
    if path in skip_paths:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk_strings(item, child_path, skip_paths)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            yield from _walk_strings(item, child_path, skip_paths)
    elif isinstance(value, str):
        yield path, value


def _packet_text_size(packet):
    return sum(len(value) for _path, value in _walk_strings(packet))


def _has_duplicate_questions(answer):
    questions = [question.strip().lower() for question in re.findall(r"([^?]+\?)", answer)]
    seen = set()
    for question in questions:
        normalized = " ".join(question.split())
        if normalized in seen:
            return True
        seen.add(normalized)
    return False


def _addresses_missing_fields(answer, missing_fields):
    lowered = answer.lower()
    if _contains_any(answer, ("missing", "need", "clarify", "unknown")):
        return True
    return any(str(field).lower() in lowered for field in missing_fields)


def _contains_any(text, terms):
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _lexical_overlap(input_text, answer):
    input_tokens = {token for token in re.findall(r"[a-z0-9]{4,}", str(input_text).lower())}
    answer_tokens = {token for token in re.findall(r"[a-z0-9]{4,}", str(answer).lower())}
    return bool(input_tokens & answer_tokens)
