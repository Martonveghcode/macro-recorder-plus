from __future__ import annotations

import ctypes
import sys
from typing import Any

from macro_recorder_plus.models.environment import MonitorInfo, RecordedEnvironment, Rect

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
MONITORINFOF_PRIMARY = 1


def get_monitor_layout() -> RecordedEnvironment:
    if sys.platform != "win32":
        return RecordedEnvironment()

    user32 = ctypes.windll.user32
    left = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    virtual_desktop = Rect(left, top, left + width, top + height)
    monitors: list[MonitorInfo] = []

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(RECT),
        ctypes.c_void_p,
    )

    def callback(hmonitor: Any, hdc: Any, rect: Any, data: Any) -> int:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            bounds = Rect(info.rcMonitor.left, info.rcMonitor.top, info.rcMonitor.right, info.rcMonitor.bottom)
            work = Rect(info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
            dpi = _get_monitor_dpi(hmonitor)
            monitors.append(
                MonitorInfo(
                    identifier=info.szDevice,
                    bounds=bounds,
                    work_area=work,
                    primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    dpi=dpi,
                    scale_factor=round(dpi / 96, 3) if dpi else None,
                )
            )
        return 1

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(callback), 0)
    return RecordedEnvironment(virtual_desktop=virtual_desktop, monitors=monitors)


def _get_monitor_dpi(hmonitor: Any) -> int | None:
    try:
        shcore = ctypes.windll.shcore
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        if shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
            return int(dpi_x.value)
    except Exception:
        return None
    return None


def transform_point(
    x: int,
    y: int,
    recorded: RecordedEnvironment,
    current: RecordedEnvironment,
    *,
    mode: str = "exact",
) -> tuple[int, int]:
    if mode == "exact" or not recorded.virtual_desktop.width or not current.virtual_desktop.width:
        return clamp_point(x, y, current.virtual_desktop)

    rx = (x - recorded.virtual_desktop.left) / max(1, recorded.virtual_desktop.width)
    ry = (y - recorded.virtual_desktop.top) / max(1, recorded.virtual_desktop.height)
    nx = current.virtual_desktop.left + round(rx * current.virtual_desktop.width)
    ny = current.virtual_desktop.top + round(ry * current.virtual_desktop.height)
    return clamp_point(nx, ny, current.virtual_desktop)


def clamp_point(x: int, y: int, bounds: Rect) -> tuple[int, int]:
    if bounds.width <= 0 or bounds.height <= 0:
        return x, y
    return (
        min(max(int(x), bounds.left), bounds.right - 1),
        min(max(int(y), bounds.top), bounds.bottom - 1),
    )
