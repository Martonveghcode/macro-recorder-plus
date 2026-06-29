from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    WAIT = "wait"
    OPEN_URL = "open_url"
    OPEN_FILE = "open_file"
    LAUNCH_PROGRAM = "launch_program"
    TYPE_TEXT = "type_text"
    TYPE_SECRET = "type_secret"
    KEY_PRESS = "key_press"
    HOTKEY = "hotkey"
    MOUSE_MOVE = "mouse_move"
    MOUSE_BUTTON = "mouse_button"
    SCROLL = "scroll"
    IMAGE_CLICK = "image_click"
    IF_CONDITION = "if_condition"
    COMMENT = "comment"


ACTION_LABELS = {
    ActionType.WAIT: "Wait",
    ActionType.OPEN_URL: "Open URL",
    ActionType.OPEN_FILE: "Open File",
    ActionType.LAUNCH_PROGRAM: "Launch Program",
    ActionType.TYPE_TEXT: "Type Text",
    ActionType.TYPE_SECRET: "Type Secret",
    ActionType.KEY_PRESS: "Press Key",
    ActionType.HOTKEY: "Keyboard Shortcut",
    ActionType.MOUSE_MOVE: "Move Mouse",
    ActionType.MOUSE_BUTTON: "Mouse Button",
    ActionType.SCROLL: "Scroll",
    ActionType.IMAGE_CLICK: "Find Image and Click",
    ActionType.IF_CONDITION: "If Image Result",
    ActionType.COMMENT: "Comment",
}


DEFAULT_PARAMS: dict[ActionType, dict[str, Any]] = {
    ActionType.WAIT: {"seconds": 1.0},
    ActionType.OPEN_URL: {"url": "https://example.com"},
    ActionType.OPEN_FILE: {"file_path": "", "target_monitor": "default", "auto_focus": False},
    ActionType.LAUNCH_PROGRAM: {
        "executable": "",
        "arguments": "",
        "working_directory": "",
        "target_monitor": "default",
        "auto_focus": False,
        "wait_for_startup": False,
        "startup_timeout": 10.0,
    },
    ActionType.TYPE_TEXT: {"text": ""},
    ActionType.TYPE_SECRET: {"environment_variable": "WEBSITE_PASSWORD"},
    ActionType.KEY_PRESS: {"key": "enter", "phase": "press_release"},
    ActionType.HOTKEY: {"keys": ["ctrl", "v"]},
    ActionType.MOUSE_MOVE: {
        "start": [0, 0],
        "end": [0, 0],
        "path": [],
        "coordinate_mode": "exact",
    },
    ActionType.MOUSE_BUTTON: {"button": "left", "phase": "click", "x": 0, "y": 0},
    ActionType.SCROLL: {"dx": 0, "dy": -1, "x": 0, "y": 0},
    ActionType.IMAGE_CLICK: {
        "image_path": "",
        "click_action": "left_click",
        "confidence": 0.85,
        "timeout": 5.0,
        "poll_interval": 0.25,
        "grayscale": True,
        "on_not_found": "error",
        "region_x": 0,
        "region_y": 0,
        "region_width": 0,
        "region_height": 0,
    },
    ActionType.IF_CONDITION: {
        "image_found_action": 0,
        "image_not_found_action": 0,
    },
    ActionType.COMMENT: {"text": ""},
}


def _format_action_target(value: Any) -> str:
    try:
        action_number = int(value)
    except (TypeError, ValueError):
        action_number = 0
    if action_number <= 0:
        return "continue"
    return f"action {action_number}"


