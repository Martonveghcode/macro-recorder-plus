from __future__ import annotations

from macro_recorder_plus.utilities.key_sequences import normalize_hotkey, normalize_key_name


def test_normalizes_key_aliases():
    assert normalize_key_name("Key.ctrl_l") == "ctrl"
    assert normalize_key_name("return") == "enter"


def test_normalizes_hotkey_order_and_duplicates():
    assert normalize_hotkey(["v", "shift", "ctrl", "ctrl_l"]) == ["ctrl", "shift", "v"]
