from __future__ import annotations

from typing import Any


def keyboard_key_to_name(key: Any) -> str:
    char = getattr(key, "char", None)
    if char:
        return char
    return str(key)


def mouse_button_to_name(button: Any) -> str:
    return str(button)


def name_to_keyboard_key(name: str) -> Any:
    from pynput import keyboard

    if name.startswith("Key."):
        key_name = name.split(".", 1)[1]
        return getattr(keyboard.Key, key_name)
    return keyboard.KeyCode.from_char(name)


def name_to_mouse_button(name: str) -> Any:
    from pynput import mouse

    if name.startswith("Button."):
        button_name = name.split(".", 1)[1]
        return getattr(mouse.Button, button_name)
    return getattr(mouse.Button, name)
