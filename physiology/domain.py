from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class DomainPhysiology:
    name: str = "default"
    scope: list[str] = field(default_factory=lambda: [
        "general reasoning",
        "operator task support",
        "BOIS/SIMA/BORIS runtime tasks"
    ])
    out_of_scope: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=lambda: [
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
