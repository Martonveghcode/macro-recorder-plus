from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RegionSelectionOverlay(QWidget):
    """Transparent full-desktop red-box overlay used to select image-search regions."""

    regionSelected = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self, initial_region: tuple[int, int, int, int] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._desktop_rect = _virtual_desktop_rect()
        self._initial_region = _rect_from_region(initial_region)
        self._drag_start: QPoint | None = None
        self._drag_current: QPoint | None = None
        self._selected_rect: QRect | None = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(self._desktop_rect)
        self.setFocusPolicy(Qt.StrongFocus)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.activateWindow()
        self.raise_()
        self.setFocus(Qt.ActiveWindowFocusReason)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 45))

        selected = self._current_selection_rect()
        if self._initial_region is not None:
            self._draw_rect(painter, self._to_local(self._initial_region), QColor(255, 64, 64), 2)
        if selected is not None:
            self._draw_rect(painter, self._to_local(selected), QColor(255, 0, 0), 3)

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(
            24,
            32,
            "Drag to select image-recognition region. Current/selected region is red. Press Esc to cancel.",
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        self._drag_start = event.globalPosition().toPoint()
        self._drag_current = self._drag_start
        self._selected_rect = None
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self._drag_start is None:
            return
        self._drag_current = event.globalPosition().toPoint()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton or self._drag_start is None:
            return
        self._drag_current = event.globalPosition().toPoint()
        rect = self._current_selection_rect()
        self._drag_start = None
        self._drag_current = None
        if rect is None or rect.width() < 4 or rect.height() < 4:
            self.update()
            return
        self._selected_rect = rect
        self.regionSelected.emit(rect.x(), rect.y(), rect.width(), rect.height())
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(event)

    def _current_selection_rect(self) -> QRect | None:
        if self._drag_start is None or self._drag_current is None:
            return self._selected_rect
        return QRect(self._drag_start, self._drag_current).normalized().intersected(self._desktop_rect)

    def _to_local(self, rect: QRect) -> QRect:
        return rect.translated(-self._desktop_rect.left(), -self._desktop_rect.top())

    def _draw_rect(self, painter: QPainter, rect: QRect, color: QColor, width: int) -> None:
        if rect.isNull() or rect.isEmpty():
            return
        painter.setPen(QPen(color, width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))


def _virtual_desktop_rect() -> QRect:
    screens = QGuiApplication.screens()
    if not screens:
        return QRect(0, 0, 1920, 1080)
    rect = QRect(screens[0].geometry())
    for screen in screens[1:]:
        rect = rect.united(screen.geometry())
    return rect


def _rect_from_region(region: tuple[int, int, int, int] | None) -> QRect | None:
    if region is None:
        return None
    x, y, width, height = region
    if width <= 0 or height <= 0:
        return None
    return QRect(int(x), int(y), int(width), int(height))
