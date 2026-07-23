from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from core_surface import CoreSurface
from runtime_compatibility.checks import RequiredCheckRegistry
from runtime_compatibility.errors import RuntimeContractError
from runtime_compatibility.models import (
    OperatorAcceptance,
    RuntimeAttestation,
    RuntimeCompatibilityResult,
    SpecificationCheck,
    SubstrateDeclaration,
    canonical_sha256,
)
from runtime_compatibility.profile import RuntimeProfile
from runtime_compatibility.schema import validate_schema_definition


RUNTIME_SCHEMAS_PATH = "schema/RUNTIME_SCHEMAS.json"
RUNTIME_TEMPLATES_PATH = "runtime/RUNTIME_TEMPLATES.json"
VALIDATION_SPEC_PATH = "assurance/VALIDATION_SPEC.json"


class RuntimeCompatibilityVerifier:
    def __init__(self, profile=None, clock=None, check_registry=None):
        self.profile = profile or RuntimeProfile()
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.check_registry = check_registry or RequiredCheckRegistry(self.profile)

    def verify(
        self,
        surface: CoreSurface,
        operator_acceptance: OperatorAcceptance | Mapping | None = None,
    ) -> RuntimeCompatibilityResult:
        schemas = self._read_contract(surface, RUNTIME_SCHEMAS_PATH)
        templates = self._read_contract(surface, RUNTIME_TEMPLATES_PATH)
        validation_spec = self._read_contract(surface, VALIDATION_SPEC_PATH)
        self._validate_contract_identity(surface, schemas, RUNTIME_SCHEMAS_PATH)
        self._validate_contract_identity(surface, templates, RUNTIME_TEMPLATES_PATH)
        self._validate_contract_identity(
            surface,
            validation_spec,
            VALIDATION_SPEC_PATH,
        )
        self._validate_contract_shape(schemas, templates, validation_spec)

        declaration = self._build_declaration(surface)
        acceptance = self._resolve_acceptance(surface, operator_acceptance)
        validate_schema_definition(
            schemas,
            "SubstrateDeclaration",
            declaration.to_dict(),
        )
        validate_schema_definition(
            schemas,
            "OperatorAcceptance",
            acceptance.to_dict(),
        )

        checks = (
            *self._run_checks(surface, schemas, templates, validation_spec),
            *self.check_registry.run(
                surface,
                schemas,
                templates,
                validation_spec,
            ),
        )
        spec_status = _aggregate_check_status(checks)
        limitations = list(self.profile.limitations)
        activation_status = self._activation_status(
            acceptance,
            spec_status,
            limitations,
        )
        attestation = RuntimeAttestation(
            package_id=surface.package_id,
            artifact_version=surface.artifact_version,
            archive_sha256=surface.archive_sha256 or "",
            manifest_sha256=surface.manifest_sha256,
            substrate_id=self.profile.substrate_id,
            loaded_component_hashes=surface.loaded_component_hashes,
            spec_check_status=spec_status,
            activation_status=activation_status,
            limitations=tuple(dict.fromkeys(limitations)),
            source_kind=surface.source_kind,
            content_set_sha256=surface.content_set_sha256,
        )
        validate_schema_definition(
            schemas,
            "RuntimeAttestation",
            attestation.to_dict(),
        )
        attestation_hash = canonical_sha256(attestation.to_dict())
        return RuntimeCompatibilityResult(
            declaration=declaration,
            operator_acceptance=acceptance,
            attestation=attestation,
            checks=checks,
            attestation_sha256=attestation_hash,
            schema_validated=True,
        )

    def _build_declaration(self, surface):
        return SubstrateDeclaration(
            package_id=surface.package_id,
            artifact_version=surface.artifact_version,
            archive_sha256=surface.archive_sha256 or "",
            manifest_sha256=surface.manifest_sha256,
            substrate_id=self.profile.substrate_id,
            capabilities=self.profile.capabilities,
            limitations=self.profile.limitations,
            data_locations=self.profile.data_locations,
            failure_modes=self.profile.failure_modes,
            source_kind=surface.source_kind,
            content_set_sha256=surface.content_set_sha256,
        )

    def _resolve_acceptance(self, surface, value):
        if value is None:
            return OperatorAcceptance(
                package_id=surface.package_id,
                artifact_version=surface.artifact_version,
                archive_sha256=surface.archive_sha256 or "",
                manifest_sha256=surface.manifest_sha256,
                operator_role="UNSPECIFIED_OPERATOR",
                decision="HOLD",
                accepted_scope=(),
                decision_time=self.clock(),
                revocation_route="Create a replacement OperatorAcceptance.",
            )
        if isinstance(value, Mapping):
            value = OperatorAcceptance.from_dict(value)
        if not isinstance(value, OperatorAcceptance):
            raise RuntimeContractError(
                "operator_acceptance must be OperatorAcceptance, object, or None."
            )
        expected = (
            surface.package_id,
            surface.artifact_version,
            surface.archive_sha256,
            surface.manifest_sha256,
        )
        actual = (
            value.package_id,
            value.artifact_version,
            value.archive_sha256,
            value.manifest_sha256,
        )
        if expected != actual:
            raise RuntimeContractError(
                "OperatorAcceptance does not match the exact loaded archive."
            )
        return value

    def _run_checks(self, surface, schemas, templates, validation_spec):
        checks = [
            _check(
                "EXACT_ARCHIVE_BINDING",
                surface.source_kind == "archive" and bool(surface.archive_sha256),
                "The loaded surface is bound to the exact source archive SHA-256.",
                "Semantic evaluation requires the original ZIP archive.",
            ),
            _check(
                "PASSIVE_DATA_ONLY",
                surface.machine_canon.get("executable") is False,
                "The machine canon declares passive data only.",
                "The package does not declare executable=false.",
                failure="STOP",
            ),
            _check(
                "RUNTIME_CONTRACT_SCHEMA",
                all(
                    name in schemas.get("$defs", {})
                    for name in (
                        "OperatorAcceptance",
                        "RuntimeAttestation",
                        "SubstrateDeclaration",
                    )
                ),
                "All Phase 4R runtime contract definitions are present.",
                "A required runtime contract definition is missing.",
                failure="REPAIR",
            ),
            _check(
                "RUNTIME_TEMPLATES",
                _templates_match(templates, schemas),
                "Unfilled templates expose every required runtime record.",
                "Runtime templates are missing or claim to be attestations.",
                failure="REPAIR",
            ),
            _check(
                "VALIDATION_SPEC_BOUNDARY",
                _validation_spec_is_declarative(validation_spec),
                "The package distinguishes declarative checks from Runtime results.",
                "Validation specification status or prohibited claims are incomplete.",
                failure="REPAIR",
            ),
            _check(
                "COMPONENT_HASH_BINDING",
                len(surface.loaded_component_hashes) == len(surface.components),
                "Every loaded manifest component is bound to its verified hash.",
                "Loaded component hashes do not cover the manifest components.",
                failure="STOP",
            ),
        ]
        predicate_dsl = surface.machine_canon.get("predicate_dsl")
        predicate_operators = (
            set(predicate_dsl.get("operators", {}))
            if isinstance(predicate_dsl, Mapping)
            and isinstance(predicate_dsl.get("operators"), Mapping)
            else set()
        )
        checks.append(_check(
            "PREDICATE_DSL_COMPATIBILITY",
            (
                isinstance(predicate_dsl, Mapping)
                and tuple(predicate_dsl.get("truth_values", ()))
                == ("TRUE", "FALSE", "UNKNOWN")
                and predicate_dsl.get("missing_path_result") == "UNKNOWN"
                and predicate_dsl.get("unknown_material_result") == "HOLD"
                and predicate_operators.issubset(
                    self.profile.supported_predicate_operators
                )
            ),
            "The declared three-valued Predicate DSL is supported.",
            "The Predicate DSL contract or operator set is unsupported.",
            failure="HOLD",
        ))
        deontic = surface.machine_canon.get("deontic_semantics")
        operations = (
            set(deontic.get("operations", {}))
            if isinstance(deontic, Mapping)
            and isinstance(deontic.get("operations"), Mapping)
            else set()
        )
        checks.append(_check(
            "DEONTIC_COMPATIBILITY",
            (
                isinstance(deontic, Mapping)
                and operations.issubset(
                    self.profile.supported_deontic_operations
                )
                and {"PERMIT", "PROHIBIT", "REQUIRE"}.issubset(operations)
            ),
            "The declared deontic operations are supported.",
            "The deontic operation set is unsupported.",
            failure="HOLD",
        ))
        gates = surface.machine_canon.get("gate_decision_semantics")
        gate_order = _gate_order(gates)
        checks.append(_check(
            "GATE_DECISION_COMPATIBILITY",
            gate_order == self.profile.supported_gate_results,
            "GateDecision precedence is supported exactly.",
            "GateDecision results or precedence are unsupported.",
            failure="HOLD",
        ))
        return tuple(checks)

    @staticmethod
    def _read_contract(surface, path):
        try:
            value = surface.read_json(path)
        except KeyError as exc:
            raise RuntimeContractError(
                f"Core package lacks required runtime contract: {path}"
            ) from exc
        except (UnicodeDecodeError, ValueError) as exc:
            raise RuntimeContractError(
                f"Core package runtime contract is invalid JSON: {path}"
            ) from exc
        if not isinstance(value, Mapping):
            raise RuntimeContractError(f"{path} must contain an object.")
        return value

    @staticmethod
    def _validate_contract_identity(surface, value, path):
        expected = {
            "package_id": surface.package_id,
            "artifact_version": surface.artifact_version,
        }
        for field, expected_value in expected.items():
            if value.get(field) != expected_value:
                raise RuntimeContractError(
                    f"{path}.{field} does not match the loaded Core Surface."
                )

    @staticmethod
    def _validate_contract_shape(schemas, templates, validation_spec):
        if not isinstance(schemas.get("$defs"), Mapping):
            raise RuntimeContractError("RUNTIME_SCHEMAS.json lacks $defs.")
        if templates.get("status") != "UNFILLED_TEMPLATES_NOT_ATTESTATIONS":
            raise RuntimeContractError(
                "RUNTIME_TEMPLATES.json has an invalid trust-boundary status."
            )
        if (
            validation_spec.get("status")
            != "DECLARATIVE_SPECIFICATION_NOT_EXECUTION"
        ):
            raise RuntimeContractError(
                "VALIDATION_SPEC.json has an invalid trust-boundary status."
            )

    @staticmethod
    def _activation_status(acceptance, spec_status, limitations):
        if acceptance.decision == "REJECT":
            return "REJECTED"
        if acceptance.decision == "HOLD":
            return "HOLD"
        if acceptance.decision != "ACCEPT":
            limitations.append("unsupported_operator_decision")
            return "HOLD"
        if spec_status != "PASS":
            limitations.append("specification_checks_not_passed")
            return "HOLD"
        if "semantic_evaluation" not in acceptance.accepted_scope:
            limitations.append("semantic_evaluation_scope_not_accepted")
            return "HOLD"
        return "ACCEPTED_IN_SCOPE"


