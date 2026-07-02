class BORISRuntimeEngine:

    def __init__(self, kernel, schema):
        self.kernel = kernel
        self.schema = schema
        self.state = schema["entrypoint"]

    def step(self, event):

        node = self.schema["states"][self.state]

        t = node["type"]

        # 1. INPUT
        if t == "input":
            self.state = node["next"]
            return event

        # 2. MEMORY READ
        if t == "memory_read":
            self.kernel.memory.write("LOAD_CONTEXT", event)
            self.state = node["next"]
            return event

        # 3. SIMA
        if t == "analysis":
            out = self.kernel.sima.analyze(event)
            event["sima"] = out
            self.state = node["next"]
            return event

        # 4. BOIS
        if t == "reasoning":
            out = self.kernel.bois.reason(event["sima"], self.kernel.memory)
            event["bois"] = out
            self.state = node["next"]
            return event

        # 5. GAP DETECTION
        if t == "decision":
            gap = self.kernel.gap.detect(event["bois"])

            if gap:
                self.state = node["next_true"]
            else:
                self.state = node["next_false"]

            return event

        # 6. INTERACTION
        if t == "interaction":
            self.state = node["next"]
            return {"type": "QUESTION", "content": event["bois"]["required_information"]}

        # 7. TOOL ROUTING (stub)
        if t == "routing":
            self.state = node["next"]
            return event

        # 8. EXECUTION (stub)
        if t == "action":
            self.state = node["next"]
            return event

        # 9. LLM RESPONSE
        if t == "generation":
            event["response"] = f"LLM_RESPONSE({event})"
            self.state = node["next"]
            return event

        # 10. MEMORY WRITE
        if t == "memory_write":
            self.kernel.memory.write(self.state, event)
            self.state = node["next"]
            return event

        # 11. RETURN
        if t == "output":
            self.state = self.schema["entrypoint"]
            return {"type": "FINAL", "content": event}
