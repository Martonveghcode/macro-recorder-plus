from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


SCHEMA_VERSION = 1
Device = Literal["keyboard", "mouse"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class MacroEvent:
    """A timestamped input event in seconds from the start of a recording."""

    time: float
    device: Device
    action: str
    key: str | None = None
    button: str | None = None
    x: int | None = None
    y: int | None = None
    dx: int | None = None
    dy: int | None = None

    def __post_init__(self) -> None:
        if self.time < 0:
            raise ValueError("event time cannot be negative")
        if self.device not in {"keyboard", "mouse"}:
            raise ValueError(f"unsupported event device: {self.device}")
        if not self.action:
            raise ValueError("event action is required")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "time": round(float(self.time), 6),
            "device": self.device,
            "action": self.action,
        }
        optional = {
            "key": self.key,
            "button": self.button,
            "x": self.x,
            "y": self.y,
            "dx": self.dx,
            "dy": self.dy,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroEvent":
        return cls(
            time=float(data["time"]),
            device=data["device"],
            action=str(data["action"]),
            key=data.get("key"),
            button=data.get("button"),
            x=_optional_int(data.get("x")),
            y=_optional_int(data.get("y")),
            dx=_optional_int(data.get("dx")),
            dy=_optional_int(data.get("dy")),
        )


@dataclass
class Macro:
    name: str = "Untitled macro"
    events: list[MacroEvent] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    version: int = SCHEMA_VERSION

    @property
    def duration(self) -> float:
        if not self.events:
            return 0.0
        return max(event.time for event in self.events)

    def add_event(self, event: MacroEvent) -> None:
        self.events.append(event)
        self.events.sort(key=lambda item: item.time)
        self.updated_at = utc_now_iso()

    def remove_indexes(self, indexes: set[int]) -> None:
        self.events = [event for index, event in enumerate(self.events) if index not in indexes]
        self.updated_at = utc_now_iso()

    def clear(self) -> None:
        self.events.clear()
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Macro":
        version = int(data.get("version", 1))
        if version != SCHEMA_VERSION:
            raise ValueError(f"unsupported macro schema version: {version}")

        events = [MacroEvent.from_dict(item) for item in data.get("events", [])]
        return cls(
            name=str(data.get("name") or "Untitled macro"),
            events=sorted(events, key=lambda item: item.time),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            version=version,
        )

    def renormalized(self) -> "Macro":
        if not self.events:
            return Macro(name=self.name, events=[], created_at=self.created_at, updated_at=utc_now_iso())
        first = min(event.time for event in self.events)
        events = [
            MacroEvent(
                time=max(0.0, event.time - first),
                device=event.device,
                action=event.action,
                key=event.key,
                button=event.button,
                x=event.x,
                y=event.y,
                dx=event.dx,
                dy=event.dy,
            )
            for event in self.events
        ]
        return Macro(name=self.name, events=events, created_at=self.created_at, updated_at=utc_now_iso())


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
