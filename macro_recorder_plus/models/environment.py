from __future__ import annotations

import platform as py_platform
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def to_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rect":
        return cls(
            left=int(data.get("left", 0)),
            top=int(data.get("top", 0)),
            right=int(data.get("right", 0)),
            bottom=int(data.get("bottom", 0)),
        )


@dataclass(slots=True)
class MonitorInfo:
    identifier: str
    bounds: Rect
    work_area: Rect
    primary: bool = False
    dpi: int | None = None
    scale_factor: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "bounds": self.bounds.to_dict(),
            "work_area": self.work_area.to_dict(),
            "primary": self.primary,
            "dpi": self.dpi,
            "scale_factor": self.scale_factor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MonitorInfo":
        return cls(
            identifier=str(data.get("identifier", "")),
            bounds=Rect.from_dict(data.get("bounds", {})),
            work_area=Rect.from_dict(data.get("work_area", {})),
            primary=bool(data.get("primary", False)),
            dpi=data.get("dpi"),
            scale_factor=data.get("scale_factor"),
        )


@dataclass(slots=True)
class RecordedEnvironment:
    platform: str = field(default_factory=py_platform.system)
    virtual_desktop: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    monitors: list[MonitorInfo] = field(default_factory=list)
    cursor_start: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "virtual_desktop": self.virtual_desktop.to_dict(),
            "monitors": [monitor.to_dict() for monitor in self.monitors],
            "cursor_start": self.cursor_start,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RecordedEnvironment":
        if not data:
            return cls()
        return cls(
            platform=str(data.get("platform", py_platform.system())),
            virtual_desktop=Rect.from_dict(data.get("virtual_desktop", {})),
            monitors=[MonitorInfo.from_dict(item) for item in data.get("monitors", [])],
            cursor_start=data.get("cursor_start"),
        )


def current_environment() -> RecordedEnvironment:
    from macro_recorder_plus.platform.windows_monitors import get_monitor_layout

    return get_monitor_layout()
