from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .actions import MacroAction
from .environment import RecordedEnvironment


FORMAT_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MacroDocument:
    name: str = "Untitled Macro"
    actions: list[MacroAction] = field(default_factory=list)
    recorded_environment: RecordedEnvironment = field(default_factory=RecordedEnvironment)
    settings: dict[str, Any] = field(default_factory=lambda: {"playback_speed": 1.0, "coordinate_mode": "exact"})
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
        return cls(
            format_version=version,
            name=str(data.get("name") or "Untitled Macro"),
            created_at=str(data.get("created_at") or utc_now()),
            updated_at=str(data.get("updated_at") or utc_now()),
            recorded_environment=RecordedEnvironment.from_dict(data.get("recorded_environment")),
            settings=dict(data.get("settings") or {"playback_speed": 1.0, "coordinate_mode": "exact"}),
            actions=actions,
        )
