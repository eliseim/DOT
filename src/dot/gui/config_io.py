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
    """Read GUI state and resolve portable paths relative to its JSON file."""

    source = Path(path).resolve()
    with source.open(encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("GUI config must be a JSON object")
    base = source.parent
    output_dir = loaded.get("output_dir")
    if isinstance(output_dir, str) and output_dir.strip():
        loaded["output_dir"] = _resolved_config_path(output_dir, base)
    layers = loaded.get("layers")
    if isinstance(layers, list):
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            cadata_path = layer.get("cadata_path")
            if isinstance(cadata_path, str) and cadata_path.strip():
                layer["cadata_path"] = _resolved_config_path(cadata_path, base)
    return loaded


def _resolved_config_path(value: str, base: Path) -> str:
    path = Path(value).expanduser()
    return str(path if path.is_absolute() else (base / path).resolve())

