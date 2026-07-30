from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget


class ImageClickPreview(QWidget):
    """Image preview with the configured relative click point and radius."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap = QPixmap()
        self._path = ""
        self._offset = (0, 0)
        self._radius = 0
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("The red dot is the click center; the red circle is the random click area.")

    def set_preview(self, image_path: str, offset: tuple[int, int], radius: int) -> None:
        self._path = str(image_path)
        self._offset = (int(offset[0]), int(offset[1]))
        self._radius = max(0, int(radius))
        expanded = os.path.expandvars(self._path)
        path = Path(expanded).expanduser()
        self._pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(20, 20, 20, 35))
        painter.setPen(QPen(QColor(128, 128, 128), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._pixmap.isNull():
            painter.setPen(QColor(170, 170, 170))
            message = "Choose an image to preview the click circle" if not self._path else "Image preview unavailable"
            painter.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.AlignCenter | Qt.TextWordWrap, message)
            return

        available = self.rect().adjusted(8, 8, -8, -8)
        scaled = self._pixmap.scaled(available.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        left = available.left() + (available.width() - scaled.width()) // 2
        top = available.top() + (available.height() - scaled.height()) // 2
        painter.drawPixmap(left, top, scaled)

        scale = scaled.width() / max(1, self._pixmap.width())
        center_x = left + (self._pixmap.width() / 2.0 + self._offset[0]) * scale
        center_y = top + (self._pixmap.height() / 2.0 + self._offset[1]) * scale
        display_radius = self._radius * scale
        painter.setPen(QPen(QColor(255, 0, 0), 2))
        painter.setBrush(QColor(255, 0, 0, 30))
        if display_radius > 0:
            painter.drawEllipse(
                int(round(center_x - display_radius)),
                int(round(center_y - display_radius)),
                max(1, int(round(display_radius * 2))),
                max(1, int(round(display_radius * 2))),
            )
        painter.setBrush(QColor(255, 0, 0))
        painter.drawEllipse(int(round(center_x - 3)), int(round(center_y - 3)), 6, 6)
