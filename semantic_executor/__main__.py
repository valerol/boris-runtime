import argparse
import json
import sys
from pathlib import Path

from core_surface import CoreSurfaceError, load_core_surface
from runtime_compatibility import (
    OperatorAcceptance,
    RuntimeCompatibilityError,
    RuntimeCompatibilityVerifier,
)
from llm.config import build_llm_adapter, load_env_file
from llm.errors import LLMConfigurationError
from semantic_executor import (
    LLMSemanticCalculator,
    SemanticExecutor,
    SemanticExecutorError,
    SemanticInput,
)


INPUT_FIELDS = {
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


class StaticCalculator:
    def __init__(self, calculation):
        self.calculation = calculation

    def calculate(self, view, semantic_input):
        return self.calculation


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run the isolated Phase 4F Minimal Semantic Executor against a "
            "versioned BOIS Core package."
        )
    )
    parser.add_argument("source", help="Path to a Core package directory or ZIP.")
    parser.add_argument("input", help="Path to a SemanticInput JSON object.")
    parser.add_argument(
        "--calculation",
        help=(
            "Validate a precomputed semantic calculation JSON instead of "
            "calling the configured LLM."
        ),
    )
    parser.add_argument(
        "--operator-acceptance",
        help=(
            "Path to an OperatorAcceptance JSON record bound to the exact "
            "archive hash. Without it the compatibility decision remains HOLD."
        ),
    )
    args = parser.parse_args()

    try:
        load_env_file()
        surface = load_core_surface(args.source, purpose="evaluation")
        operator_acceptance = _load_operator_acceptance(
            args.operator_acceptance
        )
        compatibility = RuntimeCompatibilityVerifier().verify(
            surface,
            operator_acceptance=operator_acceptance,
        )
        semantic_input = _load_semantic_input(args.input)
        calculator = _build_calculator(args.calculation)
        candidate = SemanticExecutor(
            surface,
            calculator,
            compatibility,
        ).execute(semantic_input)
    except (
        CoreSurfaceError,
        LLMConfigurationError,
        RuntimeCompatibilityError,
        SemanticExecutorError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(json.dumps({
            "status": "REJECTED",
            "error": exc.__class__.__name__,
            "detail": str(exc),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    print(json.dumps({
        "status": "CANDIDATE",
        "execution_candidate": candidate.to_dict(),
    }, ensure_ascii=False, indent=2))
    return 0


def _load_semantic_input(path):
    payload = _load_json_object(path, "SemanticInput")
    unexpected = set(payload) - INPUT_FIELDS
    missing = {"phenomenon", "phase"} - set(payload)
    if unexpected or missing:
        raise ValueError(
            "SemanticInput fields mismatch: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )
    return SemanticInput(**payload)


def _build_calculator(calculation_path):
    if calculation_path:
        return StaticCalculator(
            _load_json_object(calculation_path, "semantic calculation")
        )
    adapter = build_llm_adapter()
    if getattr(adapter, "adapter_name", "mock") == "mock":
        raise LLMConfigurationError(
            "Phase 4F requires BOIS_LLM=openai or --calculation."
        )
    return LLMSemanticCalculator(adapter)


def _load_operator_acceptance(path):
    if not path:
        return None
    return OperatorAcceptance.from_dict(
        _load_json_object(path, "OperatorAcceptance")
    )


def _load_json_object(path, label):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} file must contain one JSON object.")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
