class MemoryAdapter:
    """External memory interface. The middleware has no built-in memory."""

    def read(self, context):
        raise NotImplementedError

    def write(self, event):
        raise NotImplementedError

