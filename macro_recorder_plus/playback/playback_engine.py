from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from macro_recorder_plus.models.actions import MacroAction
from macro_recorder_plus.playback.playback_worker import PlaybackWorker
from macro_recorder_plus.playback.safety_controller import SafetyController


class PlaybackEngine(QObject):
    progress = Signal(int, object)
    status = Signal(str)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: PlaybackWorker | None = None
        self.safety = SafetyController()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def play(self, actions: list[MacroAction], *, start_index: int = 0, speed: float = 1.0) -> None:
        if self.running:
            return
        self.safety.reset()
        self._thread = QThread(self)
        self._worker = PlaybackWorker(actions, start_index=start_index, speed=speed, safety=self.safety)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.status.connect(self.status)
        self._worker.error.connect(self.error)
        self._worker.finished.connect(self.finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear)
        self._thread.start()

    def stop(self) -> None:
        self.safety.stop()
        if self._worker is not None:
            self._worker.stop()

    def pause_or_resume(self) -> None:
        if self._worker is not None:
            self._worker.pause_or_resume()

    def _clear(self) -> None:
        self._thread = None
        self._worker = None
