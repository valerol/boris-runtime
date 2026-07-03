from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DomainPhysiology:
    name: str = "default"
    capabilities: list[str] = field(default_factory=lambda: [
        "text reasoning",
        "BOIS structured reasoning",
        "SIMA analysis",
        "runtime state machine execution",
        "memory read/write"
    ])
    limitations: list[str] = field(default_factory=lambda: [
        "no autonomous self-modification",
        "no guaranteed external tool execution unless explicitly configured",
        "no vision/audio capabilities unless added later",
        "no persistent long-term learning unless explicitly enabled"
    ])
    version: str = "v1-static"
    scope: list[str] = field(default_factory=lambda: [
        "general reasoning",
        "operator task support",
        "BOIS/SIMA/BORIS runtime tasks"
    ])
    out_of_scope: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=lambda: [
        "produce useful answer",
        "maintain structured output contract",
        "ensure single terminal state per input",
        "answer is useful",
        "unknowns are explicit",
        "next step is actionable"
    ])
    learning_policy: str = (
        "store only stable operator-approved or repeatedly confirmed knowledge"
    )

    def snapshot(self):
        return asdict(self)


DEFAULT_DOMAIN = DomainPhysiology()
