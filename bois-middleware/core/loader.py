from pathlib import Path

from core.protocol import ProtocolDefinitions


class CoreLoader:
    """Loads declarative BOIS, SIMA, and BORIS definitions."""

    def __init__(self, definitions_dir=None):
        base = Path(__file__).resolve().parent / "definitions"
        self.definitions_dir = Path(definitions_dir) if definitions_dir else base

    def load(self):
        return ProtocolDefinitions(
            bois=self._read("bois.md"),
            sima=self._read("sima.md"),
            boris=self._read("boris.md"),
        )

    def _read(self, filename):
        return (self.definitions_dir / filename).read_text(encoding="utf-8").strip()

