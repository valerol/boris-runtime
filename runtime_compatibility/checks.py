from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import stat
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from runtime_compatibility.models import SpecificationCheck


FINAL_VERIFICATION_PATH = "FINAL_VERIFICATION.json"
NORM_CATALOG_PATH = "assurance/NORM_CATALOG.tsv"
OBJECT_CATALOG_PATH = "assurance/OBJECT_CATALOG.tsv"
PHASE_APPLICABILITY_PATH = "assurance/NORM_PHASE_APPLICABILITY.tsv"
TEST_BINDINGS_PATH = "assurance/TEST_BINDINGS.tsv"
TEST_VECTORS_PATH = "assurance/TEST_VECTORS.json"
DEPENDENCY_DAG_PATH = "assurance/DEPENDENCY_DAG.tsv"
SOURCE_CODE_SUFFIXES = {
    ".bat",
    ".c",
    ".cmd",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".mjs",
    ".php",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".ts",
}
CYRILLIC = re.compile(r"[\u0400-\u04ff]")


class RequiredCheckRegistry:
    """Fail-closed executor for checks declared by VALIDATION_SPEC."""

    def __init__(self, profile):
        self.profile = profile
        self.handlers = {
            "SAFE_RELATIVE_ARCHIVE_PATHS": self._safe_relative_archive_paths,
            "NO_SYMBOLIC_LINKS": self._no_symbolic_links,
            "NO_EXECUTABLE_OR_SOURCE_CODE": self._no_executable_or_source_code,
            "ENGLISH_ONLY_PACKAGE": self._english_only_package,
            "ONE_PACKAGE_ID": self._one_package_id,
            "VERSION_IDENTITY_CONSISTENT": self._version_identity_consistent,
            "HASH_REPRODUCTION": self._hash_reproduction,
            "PDF_CATALOG_EQUIVALENCE": self._pdf_catalog_equivalence,
            "FOUNDATION_PROVENANCE": self._foundation_provenance,
            "UNIQUE_TEST_IDS": self._unique_test_ids,
            "NORM_TEST_SET_EQUALITY": self._norm_test_set_equality,
            "PREDICATE_DSL_SCHEMA_CONFORMANCE": (
                self._predicate_dsl_schema_conformance
            ),
            "HOLD_RETURN_STATE_PRESENT": self._hold_return_state_present,
            "C10_INDEPENDENCE_CONTRACT": self._c10_independence_contract,
            "C11_TERMINAL_EXECUTION_ONLY": self._c11_terminal_execution_only,
            "NORM_PHASE_APPLICABILITY_COMPLETE": (
                self._norm_phase_applicability_complete
            ),
            "OBJECT_RELATION_CLOSURE": self._object_relation_closure,
            "DEPENDENCY_DAG_ACYCLIC": self._dependency_dag_acyclic,
            "RUNTIME_TEMPLATES_MATCH_SCHEMAS": (
                self._runtime_templates_match_schemas
            ),
            "T_N_043_CANDIDATE_NOT_ACTIVE": (
                self._t_n_043_candidate_not_active
            ),
            "OPEN_DEBTS_VISIBLE": self._open_debts_visible,
        }

    def run(self, surface, schemas, templates, validation_spec):
        declared = validation_spec.get("required_checks")
        if not isinstance(declared, list) or not declared:
            return (
                SpecificationCheck(
                    check_id="DECLARED_REQUIRED_CHECKS",
                    status="REPAIR",
                    detail="VALIDATION_SPEC.required_checks is missing or empty.",
                ),
            )

        checks = []
        seen = set()
        for check_id in declared:
            if not isinstance(check_id, str) or not check_id.strip():
                checks.append(SpecificationCheck(
                    check_id="INVALID_REQUIRED_CHECK_ID",
                    status="REPAIR",
                    detail="A required check ID is not a non-empty string.",
                ))
                continue
            if check_id in seen:
                checks.append(SpecificationCheck(
                    check_id=check_id,
                    status="REPAIR",
                    detail="The required check is declared more than once.",
                ))
                continue
            seen.add(check_id)
            handler = self.handlers.get(check_id)
            if handler is None:
                checks.append(SpecificationCheck(
                    check_id=check_id,
                    status="HOLD",
                    detail=(
                        "The receiving Runtime has no implementation for this "
                        "declared required check."
                    ),
                ))
                continue
            try:
                passed = bool(handler(surface, schemas, templates))
            except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
                passed = False
            checks.append(SpecificationCheck(
                check_id=check_id,
                status="PASS" if passed else "HOLD",
                detail=(
                    "The declared package check was executed successfully."
                    if passed
                    else "The declared package check did not pass on this Runtime."
                ),
            ))
        return tuple(checks)

    @staticmethod
    def _safe_relative_archive_paths(surface, schemas, templates):
        path = Path(surface.source)
        if surface.source_kind != "archive" or not path.is_file():
            return False
        with zipfile.ZipFile(path) as archive:
            names = [item.filename for item in archive.infolist()]
        return bool(names) and all(_safe_archive_path(name) for name in names)

    @staticmethod
    def _no_symbolic_links(surface, schemas, templates):
        path = Path(surface.source)
        if surface.source_kind != "archive" or not path.is_file():
            return False
        with zipfile.ZipFile(path) as archive:
            return all(
                not stat.S_ISLNK((item.external_attr >> 16) & 0xFFFF)
                for item in archive.infolist()
            )

    @staticmethod
    def _no_executable_or_source_code(surface, schemas, templates):
        paths = set(surface.payload_paths)
        return (
            surface.machine_canon.get("executable") is False
            and not any(PurePosixPath(path).suffix.lower() in SOURCE_CODE_SUFFIXES for path in paths)
            and _static_check(surface, "packaged_executable_or_source_code") is False
        )

    @staticmethod
    def _english_only_package(surface, schemas, templates):
        if _static_check(surface, "english_only_text_surfaces") is not True:
            return False
        for path in surface.payload_paths:
            if PurePosixPath(path).suffix.lower() not in {
                ".csv",
                ".json",
                ".md",
                ".tsv",
                ".txt",
            }:
                continue
            text = surface.read_bytes(path).decode("utf-8")
            if CYRILLIC.search(text):
                return False
        pdf_qa = _final_verification(surface).get("static_checks", {}).get("pdf_qa")
        return isinstance(pdf_qa, Mapping) and all(
            item.get("cyrillic_detected") is False
            for item in pdf_qa.values()
            if isinstance(item, Mapping)
        )

    @staticmethod
    def _one_package_id(surface, schemas, templates):
        identities = _json_identity_values(surface, "package_id")
        return bool(identities) and identities == {surface.package_id}

    @staticmethod
    def _version_identity_consistent(surface, schemas, templates):
        identities = _json_identity_values(surface, "artifact_version")
        return bool(identities) and identities == {surface.artifact_version}

    @staticmethod
    def _hash_reproduction(surface, schemas, templates):
        if _status(surface, "HASH_REPRODUCTION") != "PASS_AFTER_PACKAGING":
            return False
        return all(
            hashlib.sha256(surface.read_bytes(component.path)).hexdigest()
            == component.sha256
            and len(surface.read_bytes(component.path)) == component.size_bytes
            for component in surface.components
        )

    @staticmethod
    def _pdf_catalog_equivalence(surface, schemas, templates):
        pdfs = [
            path
            for path in surface.payload_paths
            if PurePosixPath(path).suffix.lower() == ".pdf"
        ]
        return (
            bool(pdfs)
            and _status(surface, "PDF_CATALOG_EQUIVALENCE") == "PASS_STATIC"
            and _static_check(surface, "pdf_catalog_equivalence_expected") is True
        )

    @staticmethod
    def _foundation_provenance(surface, schemas, templates):
        foundations = surface.machine_canon.get("foundations")
        if not isinstance(foundations, Sequence) or isinstance(foundations, (str, bytes)):
            return False
        ids = []
        for item in foundations:
            if not isinstance(item, Mapping):
                return False
            foundation_id = item.get("id")
            if not foundation_id or not item.get("canonical_ref"):
                return False
            ids.append(foundation_id)
        return (
            bool(ids)
            and len(ids) == len(set(ids))
            and _status(surface, "FOUNDATION_PROVENANCE") == "PASS_STATIC"
        )

    @staticmethod
    def _unique_test_ids(surface, schemas, templates):
        tests = _tests(surface)
        ids = [item.get("test_id") for item in tests if isinstance(item, Mapping)]
        return (
            bool(ids)
            and all(isinstance(test_id, str) and test_id for test_id in ids)
            and len(ids) == len(set(ids))
            and _static_check(surface, "unique_test_ids") is True
        )

    @staticmethod
    def _norm_test_set_equality(surface, schemas, templates):
        catalog_ids = set()
        for row in _tsv(surface, NORM_CATALOG_PATH):
            values = json.loads(row.get("tests") or "[]")
            if not isinstance(values, list):
                return False
            catalog_ids.update(values)
        binding_ids = {
            row["test_id"]
            for row in _tsv(surface, TEST_BINDINGS_PATH)
            if row.get("norm_id")
        }
        return (
            bool(catalog_ids)
            and catalog_ids == binding_ids
            and _static_check(surface, "norm_test_set_equality") is True
        )

    def _predicate_dsl_schema_conformance(self, surface, schemas, templates):
        dsl = surface.machine_canon.get("predicate_dsl")
        if not isinstance(dsl, Mapping):
            return False
        if (
            tuple(dsl.get("truth_values", ())) != ("TRUE", "FALSE", "UNKNOWN")
            or dsl.get("missing_path_result") != "UNKNOWN"
            or dsl.get("unknown_material_result") != "HOLD"
        ):
            return False
        declared = dsl.get("operators")
        if not isinstance(declared, Mapping):
            return False
        if not set(declared).issubset(self.profile.supported_predicate_operators):
            return False
        for norm_id in surface.norm_ids:
            record = surface.get_norm(norm_id)
            predicate = json.loads(record.fields.get("when") or "{}")
            if not _predicate_operators(predicate).issubset(set(declared)):
                return False
        return True

    @staticmethod
    def _hold_return_state_present(surface, schemas, templates):
        machine = surface.machine_canon.get("cycle_state_machine")
        if not isinstance(machine, Mapping):
            return False
        contract = machine.get("hold_contract")
        transitions = machine.get("transitions")
        return (
            isinstance(contract, Mapping)
            and contract.get("return_transition") == "HOLD_TO_STORED_RETURN_STATE"
            and contract.get("resume_requires_gate_recheck") is True
            and isinstance(transitions, Sequence)
            and any(
                isinstance(item, Mapping)
                and item.get("from") == "HOLD"
                and item.get("to") == "$stored_return_state"
                and bool(item.get("preserves"))
                for item in transitions
            )
            and _static_check(surface, "hold_return_transition_present") is True
        )

    @staticmethod
    def _c10_independence_contract(surface, schemas, templates):
        vector = _test(surface, "TEST-GATE-G-C10-INDEPENDENT")
        operators = _predicate_operators(vector.get("predicate", {}))
        return (
            vector.get("required_phase") == "C10"
            and {"neq", "gte"}.issubset(operators)
            and vector.get("expected_negative") == "HOLD"
            and _static_check(surface, "c10_independence_predicate_present") is True
        )

    @staticmethod
    def _c11_terminal_execution_only(surface, schemas, templates):
        vector = _test(surface, "TEST-GATE-EFFECT-RECORDED")
        predicate = vector.get("predicate")
        terminal_values = set()
        for item in predicate.get("args", ()) if isinstance(predicate, Mapping) else ():
            if isinstance(item, Mapping) and item.get("path") == "execution_status":
                terminal_values.update(item.get("values", ()))
        return (
            vector.get("required_phase") == "C11"
            and "EXECUTING" not in terminal_values
            and {"EXECUTED", "FAILED", "NO_ACTION"}.issubset(terminal_values)
            and _static_check(surface, "c11_terminal_status_contract_present") is True
        )

    @staticmethod
    def _norm_phase_applicability_complete(surface, schemas, templates):
        bound = {
            row["norm_id"]
            for row in _tsv(surface, PHASE_APPLICABILITY_PATH)
            if row.get("norm_id") and row.get("required_phase")
        }
        return (
            set(surface.norm_ids).issubset(bound)
            and _static_check(surface, "all_norms_have_phase_applicability") is True
        )

    @staticmethod
    def _object_relation_closure(surface, schemas, templates):
        rows = _tsv(surface, OBJECT_CATALOG_PATH)
        object_types = {
            row["object_type"]
            for row in rows
            if row.get("record_type") == "OBJECT" and row.get("object_type")
        }
        lexicon = surface.machine_canon.get("lexicon", ())
        lexicon_terms = {
            item["term"]
            for item in lexicon
            if isinstance(item, Mapping) and item.get("term")
        }
        relation_targets = object_types | lexicon_terms
        relations = surface.machine_canon.get("object_relation_requirements")
        if not object_types or not isinstance(relations, Mapping):
            return False
        for source, requirements in relations.items():
            if source not in object_types or not isinstance(requirements, Sequence):
                return False
            for relation in requirements:
                if not isinstance(relation, str) or ":" not in relation:
                    return False
                if relation.split(":", 1)[1] not in relation_targets:
                    return False
        return True

    @staticmethod
    def _dependency_dag_acyclic(surface, schemas, templates):
        rows = _tsv(surface, DEPENDENCY_DAG_PATH)
        paths = {row["path"] for row in rows if row.get("path")}
        dependencies = {}
        for row in rows:
            path = row.get("path")
            refs = json.loads(row.get("depends_on") or "[]")
            if not path or not isinstance(refs, list) or not set(refs).issubset(paths):
                return False
            dependencies[path] = set(refs)
        resolved = set()
        while len(resolved) < len(dependencies):
            ready = {
                path
                for path, refs in dependencies.items()
                if path not in resolved and refs.issubset(resolved)
            }
            if not ready:
                return False
            resolved.update(ready)
        return bool(resolved)

    @staticmethod
    def _runtime_templates_match_schemas(surface, schemas, templates):
        definitions = schemas.get("$defs")
        if not isinstance(definitions, Mapping):
            return False
        mapping = {
            "operator_acceptance": "OperatorAcceptance",
            "runtime_attestation": "RuntimeAttestation",
            "substrate_declaration": "SubstrateDeclaration",
        }
        return all(
            isinstance(templates.get(template_name), Mapping)
            and isinstance(definitions.get(definition_name), Mapping)
            and set(definitions[definition_name].get("required", ())).issubset(
                templates[template_name]
            )
            for template_name, definition_name in mapping.items()
        )

    @staticmethod
    def _t_n_043_candidate_not_active(surface, schemas, templates):
        if not surface.has_norm("T-N-043"):
            return False
        record = surface.get_norm("T-N-043")
        return (
            record.fields.get("card_status") == "CANDIDATE"
            and record.fields.get("available_for_application") == "FALSE"
            and _static_check(surface, "t_n_043_candidate_inactive") is True
        )

    @staticmethod
    def _open_debts_visible(surface, schemas, templates):
        debts = _final_verification(surface).get("open_debts")
        return (
            isinstance(debts, list)
            and bool(debts)
            and all(
                isinstance(item, Mapping)
                and item.get("id")
                and item.get("status") == "OPEN"
                and item.get("closure")
                for item in debts
            )
        )


