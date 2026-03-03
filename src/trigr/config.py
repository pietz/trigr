import tomllib
from pathlib import Path

from trigr.models import TrigrConfig


def find_config() -> Path | None:
    """Find trigr.toml in cwd."""
    path = Path.cwd() / "trigr.toml"
    return path if path.exists() else None


def load_config() -> TrigrConfig:
    """Parse trigr.toml into TrigrConfig, return defaults if missing."""
    path = find_config()
    if path is None:
        return TrigrConfig()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return TrigrConfig(**data)