def _check(check_id, passed, success, failure_detail, *, failure="HOLD"):
    return SpecificationCheck(
        check_id=check_id,
        status="PASS" if passed else failure,
        detail=success if passed else failure_detail,
    )


def _aggregate_check_status(checks):
    precedence = ("REPAIR", "STOP", "HOLD", "PASS")
    statuses = {check.status for check in checks}
    return next(status for status in precedence if status in statuses)


def _templates_match(templates, schemas):
    if templates.get("status") != "UNFILLED_TEMPLATES_NOT_ATTESTATIONS":
        return False
    definitions = schemas.get("$defs")
    if not isinstance(definitions, Mapping):
        return False
    template_definitions = {
        "operator_acceptance": "OperatorAcceptance",
        "runtime_attestation": "RuntimeAttestation",
        "substrate_declaration": "SubstrateDeclaration",
    }
    for template_name, definition_name in template_definitions.items():
        template = templates.get(template_name)
        definition = definitions.get(definition_name)
        if not isinstance(template, Mapping) or not isinstance(definition, Mapping):
            return False
        required = definition.get("required")
        if not isinstance(required, list) or not set(required).issubset(template):
            return False
    return True


def _validation_spec_is_declarative(spec):
    prohibited = set(spec.get("prohibited_claims", ()))
    return (
        spec.get("status") == "DECLARATIVE_SPECIFICATION_NOT_EXECUTION"
        and "RUNTIME_COMPATIBILITY_PASS" in prohibited
        and isinstance(spec.get("required_checks"), list)
        and bool(spec["required_checks"])
    )


def _gate_order(gates):
    if not isinstance(gates, Mapping):
        return ()
    if tuple(gates.get("results", ())) != (
        "PASS",
        "HOLD",
        "STOP",
        "REPAIR",
    ):
        return ()
    mapping_rules = gates.get("mapping_rules")
    if (
        not isinstance(mapping_rules, Sequence)
        or isinstance(mapping_rules, (str, bytes))
    ):
        return ()
    return tuple(
        item.get("result")
        for item in mapping_rules
        if isinstance(item, Mapping)
    )
