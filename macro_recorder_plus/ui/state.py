from __future__ import annotations

from enum import Enum


class AppState(str, Enum):
    IDLE = "Idle"
    COUNTING_DOWN = "Counting down"
    RECORDING = "Recording"
    RECORDING_PAUSED = "Recording paused"
    PLAYING = "Playing"
    PLAYBACK_PAUSED = "Playback paused"
    EXPORTING = "Exporting"
    ERROR = "Error"
