from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from macro_recorder_plus.models.actions import MacroAction
from macro_recorder_plus.models.environment import RecordedEnvironment
from macro_recorder_plus.playback.playback_worker import PlaybackWorker
from macro_recorder_plus.playback.safety_controller import SafetyController


class PlaybackEngine(QObject):
    progress = Signal(int, object)
    preActionProgress = Signal(int, object)
    status = Signal(str)
    playbackContext = Signal(int, object)
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

    def play(
        self,
        actions: list[MacroAction],
        *,
        pre_actions: list[MacroAction] | None = None,
        start_index: int = 0,
        end_index: int | None = None,
        repeat_count: int = 1,
        loop_delay_min: float = 0.0,
        loop_delay_max: float = 0.0,
        speed: float = 1.0,
        respect_action_delays: bool = True,
        initial_image_found: bool | None = None,
        recorded_environment: RecordedEnvironment | None = None,
        current_environment_snapshot: RecordedEnvironment | None = None,
        coordinate_mode: str = "exact",
    ) -> None:
        if self.running:
            return
        self.safety.reset()
        self._thread = QThread(self)
        self._worker = PlaybackWorker(
            actions,
            pre_actions=pre_actions,
            start_index=start_index,
            end_index=end_index,
            repeat_count=repeat_count,
            loop_delay_min=loop_delay_min,
            loop_delay_max=loop_delay_max,
            speed=speed,
            respect_action_delays=respect_action_delays,
            initial_image_found=initial_image_found,
            safety=self.safety,
            recorded_environment=recorded_environment,
            current_environment_snapshot=current_environment_snapshot,
            coordinate_mode=coordinate_mode,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress)
        self._worker.preActionProgress.connect(self.preActionProgress)
        self._worker.status.connect(self.status)
        self._worker.playbackContext.connect(self.playbackContext)
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
