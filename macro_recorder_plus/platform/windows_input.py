from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from getpass import getpass
from typing import Any

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.utilities.key_sequences import normalize_key_name
from macro_recorder_plus.utilities.validation import validate_url


def keyboard_key_to_name(key: Any) -> str:
    char = getattr(key, "char", None)
    if char:
        return char
    value = str(key)
    return normalize_key_name(value)


def mouse_button_to_name(button: Any) -> str:
    value = str(button)
    if value.startswith("Button."):
        value = value.split(".", 1)[1]
    return value.lower()


def name_to_keyboard_key(name: str) -> Any:
    from pynput import keyboard

    key = normalize_key_name(name)
    key_lookup = {
        "ctrl": keyboard.Key.ctrl,
        "shift": keyboard.Key.shift,
        "alt": keyboard.Key.alt,
        "win": keyboard.Key.cmd,
        "enter": keyboard.Key.enter,
        "escape": keyboard.Key.esc,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
        "home": keyboard.Key.home,
        "end": keyboard.Key.end,
        "tab": keyboard.Key.tab,
        "space": keyboard.Key.space,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
    }
    if key in key_lookup:
        return key_lookup[key]
    if len(key) == 1:
        return keyboard.KeyCode.from_char(key)
    if key.startswith("f") and key[1:].isdigit():
        return getattr(keyboard.Key, key)
    return keyboard.KeyCode.from_char(key)


def name_to_mouse_button(name: str) -> Any:
    from pynput import mouse

    key = str(name).lower().replace("button.", "")
    return getattr(mouse.Button, key)


class HeldInputTracker:
    def __init__(self, keyboard_controller: Any | None = None, mouse_controller: Any | None = None) -> None:
        self.keyboard = keyboard_controller
        self.mouse = mouse_controller
        self.held_keys: list[Any] = []
        self.held_buttons: list[Any] = []

    def press_key(self, key: Any) -> None:
        if self.keyboard is not None:
            self.keyboard.press(key)
        self.held_keys.append(key)

    def release_key(self, key: Any) -> None:
        if self.keyboard is not None:
            self.keyboard.release(key)
        self.held_keys = [held for held in self.held_keys if held != key]

    def press_button(self, button: Any) -> None:
        if self.mouse is not None:
            self.mouse.press(button)
        self.held_buttons.append(button)

    def release_button(self, button: Any) -> None:
        if self.mouse is not None:
            self.mouse.release(button)
        self.held_buttons = [held for held in self.held_buttons if held != button]

    def release_all(self) -> None:
        for key in list(reversed(self.held_keys)):
            try:
                if self.keyboard is not None:
                    self.keyboard.release(key)
            finally:
                pass
        for button in list(reversed(self.held_buttons)):
            try:
                if self.mouse is not None:
                    self.mouse.release(button)
            finally:
                pass
        self.held_keys.clear()
        self.held_buttons.clear()


class ActionExecutor:
    def __init__(self, keyboard_controller: Any, mouse_controller: Any) -> None:
        self.keyboard = keyboard_controller
        self.mouse = mouse_controller
        self.held = HeldInputTracker(keyboard_controller, mouse_controller)

    def execute(self, action: MacroAction, *, dry_run: bool = False) -> None:
        if dry_run or not action.enabled:
            return

        match action.type:
            case ActionType.WAIT | ActionType.COMMENT:
                return
            case ActionType.OPEN_URL:
                url = str(action.params.get("url", ""))
                if not validate_url(url):
                    raise ValueError(f"Invalid URL: {url}")
                webbrowser.open(url)
            case ActionType.LAUNCH_PROGRAM:
                executable = str(action.params.get("executable", ""))
                if not executable:
                    raise ValueError("Launch Program action is missing executable")
                args = str(action.params.get("arguments", ""))
                cwd = str(action.params.get("working_directory") or os.getcwd())
                command = [executable] + ([args] if args else [])
                subprocess.Popen(command, cwd=cwd)
            case ActionType.TYPE_TEXT:
                self.keyboard.type(str(action.params.get("text", "")))
            case ActionType.TYPE_SECRET:
                env_name = str(action.params.get("environment_variable", ""))
                secret = os.environ.get(env_name)
                if secret is None and sys.stdin.isatty():
                    secret = getpass(f"{env_name}: ")
                if secret is None:
                    raise ValueError(f"Missing required environment variable: {env_name}")
                self.keyboard.type(secret)
            case ActionType.KEY_PRESS:
                key = name_to_keyboard_key(str(action.params.get("key", "")))
                phase = str(action.params.get("phase", "press_release"))
                if phase in {"press", "down"}:
                    self.held.press_key(key)
                elif phase in {"release", "up"}:
                    self.held.release_key(key)
                else:
                    self.keyboard.press(key)
                    self.keyboard.release(key)
            case ActionType.HOTKEY:
                keys = [name_to_keyboard_key(key) for key in action.params.get("keys", [])]
                for key in keys:
                    self.held.press_key(key)
                for key in reversed(keys):
                    self.held.release_key(key)
            case ActionType.MOUSE_MOVE:
                end = action.params.get("end") or [0, 0]
                self.mouse.position = (int(end[0]), int(end[1]))
            case ActionType.MOUSE_BUTTON:
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    self.mouse.position = (int(x), int(y))
                button = name_to_mouse_button(str(action.params.get("button", "left")))
                phase = str(action.params.get("phase", "click"))
                if phase == "press":
                    self.held.press_button(button)
                elif phase == "release":
                    self.held.release_button(button)
                else:
                    self.mouse.press(button)
                    self.mouse.release(button)
            case ActionType.SCROLL:
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    self.mouse.position = (int(x), int(y))
                self.mouse.scroll(int(action.params.get("dx", 0)), int(action.params.get("dy", 0)))

    def release_all(self) -> None:
        self.held.release_all()
