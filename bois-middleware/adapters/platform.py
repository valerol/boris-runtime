class PlatformAdapter:
    """Host platform boundary for UI, auth, storage, and transport concerns."""

    def normalize_input(self, payload):
        raise NotImplementedError

    def format_output(self, response):
        raise NotImplementedError

