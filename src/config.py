"""Load config.yaml and expose project paths. Used by every module."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def path(key: str) -> Path:
    """Absolute path for a key under `paths:` in config.yaml."""
    p = ROOT / load_config()["paths"][key]
    return p
