from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from macro_recorder_plus.platform.windows_monitors import get_monitor_layout


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
        x, y, width, height = _qt_rect_to_native_region(rect)
        self.regionSelected.emit(x, y, width, height)
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
    top_left = _native_to_qt_global(QPoint(int(x), int(y)))
    bottom_right = _native_to_qt_global(QPoint(int(x + width), int(y + height)))
    return QRect(top_left, bottom_right).normalized()


class CircleSelectionOverlay(QWidget):
    """Full-desktop picker that previews a red center point and radius."""

    pointSelected = Signal(int, int)
    cancelled = Signal()

    def __init__(
        self,
        radius: int,
        initial_center: tuple[int, int] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._desktop_rect = _virtual_desktop_rect()
        self._radius = max(0, int(radius))
        self._cursor_global = _native_to_qt_global(QPoint(*initial_center)) if initial_center is not None else None
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
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 35))
        if self._cursor_global is not None:
            center = self.mapFromGlobal(self._cursor_global)
            radius = _native_radius_to_qt(self._radius, self._cursor_global)
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(QColor(255, 0, 0, 32))
            painter.drawEllipse(center, radius, radius)
            painter.setBrush(QColor(255, 0, 0))
            painter.drawEllipse(center, 4, 4)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawText(24, 32, f"Move the pointer to preview the {self._radius}px start circle, then click its center. Esc cancels.")

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        self._cursor_global = event.globalPosition().toPoint()
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() != Qt.LeftButton:
            return
        point = _qt_global_to_native(event.globalPosition().toPoint())
        self.pointSelected.emit(point.x(), point.y())
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(event)


def _qt_rect_to_native_region(rect: QRect) -> tuple[int, int, int, int]:
    top_left = _qt_global_to_native(rect.topLeft())
    bottom_right = _qt_global_to_native(QPoint(rect.x() + rect.width(), rect.y() + rect.height()))
    left = min(top_left.x(), bottom_right.x())
    top = min(top_left.y(), bottom_right.y())
    return (left, top, abs(bottom_right.x() - top_left.x()), abs(bottom_right.y() - top_left.y()))


def _qt_global_to_native(point: QPoint) -> QPoint:
    screen = QGuiApplication.screenAt(point)
    if screen is None:
        return QPoint(point)
    geometry = screen.geometry()
    ratio = max(0.01, float(screen.devicePixelRatio()))
    monitor = _native_monitor_for_screen(screen.name())
    if monitor is None:
        return QPoint(round(point.x() * ratio), round(point.y() * ratio))
    return QPoint(
        monitor.bounds.left + round((point.x() - geometry.left()) * ratio),
        monitor.bounds.top + round((point.y() - geometry.top()) * ratio),
    )


def _native_to_qt_global(point: QPoint) -> QPoint:
    screens = QGuiApplication.screens()
    layout = get_monitor_layout()
    for monitor in layout.monitors:
        if monitor.bounds.left <= point.x() < monitor.bounds.right and monitor.bounds.top <= point.y() < monitor.bounds.bottom:
            screen = next((candidate for candidate in screens if candidate.name().casefold() == monitor.identifier.casefold()), None)
            if screen is None:
                break
            ratio = max(0.01, float(screen.devicePixelRatio()))
            geometry = screen.geometry()
            return QPoint(
                geometry.left() + round((point.x() - monitor.bounds.left) / ratio),
                geometry.top() + round((point.y() - monitor.bounds.top) / ratio),
            )
    screen = QGuiApplication.screenAt(point)
    ratio = max(0.01, float(screen.devicePixelRatio())) if screen is not None else 1.0
    return QPoint(round(point.x() / ratio), round(point.y() / ratio))


def _native_monitor_for_screen(screen_name: str):
    name = str(screen_name).casefold()
    return next((monitor for monitor in get_monitor_layout().monitors if monitor.identifier.casefold() == name), None)


def _native_radius_to_qt(radius: int, point: QPoint) -> int:
    screen = QGuiApplication.screenAt(point)
    ratio = max(0.01, float(screen.devicePixelRatio())) if screen is not None else 1.0
    return max(0, round(int(radius) / ratio))
