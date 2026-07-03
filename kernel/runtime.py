"""
Kernel composition root.

This module wires BOIS, SIMA, GAP, Memory, LLM, Domain, and the runtime engine.
The state machine itself lives in runtime/engine.py.
"""

from kernel.sima import SIMA
from kernel.bois import BOIS
from kernel.memory import Memory
from kernel.llm import LLM
from kernel.gap import GapDetector
from kernel.self_introspection import explain_system, is_introspection_query
from core.loader import EpistemicHierarchyLoader, SchemaLoader
from physiology.domain import DEFAULT_DOMAIN
from runtime.engine import BORISRuntimeEngine

class BORISKernel:

    def __init__(
        self,
        memory=None,
        sima=None,
        bois=None,
        gap=None,
        llm=None,
        domain=None,
        schema_loader=None,
        epistemic_loader=None,
        engine=None
    ):
        self.memory = memory or Memory()
        self.sima = sima or SIMA()
        self.bois = bois or BOIS()
        self.gap = gap or GapDetector()
        self.llm = llm or LLM()
        self.domain = domain or DEFAULT_DOMAIN
        self.schema_loader = schema_loader or SchemaLoader()
        self.epistemic_loader = epistemic_loader or EpistemicHierarchyLoader()
        self.engine = engine or BORISRuntimeEngine(
            self,
            self.schema_loader.schema,
            epistemic_hierarchy=self.epistemic_loader.hierarchy
        )

    def run(self, event: dict):
        user_input = event.get("input", "")

        if is_introspection_query(user_input):
            return explain_system(user_input, self.domain, memory=self.memory)

        return self.engine.run(event)
