from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from macro_recorder_plus.utilities.key_sequences import normalize_key_name


DEFAULT_HOTKEYS = {
    "start_recording": "<f8>",
    "stop_recording": "<f9>",
    "pause_recording": "<f7>",
    "emergency_stop": "<f10>",
    "pause_playback": "<f6>",
}


class HotkeyManager(QObject):
    startRecording = Signal()
    stopRecording = Signal()
    pauseRecording = Signal()
    emergencyStop = Signal()
    pausePlayback = Signal()
    registrationFailed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._listener = None

    def start(self, hotkeys: dict[str, str] | None = None) -> None:
        self.stop()
        mapping = hotkeys or DEFAULT_HOTKEYS
        try:
            from pynput import keyboard

            callbacks = {
                _normalize_hotkey(mapping.get("start_recording", "<f8>")): self.startRecording.emit,
                _normalize_hotkey(mapping.get("stop_recording", "<f9>")): self.stopRecording.emit,
                _normalize_hotkey(mapping.get("pause_recording", "<f7>")): self.pauseRecording.emit,
                _normalize_hotkey(mapping.get("emergency_stop", "<f10>")): self.emergencyStop.emit,
                _normalize_hotkey(mapping.get("pause_playback", "<f6>")): self.pausePlayback.emit,
            }

            def on_release(key: object) -> None:
                key_name = normalize_key_name(str(key))
                callback = callbacks.get(key_name)
                if callback is not None:
                    callback()

            self._listener = keyboard.Listener(on_release=on_release)
            self._listener.start()
        except Exception as exc:
            self._listener = None
            self.registrationFailed.emit(str(exc))

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            finally:
                self._listener = None


def validate_hotkey_conflicts(hotkeys: dict[str, str]) -> list[str]:
    normalized = [_normalize_hotkey(value) for value in hotkeys.values() if value.strip()]
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    return duplicates


def _normalize_hotkey(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    return normalize_key_name(value)
