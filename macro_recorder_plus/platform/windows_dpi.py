from __future__ import annotations

import ctypes
import sys


def set_process_dpi_awareness() -> str:
    if sys.platform != "win32":
        return "not-windows"

    user32 = ctypes.windll.user32
    try:
        awareness_context_per_monitor_v2 = ctypes.c_void_p(-4)
        if user32.SetProcessDpiAwarenessContext(awareness_context_per_monitor_v2):
            return "per-monitor-v2"
    except Exception:
        pass

    try:
        shcore = ctypes.windll.shcore
        if shcore.SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
    except Exception:
        pass

    try:
        user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "unavailable"
