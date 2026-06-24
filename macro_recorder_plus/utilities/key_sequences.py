from __future__ import annotations

ALIASES = {
    "control": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
    "return": "enter",
    "esc": "escape",
}

ORDER = {"ctrl": 0, "shift": 1, "alt": 2, "win": 3}


def normalize_key_name(key: str) -> str:
    key = key.strip().lower()
    if key.startswith("key."):
        key = key.split(".", 1)[1]
    return ALIASES.get(key, key)


def normalize_hotkey(keys: list[str] | tuple[str, ...]) -> list[str]:
    normalized = [normalize_key_name(key) for key in keys if key]
    return sorted(dict.fromkeys(normalized), key=lambda key: (ORDER.get(key, 99), key))
