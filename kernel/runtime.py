from kernel.sima import SIMA
from kernel.bois import BOIS
from kernel.memory import Memory
from kernel.llm import LLM
from kernel.gap import GapDetector

class BORISKernel:

    def __init__(self):
        self.memory = Memory()
        self.sima = SIMA()
        self.bois = BOIS()
        self.llm = LLM()
        self.gap = GapDetector()

    def run(self, event: dict):

        user_input = event["input"]

        sima_out = self.sima.analyze(event)

        bois_out = self.bois.reason(sima_out, self.memory)

        if self.gap.detect(bois_out):
            return {
                "type": "QUESTION",
                "content": bois_out["required_information"]
            }

        llm_out = self.llm.generate({
            "input": user_input,
            "bois": bois_out
        })

        self.memory.write_event("FINAL", llm_out)

        return {
            "type": "ANSWER",
            "content": llm_out
        }
