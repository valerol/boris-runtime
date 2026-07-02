from kernel.sima import SIMA
from kernel.bois import BOIS
from kernel.memory import Memory
from kernel.llm import LLM
from kernel.gap import GapDetector
from core.loader import SchemaLoader
from runtime.engine import BORISRuntimeEngine

class BORISKernel:

    def __init__(
        self,
        memory=None,
        sima=None,
        bois=None,
        gap=None,
        llm=None,
        schema_loader=None,
        engine=None
    ):
        self.memory = memory or Memory()
        self.sima = sima or SIMA()
        self.bois = bois or BOIS()
        self.gap = gap or GapDetector()
        self.llm = llm or LLM()
        self.schema_loader = schema_loader or SchemaLoader()
        self.engine = engine or BORISRuntimeEngine(self, self.schema_loader.schema)

    def run(self, event: dict):
        return self.engine.run(event)
