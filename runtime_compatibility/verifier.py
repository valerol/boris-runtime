from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from core_surface import CoreSurface
from core_surface.manifest import RELEASE_MANIFEST_DIALECT
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
        self._validate_contract_shape(
            surface,
            schemas,
            templates,
            validation_spec,
        )

        declaration = self._build_declaration(surface)
        acceptance = self._resolve_acceptance(surface, operator_acceptance)
        if surface.manifest_dialect != RELEASE_MANIFEST_DIALECT:
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

        declared_checks = (
            self._release_receipt_checks(surface, validation_spec)
            if surface.manifest_dialect == RELEASE_MANIFEST_DIALECT
            else self.check_registry.run(
                surface,
                schemas,
                templates,
                validation_spec,
            )
        )
        checks = (
            *self._run_checks(surface, schemas, templates, validation_spec),
            *declared_checks,
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
        canonical_records = {}
        if surface.manifest_dialect == RELEASE_MANIFEST_DIALECT:
            canonical_records = self._build_release_canonical_records(
                surface,
                declaration,
                acceptance,
                attestation,
                checks,
            )
            definition_names = {
                "substrate_declaration": "SubstrateDeclarationFinal",
                "operator_acceptance": "OperatorAcceptanceFinal",
                "specification_check_receipt": "SpecificationCheckReceiptFinal",
                "runtime_attestation": "RuntimeAttestationFinal",
            }
            for record_name, definition_name in definition_names.items():
                validate_schema_definition(
                    schemas,
                    definition_name,
                    canonical_records[record_name],
                )
        else:
            validate_schema_definition(
                schemas,
                "RuntimeAttestation",
                attestation.to_dict(),
            )
        attestation_hash = canonical_sha256(attestation.to_dict())
        package_identity = dict(surface.package_identity)
        return RuntimeCompatibilityResult(
            declaration=declaration,
            operator_acceptance=acceptance,
            attestation=attestation,
            checks=checks,
            attestation_sha256=attestation_hash,
            schema_validated=True,
            package_identity=package_identity,
            package_identity_sha256=canonical_sha256(package_identity),
            canonical_records=canonical_records,
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
        release_dialect = (
            surface.manifest_dialect == RELEASE_MANIFEST_DIALECT
        )
        contract_definitions = (
            (
                "OperatorAcceptanceFinal",
                "RuntimeAttestationFinal",
                "SpecificationCheckReceiptFinal",
                "SubstrateDeclarationFinal",
            )
            if release_dialect
            else (
                "OperatorAcceptance",
                "RuntimeAttestation",
                "SubstrateDeclaration",
            )
        )
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
                    for name in contract_definitions
                ),
                "All Phase 4R runtime contract definitions are present.",
                "A required runtime contract definition is missing.",
                failure="REPAIR",
            ),
            _check(
                "RUNTIME_TEMPLATES",
                _templates_match(
                    templates,
                    schemas,
                    release_dialect=release_dialect,
                ),
                "Unfilled templates expose every required runtime record.",
                "Runtime templates are missing or claim to be attestations.",
                failure="REPAIR",
            ),
            _check(
                "VALIDATION_SPEC_BOUNDARY",
                _validation_spec_is_declarative(
                    validation_spec,
                    release_dialect=release_dialect,
                ),
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
        if surface.manifest_dialect == RELEASE_MANIFEST_DIALECT:
            if path == RUNTIME_SCHEMAS_PATH:
                _validate_release_schema_identity(surface, value, path)
                return
            if path == VALIDATION_SPEC_PATH:
                expected = {
                    "normative_package_id": surface.normative_package_id,
                    "normative_content_version": (
                        surface.normative_content_version
                    ),
                    "release_package_id": surface.release_package_id,
                    "release_version": surface.release_version,
                }
            else:
                expected = {
                    "package_id": surface.package_id,
                    "artifact_version": surface.artifact_version,
                }
        else:
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
    def _validate_contract_shape(surface, schemas, templates, validation_spec):
        if not isinstance(schemas.get("$defs"), Mapping):
            raise RuntimeContractError("RUNTIME_SCHEMAS.json lacks $defs.")
        if surface.manifest_dialect == RELEASE_MANIFEST_DIALECT:
            definitions = schemas["$defs"]
            required_definitions = {
                "SubstrateDeclarationFinal",
                "OperatorAcceptanceFinal",
                "SpecificationCheckReceiptFinal",
                "RuntimeAttestationFinal",
            }
            if not required_definitions.issubset(definitions):
                raise RuntimeContractError(
                    "RUNTIME_SCHEMAS.json lacks release runtime record "
                    "definitions."
                )
            if not isinstance(templates.get("templates"), Mapping):
                raise RuntimeContractError(
                    "RUNTIME_TEMPLATES.json lacks templates."
                )
            mandatory_checks = validation_spec.get("mandatory_checks")
            if (
                validation_spec.get("inside_archive_status")
                != "PASSIVE_SPECIFICATION"
                or not isinstance(mandatory_checks, list)
                or not mandatory_checks
            ):
                raise RuntimeContractError(
                    "VALIDATION_SPEC.json has an invalid release validation "
                    "boundary."
                )
            return
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
    def _release_receipt_checks(surface, validation_spec):
        try:
            receipt = surface.read_json("assurance/VALIDATION_RECEIPT.json")
        except (KeyError, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeContractError(
                "Release package lacks a valid VALIDATION_RECEIPT.json."
            ) from exc
        receipt_checks = receipt.get("checks")
        declared = validation_spec.get("mandatory_checks")
        if not isinstance(receipt_checks, Mapping) or not isinstance(declared, list):
            raise RuntimeContractError(
                "Release validation specification or receipt has invalid checks."
            )

        results = []
        declared_ids = []
        seen = set()
        for item in declared:
            check_id = item.get("check_id") if isinstance(item, Mapping) else None
            if not isinstance(check_id, str) or not check_id.strip():
                results.append(SpecificationCheck(
                    check_id="INVALID_MANDATORY_CHECK_ID",
                    status="REPAIR",
                    detail=(
                        "A release mandatory check ID is not a non-empty string."
                    ),
                ))
                continue
            if check_id in seen:
                results.append(SpecificationCheck(
                    check_id=check_id,
                    status="REPAIR",
                    detail="The release mandatory check is declared more than once.",
                ))
                continue
            seen.add(check_id)
            declared_ids.append(check_id)
            embedded = receipt_checks.get(check_id)
            trace_hash = (
                embedded.get("trace_sha256")
                if isinstance(embedded, Mapping)
                else None
            )
            passed = (
                isinstance(embedded, Mapping)
                and embedded.get("result") == "PASS"
                and isinstance(trace_hash, str)
                and re.fullmatch(r"[0-9a-f]{64}", trace_hash) is not None
            )
            results.append(SpecificationCheck(
                check_id=check_id,
                status="PASS" if passed else "HOLD",
                detail=(
                    "The cryptographically bound embedded validation receipt "
                    "records PASS for this mandatory package check."
                    if passed
                    else "The embedded validation receipt does not provide a "
                    "valid PASS result and trace hash for this mandatory check."
                ),
            ))

        if set(declared_ids) != set(receipt_checks):
            results.append(SpecificationCheck(
                check_id="VALIDATION_RECEIPT_COVERAGE",
                status="REPAIR",
                detail=(
                    "VALIDATION_RECEIPT.json checks do not exactly match "
                    "VALIDATION_SPEC.json mandatory checks."
                ),
            ))
        return tuple(results)

    def _build_release_canonical_records(
        self,
        surface,
        declaration,
        acceptance,
        attestation,
        checks,
    ):
        declaration_id = "SUBSTRATE-DECLARATION-PHASE-4R"
        acceptance_id = "OPERATOR-ACCEPTANCE-PHASE-4R"
        specification_id = "SPECIFICATION-CHECK-PHASE-4R"
        attestation_id = "RUNTIME-ATTESTATION-PHASE-4R"
        accepted = attestation.activation_status == "ACCEPTED_IN_SCOPE"
        canonical_activation = (
            "ACCEPTED_IN_SCOPE"
            if accepted
            else "REJECTED"
            if attestation.activation_status == "REJECTED"
            else "NOT_ACCEPTED"
        )
        canonical_decision = (
            "DEFER"
            if acceptance.decision == "HOLD"
            else acceptance.decision
        )
        completed_at = self.clock()
        canonical_checks = [
            {
                "check_id": check.check_id,
                "status": check.status,
                "evidence_ref": f"runtime-compatibility:{check.check_id}",
            }
            for check in checks
        ]
        return {
            "substrate_declaration": {
                "declaration_id": declaration_id,
                "record_status": "FINAL",
                "package_id": surface.package_id,
                "archive_sha256": surface.archive_sha256 or "",
                "owner_ref": "BORIS-RUNTIME-OWNER",
                "substrate_kind": "AI_HUMAN_MEMORY",
                "capabilities": list(declaration.capabilities),
                "limitations": list(declaration.limitations),
                "security_constraints": ["passive-data-only"],
                "memory_constraints": ["immutable-in-process-surface"],
                "tool_constraints": ["no-external-action"],
                "fallbacks": ["hold-on-unsupported-contract"],
                "declared_at": completed_at,
            },
            "operator_acceptance": {
                "record_id": acceptance_id,
                "record_status": "FINAL",
                "package_id": surface.package_id,
                "artifact_version": surface.artifact_version,
                "archive_sha256": surface.archive_sha256 or "",
                "operator_id": _canonical_identifier(
                    acceptance.operator_role,
                    "OPERATOR",
                ),
                "decision": canonical_decision,
                "accepted_scope": list(acceptance.accepted_scope),
                "accepted_components": (
                    list(surface.loaded_component_hashes)
                    if canonical_decision == "ACCEPT"
                    else []
                ),
                "decision_time": acceptance.decision_time,
            },
            "specification_check_receipt": {
                "record_id": specification_id,
                "record_status": "FINAL",
                "package_id": surface.package_id,
                "artifact_version": surface.artifact_version,
                "archive_sha256": surface.archive_sha256 or "",
                "check_status": attestation.spec_check_status,
                "checks": canonical_checks,
                "completed_at": completed_at,
            },
            "runtime_attestation": {
                "record_id": attestation_id,
                "record_status": "FINAL",
                "package_id": surface.package_id,
                "artifact_version": surface.artifact_version,
                "archive_sha256": surface.archive_sha256 or "",
                "activation_status": canonical_activation,
                "spec_check_status": attestation.spec_check_status,
                "loaded_component_hashes": (
                    dict(surface.loaded_component_hashes) if accepted else {}
                ),
                "substrate_declaration_ref": declaration_id,
                "operator_acceptance_ref": acceptance_id,
                "specification_check_ref": specification_id,
                "limitations": list(attestation.limitations),
            },
        }

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


def _templates_match(templates, schemas, *, release_dialect=False):
    if release_dialect:
        definitions = schemas.get("$defs")
        template_records = templates.get("templates")
        if not isinstance(definitions, Mapping) or not isinstance(
            template_records,
            Mapping,
        ):
            return False
        template_definitions = {
            "OperatorAcceptance": "OperatorAcceptanceDraft",
            "RuntimeAttestation": "RuntimeAttestationDraft",
            "SpecificationCheckReceipt": "SpecificationCheckReceiptDraft",
            "SubstrateDeclaration": "SubstrateDeclarationDraft",
        }
        for template_name, definition_name in template_definitions.items():
            template = template_records.get(template_name)
            definition = definitions.get(definition_name)
            if not isinstance(template, Mapping) or not isinstance(
                definition,
                Mapping,
            ):
                return False
            required = definition.get("required")
            if not isinstance(required, list) or not set(required).issubset(
                template
            ):
                return False
        return True

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


def _validation_spec_is_declarative(spec, *, release_dialect=False):
    if release_dialect:
        mandatory = spec.get("mandatory_checks")
        return (
            spec.get("inside_archive_status") == "PASSIVE_SPECIFICATION"
            and spec.get("execution_location")
            == "OUTSIDE_ARCHIVE_VALIDATOR; RESULTS_INSIDE_ARCHIVE"
            and isinstance(mandatory, list)
            and bool(mandatory)
            and all(
                isinstance(item, Mapping)
                and isinstance(item.get("check_id"), str)
                and bool(item["check_id"].strip())
                for item in mandatory
            )
        )

    prohibited = set(spec.get("prohibited_claims", ()))
    return (
        spec.get("status") == "DECLARATIVE_SPECIFICATION_NOT_EXECUTION"
        and "RUNTIME_COMPATIBILITY_PASS" in prohibited
        and isinstance(spec.get("required_checks"), list)
        and bool(spec["required_checks"])
    )


def _validate_release_schema_identity(surface, schemas, path):
    definitions = schemas.get("$defs")
    if not isinstance(definitions, Mapping):
        raise RuntimeContractError(f"{path} lacks $defs.")
    identity_definitions = (
        "OperatorAcceptanceFinal",
        "RuntimeAttestationFinal",
        "SpecificationCheckReceiptFinal",
    )
    for definition_name in identity_definitions:
        definition = definitions.get(definition_name)
        properties = (
            definition.get("properties")
            if isinstance(definition, Mapping)
            else None
        )
        if not isinstance(properties, Mapping):
            raise RuntimeContractError(
                f"{path}.{definition_name} lacks properties."
            )
        expected = {
            "package_id": surface.package_id,
            "artifact_version": surface.artifact_version,
        }
        for field, expected_value in expected.items():
            field_schema = properties.get(field)
            if (
                not isinstance(field_schema, Mapping)
                or field_schema.get("const") != expected_value
            ):
                raise RuntimeContractError(
                    f"{path}.{definition_name}.{field} does not match the "
                    "loaded Core Surface."
                )


def _canonical_identifier(value, fallback):
    text = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value).strip())
    text = text.strip("-_.:")
    if not text or not text[0].isalpha():
        text = fallback
    return text


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
    declared = (
        item.get("result")
        for item in mapping_rules
        if isinstance(item, Mapping)
    )
    return tuple(dict.fromkeys(declared))