def _safe_archive_path(name):
    if not isinstance(name, str) or "\x00" in name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _final_verification(surface):
    value = surface.read_json(FINAL_VERIFICATION_PATH)
    if not isinstance(value, Mapping):
        raise ValueError("FINAL_VERIFICATION.json must contain an object.")
    return value


def _status(surface, name):
    return _final_verification(surface).get("statuses", {}).get(name)


def _static_check(surface, name):
    return _final_verification(surface).get("static_checks", {}).get(name)


def _json_identity_values(surface, field):
    result = set()
    for path in surface.payload_paths:
        if PurePosixPath(path).suffix.lower() != ".json":
            continue
        value = surface.read_json(path)
        if isinstance(value, Mapping) and field in value:
            result.add(value[field])
    return result


def _tsv(surface, path):
    text = surface.read_bytes(path).decode("utf-8")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if not reader.fieldnames:
        raise ValueError(f"{path} lacks a header.")
    return list(reader)


def _tests(surface):
    value = surface.read_json(TEST_VECTORS_PATH)
    tests = value.get("tests") if isinstance(value, Mapping) else None
    if not isinstance(tests, list):
        raise ValueError("TEST_VECTORS.json lacks tests.")
    return tests


def _test(surface, test_id):
    matches = [
        item
        for item in _tests(surface)
        if isinstance(item, Mapping) and item.get("test_id") == test_id
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one test vector for {test_id}.")
    return matches[0]


def _predicate_operators(value):
    result = set()
    if isinstance(value, Mapping):
        operation = value.get("op")
        if isinstance(operation, str):
            result.add(operation)
        for nested in value.values():
            result.update(_predicate_operators(nested))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            result.update(_predicate_operators(nested))
    return result
