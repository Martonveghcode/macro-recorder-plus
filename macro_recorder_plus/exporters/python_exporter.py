from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from textwrap import dedent

from macro_recorder_plus.models.actions import ActionType
from macro_recorder_plus.models.macro import MacroDocument


RUNTIME_DIR_NAME = "macro_recorder_plus_runtime"
DEPENDENCIES_DIR_NAME = "dependencies"
ASSETS_DIR_NAME = "macro_recorder_plus_assets"
RUNTIME_REQUIREMENTS = ("pynput>=1.7.7", "Pillow>=10", "numpy>=1.26")
RUNTIME_IMPORT_DIRS = ("pynput", "PIL", "numpy")
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def default_export_directory() -> Path:
    configured = os.environ.get("MACRO_RECORDER_PLUS_EXPORT_DIR")
    if configured:
        return Path(configured)

    home = Path.home()
    user_profile = Path(os.environ.get("USERPROFILE", str(home)))
    candidates = [
        user_profile / "moodle-proxy" / "Desktop",
        user_profile / "Desktop",
        Path(os.environ.get("OneDrive", "")) / "Desktop",
        home / "Desktop",
        home / "Documents",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        if not str(candidate):
            continue
        candidate = candidate.expanduser()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate / "Macro Recorder Plus Exports"
    return home / "Macro Recorder Plus Exports"


def safe_script_filename(name: str) -> str:
    value = INVALID_FILENAME_CHARS.sub("_", str(name or "")).strip(" ._")
    value = re.sub(r"\s+", "_", value).lower()
    if not value:
        value = "exported_macro"
    if value.endswith(".py"):
        return value
    if value.endswith("_macro"):
        return f"{value}.py"
    return f"{value}_macro.py"


def safe_batch_filename(script_path: Path) -> str:
    stem = INVALID_FILENAME_CHARS.sub("_", script_path.stem).strip(" ._")
    stem = re.sub(r"\s+", "_", stem).lower() or "macro"
    return f"run_{stem}.bat"


def export_support_directory(target: str | Path) -> Path:
    """Keep auxiliary export files out of the visible Desktop when possible."""
    target = Path(target)
    if target.parent.name.casefold() == "desktop":
        return target.parent / "misc"
    return target.parent


class PythonExporter:
    def __init__(self, *, python_executable: str | Path | None = None) -> None:
        configured = str(python_executable).strip() if python_executable else ""
        self.python_executable = configured or str(Path(sys.executable))

    def render(self, document: MacroDocument, *, runtime_relative_path: str | Path = RUNTIME_DIR_NAME) -> str:
        payload = json.dumps(document.to_dict(), separators=(",", ":"), sort_keys=True)
        template = '''\
#!/usr/bin/env python3
"""Standalone macro exported by Macro Recorder +."""
from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import math
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from getpass import getpass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR / Path(__RUNTIME_RELATIVE_PATH__)
LOCAL_DEPS = RUNTIME_DIR / "__DEPENDENCIES_DIR_NAME__"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

REQUIRED_PACKAGES = __REQUIRED_PACKAGES__
REQUIRED_IMPORTS = ("pynput", "PIL", "numpy")
MACRO = json.loads(__MACRO_JSON__)


def is_dedicated_console_launch():
    """Treat a no-argument Windows run as a double-click launch."""
    return sys.platform == "win32" and len(sys.argv) == 1


def hide_console_window():
    if sys.platform != "win32":
        return
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE


def set_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def current_virtual_desktop():
    if sys.platform != "win32":
        return {"left": 0, "top": 0, "right": 0, "bottom": 0}
    user32 = ctypes.windll.user32
    left = int(user32.GetSystemMetrics(76))
    top = int(user32.GetSystemMetrics(77))
    width = int(user32.GetSystemMetrics(78))
    height = int(user32.GetSystemMetrics(79))
    return {"left": left, "top": top, "right": left + width, "bottom": top + height}


def rect_size(rect):
    return (
        max(0, int(rect.get("right", 0)) - int(rect.get("left", 0))),
        max(0, int(rect.get("bottom", 0)) - int(rect.get("top", 0))),
    )


def clamp_point(x, y, bounds):
    width, height = rect_size(bounds)
    if width <= 0 or height <= 0:
        return int(x), int(y)
    left = int(bounds.get("left", 0))
    top = int(bounds.get("top", 0))
    return (
        min(max(int(x), left), left + width - 1),
        min(max(int(y), top), top + height - 1),
    )


def transform_point(x, y, recorded_environment, current_bounds, mode="exact"):
    recorded_bounds = recorded_environment.get("virtual_desktop", {})
    recorded_width, recorded_height = rect_size(recorded_bounds)
    current_width, current_height = rect_size(current_bounds)
    if str(mode) == "exact" or recorded_width <= 0 or current_width <= 0:
        return clamp_point(x, y, current_bounds)
    recorded_left = int(recorded_bounds.get("left", 0))
    recorded_top = int(recorded_bounds.get("top", 0))
    current_left = int(current_bounds.get("left", 0))
    current_top = int(current_bounds.get("top", 0))
    relative_x = (int(x) - recorded_left) / max(1, recorded_width)
    relative_y = (int(y) - recorded_top) / max(1, recorded_height)
    transformed_x = current_left + round(relative_x * current_width)
    transformed_y = current_top + round(relative_y * current_height)
    return clamp_point(transformed_x, transformed_y, current_bounds)


def transform_action_coordinates(action, recorded_environment, current_bounds, coordinate_mode):
    action_type = action.get("type")
    if action_type not in {"mouse_move", "mouse_button", "scroll"}:
        return action
    transformed = dict(action)
    params = dict(action.get("params", {}))
    if action_type == "mouse_move":
        for key in ("start", "end"):
            point = params.get(key)
            if point:
                params[key] = list(
                    transform_point(point[0], point[1], recorded_environment, current_bounds, coordinate_mode)
                )
        if params.get("path"):
            params["path"] = [
                [
                    *transform_point(point[0], point[1], recorded_environment, current_bounds, coordinate_mode),
                    point[2],
                ]
                for point in params["path"]
                if len(point) >= 3
            ]
    elif "x" in params and "y" in params:
        params["x"], params["y"] = transform_point(
            params["x"], params["y"], recorded_environment, current_bounds, coordinate_mode
        )
    transformed["params"] = params
    return transformed


def position_mouse(mouse_controller, x, y, attempts=3, tolerance=1):
    target = (int(x), int(y))
    last_position = None
    for attempt in range(max(1, int(attempts))):
        mouse_controller.position = target
        actual = getattr(mouse_controller, "position", target)
        try:
            last_position = (int(actual[0]), int(actual[1]))
        except (TypeError, ValueError, IndexError):
            last_position = target
        if abs(last_position[0] - target[0]) <= tolerance and abs(last_position[1] - target[1]) <= tolerance:
            return target
        if attempt + 1 < attempts:
            time.sleep(0.001)
    raise RuntimeError(f"Mouse did not reach ({target[0]}, {target[1]}); Windows reported {last_position}")


def install_dependencies():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_DEPS.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--target",
        str(LOCAL_DEPS),
    ]
    requirements = RUNTIME_DIR / "requirements.txt"
    if requirements.exists():
        command.extend(["-r", str(requirements)])
    else:
        command.extend(REQUIRED_PACKAGES)
    print(f"Installing export dependencies into {LOCAL_DEPS}...")
    return subprocess.call(command)


def ensure_dependencies():
    missing = [name for name in REQUIRED_IMPORTS if importlib.util.find_spec(name) is None]
    if not missing:
        return True
    print(f"Missing export dependencies: {', '.join(missing)}")
    if install_dependencies() != 0:
        return False
    if str(LOCAL_DEPS) not in sys.path:
        sys.path.insert(0, str(LOCAL_DEPS))
    importlib.invalidate_caches()
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_IMPORTS)


def import_input_modules():
    try:
        from pynput import keyboard, mouse
        return keyboard, mouse
    except Exception as exc:
        print(f"pynput is required: {exc}", file=sys.stderr)
        print("Run this script with --install-deps first.", file=sys.stderr)
        return None, None


def key_from_name(name, keyboard):
    lookup = {
        "ctrl": keyboard.Key.ctrl,
        "shift": keyboard.Key.shift,
        "alt": keyboard.Key.alt,
        "win": keyboard.Key.cmd,
        "enter": keyboard.Key.enter,
        "escape": keyboard.Key.esc,
        "backspace": keyboard.Key.backspace,
        "delete": keyboard.Key.delete,
        "home": keyboard.Key.home,
        "end": keyboard.Key.end,
        "tab": keyboard.Key.tab,
        "space": keyboard.Key.space,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
    }
    key = str(name).lower().replace("key.", "")
    if key in lookup:
        return lookup[key]
    if key.startswith("f") and key[1:].isdigit():
        return getattr(keyboard.Key, key)
    return keyboard.KeyCode.from_char(key)


def button_from_name(name, mouse):
    return getattr(mouse.Button, str(name).lower().replace("button.", ""))


def mouse_move_points(action):
    params = action.get("params", {})
    points = []
    for point in params.get("path", []) or []:
        if len(point) >= 3:
            points.append((int(point[0]), int(point[1]), float(point[2])))
    if points:
        return points
    start = params.get("start")
    end = params.get("end")
    if start and end:
        return [
            (int(start[0]), int(start[1]), float(action.get("timestamp", 0))),
            (int(end[0]), int(end[1]), float(action.get("timestamp", 0)) + float(action.get("duration", 0))),
        ]
    if end:
        return [(int(end[0]), int(end[1]), 0.0)]
    return []


def resolve_image_path(image_path):
    path = Path(str(image_path)).expanduser()
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def resolve_file_path(file_path):
    value = os.path.expandvars(str(file_path)).strip().strip('"')
    if not value:
        raise RuntimeError("Open File action is missing a file path")
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return SCRIPT_DIR / path


def open_file_with_default_app(file_path, *, target_monitor="default", auto_focus=False, timeout=10.0, window_placement=None):
    path = resolve_file_path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if sys.platform == "win32":
        if auto_focus or target_monitor != "default" or window_placement:
            pid = shell_execute_file_with_process_id(path)
            if pid is not None:
                arrange_process_window(pid, target_monitor=target_monitor, auto_focus=auto_focus, timeout=timeout, window_placement=window_placement)
                return
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def shell_execute_file_with_process_id(path):
    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("fMask", ctypes.c_ulong),
            ("hwnd", ctypes.c_void_p),
            ("lpVerb", ctypes.c_wchar_p),
            ("lpFile", ctypes.c_wchar_p),
            ("lpParameters", ctypes.c_wchar_p),
            ("lpDirectory", ctypes.c_wchar_p),
            ("nShow", ctypes.c_int),
            ("hInstApp", ctypes.c_void_p),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", ctypes.c_wchar_p),
            ("hkeyClass", ctypes.c_void_p),
            ("dwHotKey", ctypes.c_ulong),
            ("hIcon", ctypes.c_void_p),
            ("hProcess", ctypes.c_void_p),
        ]

    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
    info.fMask = 0x00000040
    info.lpVerb = "open"
    info.lpFile = str(path)
    info.nShow = 1
    if not shell32.ShellExecuteExW(ctypes.byref(info)) or not info.hProcess:
        return None
    try:
        return int(kernel32.GetProcessId(info.hProcess))
    finally:
        kernel32.CloseHandle(info.hProcess)


def arrange_process_window(process_id, *, target_monitor="default", auto_focus=False, timeout=10.0, window_placement=None):
    if sys.platform != "win32" or not process_id:
        return False
    hwnd = find_top_level_window_for_process(int(process_id), timeout=max(0.0, timeout))
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    if window_placement:
        restore_window_placement(hwnd, window_placement)
    else:
        monitor = select_target_monitor(target_monitor)
        if monitor is not None:
            move_window_to_monitor(hwnd, monitor)
    if auto_focus:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    return True


def find_top_level_window_for_process(process_id, *, timeout):
    user32 = ctypes.windll.user32
    deadline = time.perf_counter() + timeout
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def find_once():
        found = []

        def callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
                return True
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if int(window_pid.value) == process_id:
                found.append(int(hwnd))
                return False
            return True

        user32.EnumWindows(enum_proc_type(callback), 0)
        return found[0] if found else None

    while True:
        hwnd = find_once()
        if hwnd is not None:
            return hwnd
        if time.perf_counter() >= deadline:
            return None
        time.sleep(0.05)


def process_executable_path(process_id):
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, process_id)
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_top_level_window_for_executable(executable, *, timeout=10.0, title_hint=""):
    if sys.platform != "win32" or not executable:
        return None
    expected = str(executable).casefold()
    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    deadline = time.perf_counter() + max(0.0, timeout)
    while True:
        found = []

        def callback(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
                return True
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if process_executable_path(int(window_pid.value)).casefold() != expected:
                return True
            length = int(user32.GetWindowTextLengthW(hwnd))
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, length + 1)
            found.append((int(hwnd), title_buffer.value))
            return True

        user32.EnumWindows(enum_proc_type(callback), 0)
        if found:
            hint = str(title_hint).casefold().strip()
            if hint:
                exact = next((hwnd for hwnd, title in found if title.casefold() == hint), None)
                if exact is not None:
                    return exact
                hinted = next(
                    (
                        hwnd
                        for hwnd, title in found
                        if hint in title.casefold() or title.casefold() in hint
                    ),
                    None,
                )
                if hinted is not None:
                    return hinted
            return found[0][0]
        if time.perf_counter() >= deadline:
            return None
        time.sleep(0.05)


def arrange_existing_window(placement, *, auto_focus=False, timeout=10.0):
    hwnd = find_top_level_window_for_executable(
        placement.get("process_path", ""),
        timeout=timeout,
        title_hint=placement.get("window_title", ""),
    )
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    restore_window_placement(hwnd, placement)
    if auto_focus:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    return True


def select_target_monitor(target_monitor):
    value = str(target_monitor or "default").lower()
    if value == "default" or sys.platform != "win32":
        return None
    monitors = windows_monitors()
    if not monitors:
        return None
    if value == "primary":
        return next((monitor for monitor in monitors if monitor["primary"]), monitors[0])
    if value.isdigit():
        index = int(value) - 1
        if 0 <= index < len(monitors):
            return monitors[index]
    return None


def windows_monitors():
    user32 = ctypes.windll.user32

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

    monitors = []
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(RECT), ctypes.c_void_p)

    def callback(hmonitor, hdc, rect, data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            monitors.append(
                {
                    "work": (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom),
                    "primary": bool(info.dwFlags & 1),
                    "identifier": info.szDevice,
                }
            )
        return 1

    user32.EnumDisplayMonitors(0, 0, enum_proc_type(callback), 0)
    return monitors


def move_window_to_monitor(hwnd, monitor):
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return
    left, top, right, bottom = monitor["work"]
    work_width = max(1, int(right - left))
    work_height = max(1, int(bottom - top))
    width = min(max(1, int(rect.right - rect.left)), work_width)
    height = min(max(1, int(rect.bottom - rect.top)), work_height)
    x = int(left) + max(0, (work_width - width) // 2)
    y = int(top) + max(0, (work_height - height) // 2)
    user32.SetWindowPos(hwnd, 0, x, y, width, height, 0x0004)


def restore_window_placement(hwnd, placement):
    monitors = windows_monitors()
    monitor = next(
        (item for item in monitors if item.get("identifier") == placement.get("monitor_identifier")),
        None,
    )
    if monitor is None:
        try:
            index = int(placement.get("monitor_index", -1))
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < len(monitors):
            monitor = monitors[index]
    width = max(1, int(placement.get("width", 1) or 1))
    height = max(1, int(placement.get("height", 1) or 1))
    if monitor is not None:
        left, top, right, bottom = monitor["work"]
        width = min(width, max(1, right - left))
        height = min(height, max(1, bottom - top))
        x = min(max(left + int(placement.get("offset_x", 0) or 0), left), right - width)
        y = min(max(top + int(placement.get("offset_y", 0) or 0), top), bottom - height)
    else:
        x = int(placement.get("x", 0) or 0)
        y = int(placement.get("y", 0) or 0)
    ctypes.windll.user32.SetWindowPos(hwnd, 0, x, y, width, height, 0x0004)
    if placement.get("maximized"):
        ctypes.windll.user32.ShowWindow(hwnd, 3)


def region_from_params(params):
    width = int(params.get("region_width", 0) or 0)
    height = int(params.get("region_height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    return (
        int(params.get("region_x", 0) or 0),
        int(params.get("region_y", 0) or 0),
        width,
        height,
    )


def poll_interval_from_params(params):
    checks_per_second = params.get("checks_per_second")
    if checks_per_second is not None:
        return max(0.01, 1.0 / max(0.1, float(checks_per_second)))
    return max(0.05, float(params.get("poll_interval", 0.25)))


def wait_until_found_from_params(params, timeout):
    wait_until_found = bool(params.get("wait_until_found", True))
    if "wait_until_found" not in params and timeout <= 0:
        return False
    return wait_until_found


def find_image_on_screen(params, stop_event=None):
    from PIL import Image, ImageGrab
    import numpy as np

    image_path = resolve_image_path(params.get("image_path", ""))
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    template = Image.open(image_path)
    confidence = min(1.0, max(0.0, float(params.get("confidence", 0.85))))
    timeout = max(0.0, float(params.get("timeout", 5.0)))
    poll_interval = poll_interval_from_params(params)
    wait_until_found = wait_until_found_from_params(params, timeout)
    grayscale = bool(params.get("grayscale", True))
    region = region_from_params(params)
    deadline = None if wait_until_found and timeout <= 0 else time.perf_counter() + timeout

    while True:
        if stop_event is not None and stop_event.is_set():
            return None
        screenshot, offset_x, offset_y = grab_screen(ImageGrab, region)
        match = locate_image_in_image(screenshot, template, np, confidence=confidence, grayscale=grayscale)
        if match is not None:
            x, y, width, height, score = match
            return {
                "x": x + offset_x,
                "y": y + offset_y,
                "width": width,
                "height": height,
                "confidence": score,
                "center": (x + offset_x + width // 2, y + offset_y + height // 2),
            }
        if not wait_until_found:
            return None
        if deadline is not None and time.perf_counter() >= deadline:
            return None
        sleep_seconds = poll_interval if deadline is None else min(poll_interval, max(0.0, deadline - time.perf_counter()))
        if stop_event is not None:
            if not sleep_until(time.perf_counter() + sleep_seconds, stop_event):
                return None
        else:
            time.sleep(sleep_seconds)


def grab_screen(image_grab_module, region):
    if region is not None:
        x, y, width, height = region
        screenshot = image_grab_module.grab(bbox=(x, y, x + width, y + height))
        return screenshot, int(x), int(y)
    try:
        screenshot = image_grab_module.grab(all_screens=True)
        return screenshot, *virtual_screen_origin()
    except TypeError:
        return image_grab_module.grab(), 0, 0


def virtual_screen_origin():
    if not hasattr(ctypes, "windll"):
        return (0, 0)
    try:
        user32 = ctypes.windll.user32
        return (int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77)))
    except Exception:
        return (0, 0)


def locate_image_in_image(screenshot, template, np, *, confidence=0.85, grayscale=True, max_full_checks=2000):
    screen_array = image_to_array(screenshot, np, grayscale=grayscale)
    template_array = image_to_array(template, np, grayscale=grayscale)
    screen_height, screen_width = screen_array.shape[:2]
    template_height, template_width = template_array.shape[:2]
    if template_width <= 0 or template_height <= 0:
        return None
    if template_width > screen_width or template_height > screen_height:
        return None

    candidate_height = screen_height - template_height + 1
    candidate_width = screen_width - template_width + 1
    mask = np.ones((candidate_height, candidate_width), dtype=bool)
    sample_points = sample_points_for_template(template_width, template_height)
    pixel_threshold = max(8.0, (1.0 - confidence) * 255.0 * 3.0)

    for sample_x, sample_y in sample_points:
        screen_slice = screen_array[sample_y : sample_y + candidate_height, sample_x : sample_x + candidate_width]
        template_pixel = template_array[sample_y, sample_x]
        diff = np.abs(screen_slice - template_pixel)
        if diff.ndim == 3:
            diff = diff.mean(axis=2)
        mask &= diff <= pixel_threshold
        if not mask.any():
            return None

    candidate_rows, candidate_cols = np.nonzero(mask)
    if len(candidate_rows) == 0:
        return None
    if len(candidate_rows) > max_full_checks:
        candidate_rows, candidate_cols = best_sampled_candidates(
            screen_array,
            template_array,
            candidate_rows,
            candidate_cols,
            sample_points,
            np,
            max_full_checks,
        )

    best = None
    for y, x in zip(candidate_rows, candidate_cols):
        window = screen_array[y : y + template_height, x : x + template_width]
        score = 1.0 - float(np.abs(window - template_array).mean()) / 255.0
        if best is None or score > best[4]:
            best = (int(x), int(y), template_width, template_height, score)
    if best is None or best[4] < confidence:
        return None
    return best


def image_to_array(image, np, *, grayscale):
    converted = image.convert("L" if grayscale else "RGB")
    return np.asarray(converted, dtype=np.float32)


def sample_points_for_template(width, height):
    x_values = sorted({0, width // 4, width // 2, (width * 3) // 4, width - 1})
    y_values = sorted({0, height // 4, height // 2, (height * 3) // 4, height - 1})
    points = [(x, y) for y in y_values for x in x_values]
    step_x = max(1, width // 6)
    step_y = max(1, height // 6)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            points.append((min(width - 1, x), min(height - 1, y)))
    return list(dict.fromkeys(points))


def best_sampled_candidates(screen_array, template_array, candidate_rows, candidate_cols, sample_points, np, limit):
    scores = np.zeros(len(candidate_rows), dtype=np.float32)
    for sample_x, sample_y in sample_points:
        screen_values = screen_array[candidate_rows + sample_y, candidate_cols + sample_x]
        template_pixel = template_array[sample_y, sample_x]
        diff = np.abs(screen_values - template_pixel)
        if diff.ndim == 2:
            diff = diff.mean(axis=1)
        scores += diff
    scores /= max(1, len(sample_points))
    best_indexes = np.argsort(scores)[:limit]
    return candidate_rows[best_indexes], candidate_cols[best_indexes]


def execute_image_click(params, mouse_controller, mouse, stop_event=None, held_buttons=None, speed=1.0):
    match = find_image_on_screen(params, stop_event=stop_event)
    if match is None:
        if stop_event is not None and stop_event.is_set():
            return None
        if params.get("on_not_found", "error") == "skip":
            print(f"Image not found, skipping: {params.get('image_path', '')}", file=sys.stderr)
            return False
        raise RuntimeError(f"Image not found on screen: {params.get('image_path', '')}")

    position_mouse(mouse_controller, *match["center"])
    click_action = str(params.get("click_action", "left_click"))
    if click_action == "move_only":
        return True
    if click_action == "custom_movement":
        execute_image_movement(params, match, mouse_controller, mouse, stop_event=stop_event, held_buttons=held_buttons, speed=speed)
        return None if stop_event is not None and stop_event.is_set() else True
    if click_action == "double_click":
        button = button_from_name("left", mouse)
        for _ in range(2):
            mouse_controller.press(button)
            mouse_controller.release(button)
            time.sleep(0.05)
        return True

    button = button_from_name(click_action.replace("_click", ""), mouse)
    mouse_controller.press(button)
    mouse_controller.release(button)
    return True


def execute_image_movement(params, match, mouse_controller, mouse, stop_event=None, held_buttons=None, speed=1.0):
    points = image_movement_points(params, match)
    if not points:
        return
    interpolated_points = interpolated_mouse_points(points)
    if not interpolated_points:
        return
    first_x, first_y, _ = interpolated_points[0]
    position_mouse(mouse_controller, first_x, first_y)
    apply_image_movement_button(params, mouse_controller, mouse, "start", held_buttons)
    start_time = time.perf_counter()
    for x, y, relative_time in interpolated_points[1:]:
        target = start_time + (relative_time / max(0.01, speed))
        if stop_event is not None:
            if not sleep_until(target, stop_event):
                return
        else:
            remaining = target - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
        position_mouse(mouse_controller, x, y)
    apply_image_movement_button(params, mouse_controller, mouse, "end", held_buttons)


def image_movement_points(params, match):
    center_x, center_y = match["center"]
    points = []
    for point in params.get("movement_path", []) or []:
        if len(point) >= 3:
            points.append((center_x + int(point[0]), center_y + int(point[1]), max(0.0, float(point[2]))))
    if points:
        return points
    start_offset = offset_pair(params.get("movement_start_offset", [0, 0]))
    end_offset = offset_pair(params.get("movement_end_offset", [0, 0]))
    duration = max(0.0, float(params.get("movement_duration", 0.0)))
    return [
        (center_x + start_offset[0], center_y + start_offset[1], 0.0),
        (center_x + end_offset[0], center_y + end_offset[1], duration),
    ]


def offset_pair(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return (0, 0)
    return (int(value[0]), int(value[1]))


def apply_image_movement_button(params, mouse_controller, mouse, stage, held_buttons=None):
    button_action = str(params.get("movement_button_action", "none"))
    if button_action == "none":
        return
    button = button_from_name(params.get("movement_button", "left"), mouse)
    if stage == "start":
        if button_action == "click_at_start":
            click_mouse_button(mouse_controller, button)
        elif button_action == "double_click_at_start":
            double_click_mouse_button(mouse_controller, button)
        elif button_action in {"hold_during_move", "press_at_start"}:
            mouse_controller.press(button)
            if held_buttons is not None:
                held_buttons.append(button)
    elif stage == "end":
        if button_action == "click_at_end":
            click_mouse_button(mouse_controller, button)
        elif button_action == "double_click_at_end":
            double_click_mouse_button(mouse_controller, button)
        elif button_action in {"hold_during_move", "release_at_end"}:
            mouse_controller.release(button)
            if held_buttons is not None:
                held_buttons[:] = [held for held in held_buttons if held != button]


def click_mouse_button(mouse_controller, button):
    mouse_controller.press(button)
    mouse_controller.release(button)


def double_click_mouse_button(mouse_controller, button):
    for _ in range(2):
        click_mouse_button(mouse_controller, button)
        time.sleep(0.05)


def conditional_jump_target(params, runtime_state, action_count):
    last_image_found = runtime_state.get("last_image_found")
    if last_image_found is None:
        return None
    target_key = "image_found_action" if last_image_found else "image_not_found_action"
    try:
        action_number = int(params.get(target_key, 0) or 0)
    except (TypeError, ValueError):
        action_number = 0
    if action_number <= 0:
        return None
    target_index = action_number - 1
    if not 0 <= target_index < action_count:
        raise RuntimeError(f"If Image Result target is outside the macro: action {action_number}")
    return target_index


def interpolated_mouse_points(points, hz=60):
    if len(points) <= 1:
        return points
    first_time = points[0][2]
    output = [(points[0][0], points[0][1], 0.0)]
    for previous, current in zip(points, points[1:]):
        x1, y1, t1 = previous
        x2, y2, t2 = current
        segment_duration = max(0.0, t2 - t1)
        steps = max(1, math.ceil(segment_duration * hz))
        for step in range(1, steps + 1):
            alpha = step / steps
            x = round(x1 + (x2 - x1) * alpha)
            y = round(y1 + (y2 - y1) * alpha)
            relative_time = max(0.0, (t1 - first_time) + (segment_duration * alpha))
            output.append((x, y, relative_time))
    return output


def sleep_until(target, stop_event):
    while True:
        if stop_event.is_set():
            return False
        remaining = target - time.perf_counter()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.005))


def clamp_loop_count(value):
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 1
    return min(99999, max(1, count))


def main():
    parser = argparse.ArgumentParser(description="Run an exported Macro Recorder + macro.")
    parser.add_argument("--speed", type=float, default=None, help="Override the saved playback speed.")
    parser.add_argument("--loops", type=int, default=None, help="Override the saved whole-macro loop count.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-action", type=int, default=None)
    parser.add_argument("--end-action", type=int, default=None, help="Stop before this zero-based action index.")
    parser.add_argument("--install-deps", action="store_true", help="Install runtime dependencies into the local export folder.")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable the F10 emergency-stop listener.")
    parser.add_argument("--log-file", type=str, default="", help="Write console output to this file.")
    args = parser.parse_args()

    dedicated_console = is_dedicated_console_launch()
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    log_handle = None
    log_file = args.log_file or (str(RUNTIME_DIR / f"{Path(__file__).stem}.log") if dedicated_console else "")
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("w", encoding="utf-8", buffering=1)
        sys.stdout = log_handle
        sys.stderr = log_handle
    if dedicated_console:
        hide_console_window()

    if args.install_deps:
        return install_dependencies()

    set_dpi_awareness()
    speed = max(
        0.01,
        float(args.speed if args.speed is not None else MACRO.get("settings", {}).get("playback_speed", 1.0)),
    )
    recorded_environment = MACRO.get("recorded_environment", {})
    current_bounds = current_virtual_desktop()
    coordinate_mode = str(MACRO.get("settings", {}).get("coordinate_mode", "exact"))
    stop_event = threading.Event()
    hotkey_listener = None
    held_keys = []
    held_buttons = []
    keyboard_controller = None
    mouse_controller = None
    keyboard = None
    mouse = None

    if not args.dry_run:
        if not ensure_dependencies():
            print("Unable to install the required export dependencies.", file=sys.stderr)
            return 2
        keyboard, mouse = import_input_modules()
        if keyboard is None or mouse is None:
            return 2
        keyboard_controller = keyboard.Controller()
        mouse_controller = mouse.Controller()
        if not args.no_hotkey:
            try:
                hotkey_listener = keyboard.GlobalHotKeys({"<f10>": stop_event.set})
                hotkey_listener.start()
            except Exception as exc:
                print(f"Emergency-stop hotkey unavailable: {exc}", file=sys.stderr)

    def release_all():
        if keyboard_controller is not None:
            for key in reversed(held_keys):
                try:
                    keyboard_controller.release(key)
                except Exception:
                    pass
        if mouse_controller is not None:
            for button in reversed(held_buttons):
                try:
                    mouse_controller.release(button)
                except Exception:
                    pass
        held_keys.clear()
        held_buttons.clear()

    def begin_macro_loop():
        release_all()
        if args.dry_run or mouse_controller is None:
            return
        cursor_start = recorded_environment.get("cursor_start")
        if cursor_start:
            x, y = transform_point(
                cursor_start[0],
                cursor_start[1],
                recorded_environment,
                current_bounds,
                coordinate_mode,
            )
            position_mouse(mouse_controller, x, y)

    try:
        main_actions = MACRO["actions"]
        pre_actions = MACRO.get("pre_actions", [])
        runtime_state = {"last_image_found": None}
        main_start_index = max(0, args.start_action or 0)
        main_end_index = (
            len(main_actions)
            if args.end_action is None
            else min(len(main_actions), max(main_start_index, args.end_action))
        )
        running_pre_actions = bool(pre_actions)
        actions = pre_actions if running_pre_actions else main_actions
        start_index = 0 if running_pre_actions else main_start_index
        macro_loop_count = clamp_loop_count(
            args.loops if args.loops is not None else MACRO.get("settings", {}).get("macro_loop_count", 1)
        )
        macro_loop_index = -1 if running_pre_actions else 0
        loop_needs_initialization = not running_pre_actions
        index = start_index
        while macro_loop_index < macro_loop_count:
            end_index = len(actions) if running_pre_actions else main_end_index
            if index >= end_index:
                if running_pre_actions:
                    running_pre_actions = False
                    actions = main_actions
                    start_index = main_start_index
                    runtime_state["last_image_found"] = None
                    macro_loop_index = 0
                    loop_needs_initialization = True
                    index = start_index
                    continue
                macro_loop_index += 1
                if macro_loop_index >= macro_loop_count:
                    break
                runtime_state["last_image_found"] = None
                loop_needs_initialization = True
                index = start_index
                continue
            if loop_needs_initialization:
                begin_macro_loop()
                loop_needs_initialization = False
            action = actions[index]
            next_index = index + 1
            if stop_event.is_set():
                print("Emergency stop requested", file=sys.stderr)
                return 130
            if not action.get("enabled", True):
                if action.get("type") == "image_click":
                    runtime_state["last_image_found"] = None
                index = next_index
                continue
            for _loop_index in range(clamp_loop_count(action.get("loop_count", 1))):
                if stop_event.is_set():
                    print("Emergency stop requested", file=sys.stderr)
                    return 130
                delay = max(0.0, float(action.get("delay", 0.0))) / speed
                if delay and not args.dry_run:
                    if not sleep_until(time.perf_counter() + delay, stop_event):
                        print("Emergency stop requested", file=sys.stderr)
                        return 130
                print(f"{index}: {action['type']} {action.get('label') or action.get('params', '')}")
                if args.dry_run:
                    continue

                runtime_action = transform_action_coordinates(
                    action,
                    recorded_environment,
                    current_bounds,
                    coordinate_mode,
                )
                params = runtime_action.get("params", {})
                action_type = runtime_action["type"]
                if action_type == "wait":
                    seconds = float(params.get("seconds", action.get("duration", 0))) / speed
                    if not sleep_until(time.perf_counter() + seconds, stop_event):
                        print("Emergency stop requested", file=sys.stderr)
                        return 130
                elif action_type == "open_url":
                    webbrowser.open(params["url"])
                    if params.get("window_placement"):
                        arrange_existing_window(
                            params["window_placement"],
                            auto_focus=bool(params.get("auto_focus", False)),
                        )
                elif action_type == "open_file":
                    open_file_with_default_app(
                        params.get("file_path", ""),
                        target_monitor=params.get("target_monitor", "default"),
                        auto_focus=bool(params.get("auto_focus", False)),
                        window_placement=params.get("window_placement"),
                    )
                elif action_type == "launch_program":
                    command = [params["executable"]]
                    if params.get("arguments"):
                        command.append(params["arguments"])
                    process = subprocess.Popen(command, cwd=params.get("working_directory") or None)
                    target_monitor = params.get("target_monitor", "default")
                    auto_focus = bool(params.get("auto_focus", False))
                    wait_for_startup = bool(params.get("wait_for_startup", False))
                    window_placement = params.get("window_placement")
                    if wait_for_startup or auto_focus or target_monitor != "default" or window_placement:
                        arrange_process_window(
                            process.pid,
                            target_monitor=target_monitor,
                            auto_focus=auto_focus,
                            timeout=float(params.get("startup_timeout", 10.0)),
                            window_placement=window_placement,
                        )
                elif action_type == "type_text":
                    keyboard_controller.type(params.get("text", ""))
                elif action_type == "type_secret":
                    env_name = params["environment_variable"]
                    secret = os.environ.get(env_name)
                    if secret is None and sys.stdin.isatty():
                        secret = getpass(f"{env_name}: ")
                    if secret is None:
                        raise RuntimeError(f"Missing environment variable {env_name}")
                    keyboard_controller.type(secret)
                elif action_type == "key_press":
                    key = key_from_name(params.get("key", ""), keyboard)
                    phase = params.get("phase", "press_release")
                    if phase == "press":
                        keyboard_controller.press(key)
                        held_keys.append(key)
                    elif phase == "release":
                        keyboard_controller.release(key)
                        held_keys = [held for held in held_keys if held != key]
                    else:
                        keyboard_controller.press(key)
                        keyboard_controller.release(key)
                elif action_type == "hotkey":
                    keys = [key_from_name(key, keyboard) for key in params.get("keys", [])]
                    for key in keys:
                        keyboard_controller.press(key)
                        held_keys.append(key)
                    for key in reversed(keys):
                        keyboard_controller.release(key)
                        held_keys.pop()
                elif action_type == "mouse_move":
                    start_time = time.perf_counter()
                    for x, y, relative_time in interpolated_mouse_points(mouse_move_points(runtime_action)):
                        if not sleep_until(start_time + (relative_time / speed), stop_event):
                            print("Emergency stop requested", file=sys.stderr)
                            return 130
                        position_mouse(mouse_controller, x, y)
                elif action_type == "mouse_button":
                    position_mouse(mouse_controller, params.get("x", 0), params.get("y", 0))
                    button = button_from_name(params.get("button", "left"), mouse)
                    phase = params.get("phase", "click")
                    if phase == "press":
                        mouse_controller.press(button)
                        held_buttons.append(button)
                    elif phase == "release":
                        mouse_controller.release(button)
                        held_buttons = [held for held in held_buttons if held != button]
                    else:
                        mouse_controller.press(button)
                        mouse_controller.release(button)
                elif action_type == "scroll":
                    position_mouse(mouse_controller, params.get("x", 0), params.get("y", 0))
                    mouse_controller.scroll(int(params.get("dx", 0)), int(params.get("dy", 0)))
                elif action_type == "image_click":
                    image_found = execute_image_click(params, mouse_controller, mouse, stop_event, held_buttons, speed)
                    if image_found is None:
                        print("Emergency stop requested", file=sys.stderr)
                        return 130
                    runtime_state["last_image_found"] = bool(image_found)
                elif action_type == "if_condition":
                    jump_index = conditional_jump_target(params, runtime_state, len(actions))
                    if jump_index is not None:
                        print(f"If Image Result jumped to action {jump_index + 1}")
                        next_index = jump_index
                        break
            index = next_index
        return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Playback failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        if hotkey_listener is not None:
            try:
                hotkey_listener.stop()
            except Exception:
                pass
        release_all()
        if log_handle is not None:
            log_handle.flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
'''
        return (
            dedent(template)
            .replace("__RUNTIME_RELATIVE_PATH__", repr(str(runtime_relative_path)))
            .replace("__DEPENDENCIES_DIR_NAME__", DEPENDENCIES_DIR_NAME)
            .replace("__REQUIRED_PACKAGES__", repr(list(RUNTIME_REQUIREMENTS)))
            .replace("__MACRO_JSON__", repr(payload))
        )

    def export(self, document: MacroDocument, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != ".py":
            target = target.with_suffix(".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        return self._write_export(document, target, support_dir=export_support_directory(target))

    def _write_export(self, document: MacroDocument, target: Path, *, support_dir: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        export_document = self._document_with_export_assets(document, target, support_dir=support_dir)
        runtime_dir = support_dir / RUNTIME_DIR_NAME
        runtime_relative_path = Path(os.path.relpath(runtime_dir, target.parent))
        target.write_text(
            self.render(export_document, runtime_relative_path=runtime_relative_path),
            encoding="utf-8",
        )
        self.write_support_files(target, support_dir=support_dir)
        return target

    def _document_with_export_assets(
        self,
        document: MacroDocument,
        target: Path,
        *,
        support_dir: Path | None = None,
    ) -> MacroDocument:
        export_document = MacroDocument.from_dict(document.to_dict())
        asset_dir = (support_dir or target.parent) / ASSETS_DIR_NAME
        for action in [*export_document.pre_actions, *export_document.actions]:
            if action.type != ActionType.IMAGE_CLICK:
                continue
            image_path = str(action.params.get("image_path", ""))
            if not image_path:
                continue
            source = Path(image_path).expanduser()
            if not source.is_absolute():
                source = Path.cwd() / source
            if not source.exists() or not source.is_file():
                continue
            asset_dir.mkdir(parents=True, exist_ok=True)
            destination = self._unique_asset_path(asset_dir, source, action.id)
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            action.params["image_path"] = os.path.relpath(destination, target.parent)
        return export_document

    def _unique_asset_path(self, asset_dir: Path, source: Path, action_id: str) -> Path:
        stem = INVALID_FILENAME_CHARS.sub("_", source.stem).strip(" ._") or "image"
        suffix = source.suffix or ".png"
        candidate = asset_dir / f"{action_id[:8]}_{stem}{suffix}"
        counter = 2
        while candidate.exists() and candidate.resolve() != source.resolve():
            candidate = asset_dir / f"{action_id[:8]}_{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    def write_support_files(self, target: str | Path, *, support_dir: str | Path | None = None) -> None:
        target = Path(target)
        support_dir = Path(support_dir) if support_dir is not None else target.parent
        runtime_dir = support_dir / RUNTIME_DIR_NAME
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "requirements.txt").write_text("\n".join(RUNTIME_REQUIREMENTS) + "\n", encoding="utf-8")
        (runtime_dir / "install_dependencies.bat").write_text(self._install_batch(), encoding="utf-8")
        if support_dir == target.parent:
            (target.parent / safe_batch_filename(target)).write_text(self._run_batch(target), encoding="utf-8")
        readme = support_dir / "README_exported_macros.txt"
        readme.write_text(self._readme_text(single_file=support_dir != target.parent), encoding="utf-8")

    def _install_batch(self) -> str:
        python_exe = str(Path(self.python_executable))
        return (
            "@echo off\n"
            "setlocal\n"
            'cd /d "%~dp0"\n'
            f'set "PYTHON_EXE={python_exe}"\n'
            'if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"\n'
            'if not exist "dependencies" mkdir "dependencies"\n'
            '"%PYTHON_EXE%" -m pip install --upgrade --target "%~dp0dependencies" -r "%~dp0requirements.txt"\n'
            "if errorlevel 1 (\n"
            "    echo Failed to install Macro Recorder + export dependencies.\n"
            "    pause\n"
            "    exit /b 1\n"
            ")\n"
            'echo Dependencies installed in "%~dp0dependencies".\n'
        )

    def _run_batch(self, target: Path) -> str:
        python_exe = str(Path(self.python_executable))
        dependency_checks = "\n".join(f'if not exist "%DEPS_DIR%\\{name}" set "NEED_INSTALL=1"' for name in RUNTIME_IMPORT_DIRS)
        return (
            "@echo off\n"
            "setlocal\n"
            'cd /d "%~dp0"\n'
            f'set "PYTHON_EXE={python_exe}"\n'
            'if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"\n'
            f'set "RUNTIME_DIR=%~dp0{RUNTIME_DIR_NAME}"\n'
            f'set "DEPS_DIR=%RUNTIME_DIR%\\{DEPENDENCIES_DIR_NAME}"\n'
            'set "NEED_INSTALL=0"\n'
            f"{dependency_checks}\n"
            'if "%NEED_INSTALL%"=="1" (\n'
            '    call "%RUNTIME_DIR%\\install_dependencies.bat"\n'
            "    if errorlevel 1 exit /b 1\n"
            ")\n"
            f'"%PYTHON_EXE%" "%~dp0{target.name}" %*\n'
        )

    def _readme_text(self, *, single_file: bool = False) -> str:
        if single_file:
            return dedent(
                '''\
                Macro Recorder + exported Python macros

                Double-click the exported .py file on the Desktop. Required packages are installed
                automatically into misc/macro_recorder_plus_runtime on first run.
                Image recognition templates are stored under misc/macro_recorder_plus_assets.

                Useful direct commands:
                  python your_macro.py --dry-run
                  python your_macro.py --speed 1.5
                  python your_macro.py --start-action 12

                Secret actions read from environment variables in this process.
                Press F10 while a macro is running to request an emergency stop.
                '''
            )
        return dedent(
            '''\
            Macro Recorder + exported Python macros

            Run a macro with its generated run_*.bat file. The batch file installs runtime
            dependencies into macro_recorder_plus_runtime\\dependencies on first run, then starts
            the exported script. Image recognition templates are stored in macro_recorder_plus_assets.

            Useful direct commands:
              python your_macro.py --install-deps
              python your_macro.py --dry-run
              python your_macro.py --speed 1.5
              python your_macro.py --start-action 12

            Secret actions read from environment variables in this process. For example:
              set WEBSITE_PASSWORD=secret
              python your_macro.py

            Press F10 while a macro is running to request an emergency stop.
            '''
        )