@dataclass(slots=True)
class MacroAction:
    type: ActionType
    delay: float = 0.0
    timestamp: float = 0.0
    duration: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not isinstance(self.type, ActionType):
            self.type = ActionType(str(self.type))
        self.delay = max(0.0, float(self.delay))
        self.timestamp = max(0.0, float(self.timestamp))
        self.duration = max(0.0, float(self.duration))
        defaults = dict(DEFAULT_PARAMS.get(self.type, {}))
        defaults.update(self.params)
        self.params = defaults

    @property
    def description(self) -> str:
        if self.label:
            return self.label
        match self.type:
            case ActionType.WAIT:
                return f"Wait {self.params.get('seconds', self.duration or self.delay):.2f}s"
            case ActionType.OPEN_URL:
                return str(self.params.get("url", ""))
            case ActionType.OPEN_FILE:
                file_path = self.params.get("file_path") or "file"
                return f"Open {file_path}"
            case ActionType.LAUNCH_PROGRAM:
                executable = self.params.get("executable") or "program"
                return f"Launch {executable}"
            case ActionType.TYPE_TEXT:
                text = str(self.params.get("text", ""))
                return f"Type {len(text)} character(s)"
            case ActionType.TYPE_SECRET:
                return f"Type secret from {self.params.get('environment_variable', '')}"
            case ActionType.KEY_PRESS:
                return f"{self.params.get('phase', 'press')} {self.params.get('key', '')}"
            case ActionType.HOTKEY:
                return "+".join(self.params.get("keys", []))
            case ActionType.MOUSE_MOVE:
                return f"{self.params.get('start')} -> {self.params.get('end')}"
            case ActionType.MOUSE_BUTTON:
                return f"{self.params.get('phase')} {self.params.get('button')}"
            case ActionType.SCROLL:
                return f"dx={self.params.get('dx', 0)}, dy={self.params.get('dy', 0)}"
            case ActionType.IMAGE_CLICK:
                action = str(self.params.get("click_action", "left_click")).replace("_", " ")
                image_path = str(self.params.get("image_path", ""))
                return f"Find image and {action}: {image_path}"
            case ActionType.IF_CONDITION:
                found = _format_action_target(self.params.get("image_found_action", 0))
                not_found = _format_action_target(self.params.get("image_not_found_action", 0))
                return f"If last image found -> {found}; not found -> {not_found}"
            case ActionType.COMMENT:
                return str(self.params.get("text", ""))
        return ACTION_LABELS[self.type]

    @property
    def target(self) -> str:
        match self.type:
            case ActionType.OPEN_URL:
                return str(self.params.get("url", ""))
            case ActionType.OPEN_FILE:
                return str(self.params.get("file_path", ""))
            case ActionType.LAUNCH_PROGRAM:
                return str(self.params.get("executable", ""))
            case ActionType.TYPE_SECRET:
                return str(self.params.get("environment_variable", ""))
            case ActionType.KEY_PRESS:
                return str(self.params.get("key", ""))
            case ActionType.HOTKEY:
                return "+".join(self.params.get("keys", []))
            case ActionType.MOUSE_MOVE:
                return str(self.params.get("end", ""))
            case ActionType.MOUSE_BUTTON | ActionType.SCROLL:
                return f"{self.params.get('x', '')}, {self.params.get('y', '')}"
            case ActionType.IMAGE_CLICK:
                return str(self.params.get("image_path", ""))
            case ActionType.IF_CONDITION:
                found = _format_action_target(self.params.get("image_found_action", 0))
                not_found = _format_action_target(self.params.get("image_not_found_action", 0))
                return f"found: {found}; not found: {not_found}"
        return ""

    def clone(self, *, keep_id: bool = False) -> "MacroAction":
        clone = replace(self, params=dict(self.params))
        if not keep_id:
            clone.id = uuid.uuid4().hex
        return clone

    def with_changes(self, **changes: Any) -> "MacroAction":
        if "params" in changes and changes["params"] is not None:
            changes["params"] = dict(changes["params"])
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "enabled": self.enabled,
            "delay": self.delay,
            "timestamp": self.timestamp,
            "duration": self.duration,
            "label": self.label,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroAction":
        if not isinstance(data, dict):
            raise ValueError("macro action must be an object")
        if "type" not in data:
            raise ValueError("macro action is missing type")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            type=ActionType(str(data["type"])),
            enabled=bool(data.get("enabled", True)),
            delay=float(data.get("delay", 0.0)),
            timestamp=float(data.get("timestamp", 0.0)),
            duration=float(data.get("duration", 0.0)),
            label=str(data.get("label", "")),
            params=dict(data.get("params") or {}),
        )


def create_action(action_type: ActionType, *, timestamp: float = 0.0, delay: float = 0.0) -> MacroAction:
    return MacroAction(
        type=action_type,
        timestamp=timestamp,
        delay=delay,
        duration=float(DEFAULT_PARAMS.get(action_type, {}).get("seconds", 0.0)) if action_type == ActionType.WAIT else 0.0,
        params=dict(DEFAULT_PARAMS[action_type]),
    )
