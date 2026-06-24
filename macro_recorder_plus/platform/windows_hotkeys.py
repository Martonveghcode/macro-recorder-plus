from __future__ import annotations

from PySide6.QtCore import QObject, Signal


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

            self._listener = keyboard.GlobalHotKeys(
                {
                    mapping.get("start_recording", "<f8>"): self.startRecording.emit,
                    mapping.get("stop_recording", "<f9>"): self.stopRecording.emit,
                    mapping.get("pause_recording", "<f7>"): self.pauseRecording.emit,
                    mapping.get("emergency_stop", "<f10>"): self.emergencyStop.emit,
                    mapping.get("pause_playback", "<f6>"): self.pausePlayback.emit,
                }
            )
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
    normalized = [value.strip().lower() for value in hotkeys.values() if value.strip()]
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    return duplicates
