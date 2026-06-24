from __future__ import annotations

import json
from pathlib import Path

from .model import Macro


def save_macro(macro: Macro, path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != ".mrplus":
        target = target.with_suffix(".mrplus")

    payload = json.dumps(macro.to_dict(), indent=2, sort_keys=True)
    temp_path = target.with_suffix(f"{target.suffix}.tmp")
    temp_path.write_text(payload + "\n", encoding="utf-8")
    temp_path.replace(target)
    return target


def load_macro(path: str | Path) -> Macro:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("macro file must contain a JSON object")
    return Macro.from_dict(data)
