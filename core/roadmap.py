import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROADMAP_PATH = Path(__file__).with_name("roadmap.json")
COMPLETED = "COMPLETED"


def load_roadmap(path=None):
    roadmap_path = Path(path) if path else ROADMAP_PATH
    with roadmap_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_roadmap(roadmap, path=None):
    roadmap_path = Path(path) if path else ROADMAP_PATH
    with roadmap_path.open("w", encoding="utf-8") as f:
        json.dump(roadmap, f, indent=2)
        f.write("\n")


def complete_step(
    roadmap,
    step_id,
    evidence,
    validation_source,
    change_reason,
    completion_timestamp=None
):
    _require_governance_fields(evidence, validation_source, change_reason)

    updated = deepcopy(roadmap)
    step = _find_step(updated, step_id)
    step["status"] = COMPLETED
    step["completion_timestamp"] = (
        completion_timestamp or datetime.now(timezone.utc).isoformat()
    )
    step["evidence"] = evidence
    step["validation_source"] = validation_source
    step["change_reason"] = change_reason
    return updated


def _find_step(roadmap, step_id):
    for step in roadmap["steps"]:
        if step["id"] == step_id:
            return step

    raise ValueError(f"Unknown roadmap step: {step_id}")


def _require_governance_fields(evidence, validation_source, change_reason):
    missing = [
        name for name, value in {
            "evidence": evidence,
            "validation_source": validation_source,
            "change_reason": change_reason
        }.items()
        if not value
    ]

    if missing:
        raise ValueError(
            "Roadmap completion requires: " + ", ".join(missing)
        )
