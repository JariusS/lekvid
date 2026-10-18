"""Version module adhering to Semantic Versioning (SemVer)."""

from pathlib import Path

VERSION_FILE = Path(__file__).parent / "VERSION"

try:
    __version__ = VERSION_FILE.read_text(encoding="utf-8").strip()
except Exception:
    __version__ = "2.1.0"
