from __future__ import annotations

from macro_recorder_plus.platform.windows_hotkeys import _normalize_hotkey, validate_hotkey_conflicts


def test_normalizes_function_hotkeys():
    assert _normalize_hotkey("<f8>") == "f8"
    assert _normalize_hotkey("Key.f9") == "f9"


def test_detects_hotkey_conflicts_after_normalization():
    assert validate_hotkey_conflicts({"start": "<f8>", "stop": "Key.f8"}) == ["f8"]
