"""JSON save/load helpers for target-synthesis GUI form state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_config(state: dict[str, Any], path: str | Path) -> None:
    """Write a GUI form-state dictionary to ``path`` as plain JSON."""

    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_config(path: str | Path) -> dict[str, Any]:
    """Read a GUI form-state dictionary from ``path``."""

    with Path(path).open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("GUI config must be a JSON object")
    return loaded

