from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout


class CountdownOverlay(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setModal(False)
        self.remaining = 0
        self.finished_callback: Callable[[], None] | None = None
        self.label = QLabel("", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumSize(240, 160)
        font = self.label.font()
        font.setPointSize(48)
        font.setBold(True)
        self.label.setFont(font)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    def start_countdown(self, seconds: int, callback: Callable[[], None]) -> None:
        self.remaining = max(0, seconds)
        self.finished_callback = callback
        self._update_label()
        self.show()
        self.raise_()
        if self.remaining <= 0:
            self._finish()
        else:
            self.timer.start(1000)

    def _tick(self) -> None:
        self.remaining -= 1
        if self.remaining <= 0:
            self._finish()
        else:
            self._update_label()

    def _update_label(self) -> None:
        self.label.setText(str(self.remaining))

    def _finish(self) -> None:
        self.timer.stop()
        self.hide()
        if self.finished_callback is not None:
            callback = self.finished_callback
            self.finished_callback = None
            callback()
