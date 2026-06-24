from __future__ import annotations

import json
from pathlib import Path

from macro_recorder_plus.models.macro import MacroDocument


class MacroFileError(ValueError):
    pass


def save_macro(document: MacroDocument, path: str | Path) -> Path:
    target = Path(path)
    if not target.suffix:
        target = target.with_suffix(".mrplus.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    document.touch()
    payload = json.dumps(document.to_dict(), indent=2, sort_keys=True)
    temp_path = target.with_name(f"{target.name}.tmp")
    temp_path.write_text(payload + "\n", encoding="utf-8")
    temp_path.replace(target)
    return target


def load_macro(path: str | Path) -> MacroDocument:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        return MacroDocument.from_dict(data)
    except json.JSONDecodeError as exc:
        raise MacroFileError(f"Invalid JSON in {source.name}: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise MacroFileError(f"Invalid macro file {source.name}: {exc}") from exc
