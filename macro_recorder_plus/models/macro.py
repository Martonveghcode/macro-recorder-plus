from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .actions import MacroAction
from .environment import RecordedEnvironment


FORMAT_VERSION = 1
MAX_MACRO_LOOP_COUNT = 99999


def clamp_macro_loop_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 1
    return min(MAX_MACRO_LOOP_COUNT, max(1, count))


def default_macro_settings() -> dict[str, Any]:
    return {"playback_speed": 1.0, "coordinate_mode": "exact", "macro_loop_count": 1}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MacroDocument:
    name: str = "Untitled Macro"
    pre_actions: list[MacroAction] = field(default_factory=list)
    actions: list[MacroAction] = field(default_factory=list)
    recorded_environment: RecordedEnvironment = field(default_factory=RecordedEnvironment)
    settings: dict[str, Any] = field(default_factory=default_macro_settings)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    format_version: int = FORMAT_VERSION

    @property
    def duration(self) -> float:
        if not self.actions:
            return 0.0
        return max(action.timestamp + action.duration for action in self.actions)

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "recorded_environment": self.recorded_environment.to_dict(),
            "settings": self.settings,
            "pre_actions": [action.to_dict() for action in self.pre_actions],
            "actions": [action.to_dict() for action in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroDocument":
        if not isinstance(data, dict):
            raise ValueError("macro file must contain a JSON object")
        version = int(data.get("format_version", data.get("version", FORMAT_VERSION)))
        if version != FORMAT_VERSION:
            raise ValueError(f"unsupported macro format version: {version}")
        actions_data = data.get("actions", data.get("events", []))
        if not isinstance(actions_data, list):
            raise ValueError("macro actions must be a list")
        actions = [MacroAction.from_dict(item) for item in actions_data]
        actions.sort(key=lambda action: action.timestamp)
        pre_actions_data = data.get("pre_actions", [])
        if not isinstance(pre_actions_data, list):
            raise ValueError("macro pre-actions must be a list")
        pre_actions = [MacroAction.from_dict(item) for item in pre_actions_data]
        pre_actions.sort(key=lambda action: action.timestamp)
        settings = dict(data.get("settings") or default_macro_settings())
        settings.setdefault("playback_speed", 1.0)
        settings.setdefault("coordinate_mode", "exact")
        settings["macro_loop_count"] = clamp_macro_loop_count(settings.get("macro_loop_count", 1))
        return cls(
            format_version=version,
            name=str(data.get("name") or "Untitled Macro"),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
            recorded_environment=RecordedEnvironment.from_dict(data.get("recorded_environment")),
            settings=settings,
            pre_actions=pre_actions,
            actions=actions,
        )
