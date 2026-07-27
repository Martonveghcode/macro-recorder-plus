from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
import webbrowser
from getpass import getpass
from pathlib import Path
from typing import Any, Callable

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.environment import MonitorInfo
from macro_recorder_plus.platform.windows_monitors import get_monitor_layout
from macro_recorder_plus.utilities.image_recognition import ImageMatch, find_image_on_screen
from macro_recorder_plus.utilities.key_sequences import normalize_key_name
from macro_recorder_plus.utilities.mouse_path import interpolated_path_points
from macro_recorder_plus.utilities.validation import validate_url


MOUSE_POSITION_ATTEMPTS = 3
MOUSE_POSITION_TOLERANCE = 1


def position_mouse(
    mouse_controller: Any,
    x: int,
    y: int,
    *,
    attempts: int = MOUSE_POSITION_ATTEMPTS,
    tolerance: int = MOUSE_POSITION_TOLERANCE,
) -> tuple[int, int]:
    """Place the cursor at an absolute coordinate and confirm that it settled there."""
    target = (int(x), int(y))
    last_position: tuple[int, int] | None = None
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


def keyboard_key_to_name(key: Any) -> str:
    char = getattr(key, "char", None)
    if char:
        if str(char).isprintable():
            return normalize_key_name(str(char))
        char_code = ord(str(char)[0])
        if 1 <= char_code <= 26:
            return chr(ord("a") + char_code - 1)
    virtual_key = getattr(key, "vk", None)
    if virtual_key is None:
        virtual_key = getattr(getattr(key, "value", None), "vk", None)
    if virtual_key is not None:
        virtual_key = int(virtual_key)
        if 0x30 <= virtual_key <= 0x39 or 0x41 <= virtual_key <= 0x5A:
            return chr(virtual_key).lower()
        virtual_key_names = {
            0x20: "space",
            0xBA: ";",
            0xBB: "=",
            0xBC: ",",
            0xBD: "-",
            0xBE: ".",
            0xBF: "/",
            0xC0: "`",
            0xDB: "[",
            0xDC: "\\",
            0xDD: "]",
            0xDE: "'",
        }
        if virtual_key in virtual_key_names:
            return virtual_key_names[virtual_key]
    value = str(key)
    return normalize_key_name(value)


def mouse_button_to_name(button: Any) -> str:
    value = str(button)
    if value.startswith("Button."):
        value = value.split(".", 1)[1]
    return value.lower()


def name_to_keyboard_key(name: str) -> Any:
    from pynput import keyboard

    key = normalize_key_name(name)
    key_lookup = {
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
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
    }
    if key in key_lookup:
        return key_lookup[key]
    if len(key) == 1:
        return keyboard.KeyCode.from_char(key)
    if key.startswith("f") and key[1:].isdigit():
        return getattr(keyboard.Key, key)
    return keyboard.KeyCode.from_char(key)


def name_to_mouse_button(name: str) -> Any:
    from pynput import mouse

    key = str(name).lower().replace("button.", "")
    return getattr(mouse.Button, key)


class HeldInputTracker:
    def __init__(self, keyboard_controller: Any | None = None, mouse_controller: Any | None = None) -> None:
        self.keyboard = keyboard_controller
        self.mouse = mouse_controller
        self.held_keys: list[Any] = []
        self.held_buttons: list[Any] = []

    def press_key(self, key: Any) -> None:
        if self.keyboard is not None:
            self.keyboard.press(key)
        self.held_keys.append(key)

    def release_key(self, key: Any) -> None:
        if self.keyboard is not None:
            self.keyboard.release(key)
        self.held_keys = [held for held in self.held_keys if held != key]

    def press_button(self, button: Any) -> None:
        if self.mouse is not None:
            self.mouse.press(button)
        self.held_buttons.append(button)

    def release_button(self, button: Any) -> None:
        if self.mouse is not None:
            self.mouse.release(button)
        self.held_buttons = [held for held in self.held_buttons if held != button]

    def release_all(self) -> None:
        for key in list(reversed(self.held_keys)):
            try:
                if self.keyboard is not None:
                    self.keyboard.release(key)
            finally:
                pass
        for button in list(reversed(self.held_buttons)):
            try:
                if self.mouse is not None:
                    self.mouse.release(button)
            finally:
                pass
        self.held_keys.clear()
        self.held_buttons.clear()


class ActionExecutor:
    def __init__(self, keyboard_controller: Any, mouse_controller: Any) -> None:
        self.keyboard = keyboard_controller
        self.mouse = mouse_controller
        self.held = HeldInputTracker(keyboard_controller, mouse_controller)

    def execute(self, action: MacroAction, *, dry_run: bool = False) -> None:
        if dry_run or not action.enabled:
            return

        match action.type:
            case ActionType.WAIT | ActionType.IF_CONDITION | ActionType.COMMENT:
                return
            case ActionType.OPEN_URL:
                url = str(action.params.get("url", ""))
                if not validate_url(url):
                    raise ValueError(f"Invalid URL: {url}")
                webbrowser.open(url)
                window_placement = action.params.get("window_placement")
                if window_placement:
                    _arrange_existing_window(
                        window_placement,
                        auto_focus=bool(action.params.get("auto_focus", False)),
                        timeout=10.0,
                    )
            case ActionType.OPEN_FILE:
                open_options: dict[str, Any] = {
                    "target_monitor": str(action.params.get("target_monitor", "default")),
                    "auto_focus": bool(action.params.get("auto_focus", False)),
                }
                if action.params.get("window_placement"):
                    open_options["window_placement"] = action.params["window_placement"]
                open_file_with_default_app(str(action.params.get("file_path", "")), **open_options)
            case ActionType.LAUNCH_PROGRAM:
                executable = str(action.params.get("executable", ""))
                if not executable:
                    raise ValueError("Launch Program action is missing executable")
                args = str(action.params.get("arguments", ""))
                cwd = str(action.params.get("working_directory") or os.getcwd())
                command = [executable] + ([args] if args else [])
                process = subprocess.Popen(command, cwd=cwd)
                target_monitor = str(action.params.get("target_monitor", "default"))
                auto_focus = bool(action.params.get("auto_focus", False))
                wait_for_startup = bool(action.params.get("wait_for_startup", False))
                window_placement = action.params.get("window_placement")
                if wait_for_startup or auto_focus or target_monitor != "default" or window_placement:
                    arrange_options: dict[str, Any] = {
                        "target_monitor": target_monitor,
                        "auto_focus": auto_focus,
                        "timeout": float(action.params.get("startup_timeout", 10.0)),
                    }
                    if window_placement:
                        arrange_options["window_placement"] = window_placement
                    arrange_process_window(process.pid, **arrange_options)
            case ActionType.TYPE_TEXT:
                self.keyboard.type(str(action.params.get("text", "")))
            case ActionType.TYPE_SECRET:
                env_name = str(action.params.get("environment_variable", ""))
                secret = os.environ.get(env_name)
                if secret is None and sys.stdin.isatty():
                    secret = getpass(f"{env_name}: ")
                if secret is None:
                    raise ValueError(f"Missing required environment variable: {env_name}")
                self.keyboard.type(secret)
            case ActionType.KEY_PRESS:
                key = name_to_keyboard_key(str(action.params.get("key", "")))
                phase = str(action.params.get("phase", "press_release"))
                if phase in {"press", "down"}:
                    self.held.press_key(key)
                elif phase in {"release", "up"}:
                    self.held.release_key(key)
                else:
                    self.keyboard.press(key)
                    self.keyboard.release(key)
            case ActionType.HOTKEY:
                keys = [name_to_keyboard_key(key) for key in action.params.get("keys", [])]
                for key in keys:
                    self.held.press_key(key)
                for key in reversed(keys):
                    self.held.release_key(key)
            case ActionType.MOUSE_MOVE:
                end = action.params.get("end") or [0, 0]
                position_mouse(self.mouse, int(end[0]), int(end[1]))
            case ActionType.MOUSE_BUTTON:
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    position_mouse(self.mouse, int(x), int(y))
                button = name_to_mouse_button(str(action.params.get("button", "left")))
                phase = str(action.params.get("phase", "click"))
                if phase == "press":
                    self.held.press_button(button)
                elif phase == "release":
                    self.held.release_button(button)
                else:
                    self.mouse.press(button)
                    self.mouse.release(button)
            case ActionType.SCROLL:
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    position_mouse(self.mouse, int(x), int(y))
                self.mouse.scroll(int(action.params.get("dx", 0)), int(action.params.get("dy", 0)))
            case ActionType.IMAGE_CLICK:
                self._execute_image_click(action)

    def release_all(self) -> None:
        self.held.release_all()

    def _execute_image_click(self, action: MacroAction) -> None:
        match = find_image_match_for_action(action)
        if match is None:
            if str(action.params.get("on_not_found", "error")) == "skip":
                return
            raise ValueError(f"Image not found on screen: {action.params.get('image_path', '')}")
        self.click_image_match(action, match)

    def click_image_match(self, action: MacroAction, match: ImageMatch) -> None:
        position_mouse(self.mouse, int(match.center[0]), int(match.center[1]))
        click_action = str(action.params.get("click_action", "left_click"))
        if click_action == "move_only":
            return
        if click_action == "custom_movement":
            self.perform_image_movement(action, match)
            return
        if click_action == "double_click":
            button = name_to_mouse_button("left")
            for _ in range(2):
                self.mouse.press(button)
                self.mouse.release(button)
                time.sleep(0.05)
            return

        button_name = click_action.replace("_click", "")
        button = name_to_mouse_button(button_name)
        self.mouse.press(button)
        self.mouse.release(button)

    def perform_image_movement(self, action: MacroAction, match: ImageMatch) -> None:
        points = image_movement_points_for_match(action, match)
        if not points:
            return
        interpolated_points = interpolated_path_points(points, hz=60)
        if not interpolated_points:
            return
        first_x, first_y, _ = interpolated_points[0]
        position_mouse(self.mouse, int(first_x), int(first_y))
        self.apply_image_movement_button(action, "start")
        start_time = time.perf_counter()
        for x, y, relative_time in interpolated_points[1:]:
            target = start_time + max(0.0, float(relative_time))
            remaining = target - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            position_mouse(self.mouse, int(x), int(y))
        self.apply_image_movement_button(action, "end")

    def apply_image_movement_button(self, action: MacroAction, stage: str) -> None:
        button_action = str(action.params.get("movement_button_action", "none"))
        if button_action == "none":
            return
        button = name_to_mouse_button(str(action.params.get("movement_button", "left")))
        if stage == "start":
            if button_action == "click_at_start":
                self._click_mouse_button(button)
            elif button_action == "double_click_at_start":
                self._double_click_mouse_button(button)
            elif button_action in {"hold_during_move", "press_at_start"}:
                self.held.press_button(button)
        elif stage == "end":
            if button_action == "click_at_end":
                self._click_mouse_button(button)
            elif button_action == "double_click_at_end":
                self._double_click_mouse_button(button)
            elif button_action in {"hold_during_move", "release_at_end"}:
                self.held.release_button(button)

    def _click_mouse_button(self, button: Any) -> None:
        self.mouse.press(button)
        self.mouse.release(button)

    def _double_click_mouse_button(self, button: Any) -> None:
        for _ in range(2):
            self._click_mouse_button(button)
            time.sleep(0.05)


def resolve_file_path(file_path: str, *, base_dir: Path | None = None) -> Path:
    value = os.path.expandvars(str(file_path)).strip().strip('"')
    if not value:
        raise ValueError("Open File action is missing a file path")
    path = Path(value).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = base_dir / path
    return path


def open_file_with_default_app(
    file_path: str,
    *,
    base_dir: Path | None = None,
    target_monitor: str = "default",
    auto_focus: bool = False,
    timeout: float = 10.0,
    window_placement: dict[str, Any] | None = None,
) -> None:
    path = resolve_file_path(file_path, base_dir=base_dir)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if sys.platform == "win32":
        if auto_focus or target_monitor != "default" or window_placement:
            pid = _shell_execute_file_with_process_id(path)
            if pid is not None:
                arrange_process_window(
                    pid,
                    target_monitor=target_monitor,
                    auto_focus=auto_focus,
                    timeout=timeout,
                    window_placement=window_placement,
                )
                return
        os.startfile(str(path))  # type: ignore[attr-defined]
        if window_placement:
            _arrange_existing_window(window_placement, auto_focus=auto_focus, timeout=timeout)
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def arrange_process_window(
    process_id: int | None,
    *,
    target_monitor: str = "default",
    auto_focus: bool = False,
    timeout: float = 10.0,
    window_placement: dict[str, Any] | None = None,
) -> bool:
    if sys.platform != "win32" or not process_id:
        return False
    title_hint = str((window_placement or {}).get("window_title", ""))
    hwnd = _find_top_level_window_for_process(int(process_id), timeout=max(0.0, timeout), title_hint=title_hint)
    if not hwnd and window_placement:
        hwnd = _find_top_level_window_for_executable(
            str(window_placement.get("process_path", "")),
            timeout=0.0,
            title_hint=title_hint,
        )
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    if window_placement:
        _restore_window_placement(hwnd, window_placement)
    else:
        monitor = _select_target_monitor(target_monitor)
        if monitor is not None:
            _move_window_to_monitor(hwnd, monitor)
    if auto_focus:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    return True


def _arrange_existing_window(placement: dict[str, Any], *, auto_focus: bool, timeout: float) -> bool:
    hwnd = _find_top_level_window_for_executable(
        str(placement.get("process_path", "")),
        timeout=max(0.0, timeout),
        title_hint=str(placement.get("window_title", "")),
    )
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    _restore_window_placement(hwnd, placement)
    if auto_focus:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    return True


def list_open_windows() -> list[dict[str, Any]]:
    """Return capturable top-level Windows windows with their current placement."""
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    windows: list[dict[str, Any]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value.strip()
        placement = capture_window_placement(int(hwnd))
        if not title or placement is None:
            return True
        window_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        process_path = _process_executable_path(int(window_pid.value))
        windows.append(
            {
                "handle": int(hwnd),
                "title": title,
                "process_id": int(window_pid.value),
                "process_path": process_path,
                "placement": placement,
            }
        )
        return True

    user32.EnumWindows(enum_proc_type(callback), 0)
    return windows


def capture_window_placement(hwnd: int) -> dict[str, Any] | None:
    if sys.platform != "win32" or not hwnd:
        return None

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = max(1, int(rect.right - rect.left))
    height = max(1, int(rect.bottom - rect.top))
    monitors = get_monitor_layout().monitors
    monitor_index = _monitor_index_for_rect(int(rect.left), int(rect.top), width, height, monitors)
    monitor = monitors[monitor_index] if 0 <= monitor_index < len(monitors) else None
    work = monitor.work_area if monitor is not None else None
    return {
        "x": int(rect.left),
        "y": int(rect.top),
        "width": width,
        "height": height,
        "maximized": bool(user32.IsZoomed(hwnd)),
        "monitor_index": monitor_index,
        "monitor_identifier": monitor.identifier if monitor is not None else "",
        "offset_x": int(rect.left - work.left) if work is not None else 0,
        "offset_y": int(rect.top - work.top) if work is not None else 0,
    }


def find_image_match_for_action(action: MacroAction, *, stop_check: Callable[[], bool] | None = None) -> ImageMatch | None:
    image_path = str(action.params.get("image_path", ""))
    if not image_path:
        raise ValueError("Image action is missing an image path")
    timeout = float(action.params.get("timeout", 5.0))
    wait_until_found = bool(action.params.get("wait_until_found", True))
    if "wait_until_found" not in action.params and timeout <= 0:
        wait_until_found = False
    checks_per_second = action.params.get("checks_per_second")
    if checks_per_second is not None:
        checks_per_second = float(checks_per_second)
    return find_image_on_screen(
        image_path,
        confidence=float(action.params.get("confidence", 0.85)),
        timeout=timeout,
        poll_interval=float(action.params.get("poll_interval", 0.25)),
        checks_per_second=checks_per_second,
        wait_until_found=wait_until_found,
        grayscale=bool(action.params.get("grayscale", True)),
        region=_region_from_params(action.params),
        verification_attempts=int(action.params.get("verification_attempts", 2) or 1),
        stable_match_pixels=int(action.params.get("stable_match_pixels", 8) or 0),
        scale_tolerance=float(action.params.get("scale_tolerance", 0.05) or 0.0),
        stop_check=stop_check,
    )


def image_movement_points_for_match(action: MacroAction, match: object) -> list[tuple[int, int, float]]:
    center_x, center_y = _match_center(match)
    raw_path = action.params.get("movement_path") or []
    points: list[tuple[int, int, float]] = []
    for point in raw_path:
        if len(point) >= 3:
            points.append((center_x + int(point[0]), center_y + int(point[1]), max(0.0, float(point[2]))))
    if points:
        return points

    start_offset = _offset_pair(action.params.get("movement_start_offset", [0, 0]))
    end_offset = _offset_pair(action.params.get("movement_end_offset", [0, 0]))
    duration = max(0.0, float(action.params.get("movement_duration", 0.0)))
    return [
        (center_x + start_offset[0], center_y + start_offset[1], 0.0),
        (center_x + end_offset[0], center_y + end_offset[1], duration),
    ]


def _match_center(match: object) -> tuple[int, int]:
    center = getattr(match, "center", None)
    if center is None and isinstance(match, dict):
        center = match.get("center")
    if center is None:
        raise ValueError("Image match is missing center coordinates")
    return (int(center[0]), int(center[1]))


def _offset_pair(value: Any) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return (0, 0)
    return (int(value[0]), int(value[1]))


def _shell_execute_file_with_process_id(path: Path) -> int | None:
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
    info.fMask = 0x00000040  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "open"
    info.lpFile = str(path)
    info.nShow = 1  # SW_SHOWNORMAL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return None
    if not info.hProcess:
        return None
    try:
        return int(kernel32.GetProcessId(info.hProcess))
    finally:
        kernel32.CloseHandle(info.hProcess)


def _find_top_level_window_for_process(process_id: int, *, timeout: float, title_hint: str = "") -> int | None:
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    deadline = time.perf_counter() + timeout
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def find_once() -> int | None:
        found: list[tuple[int, str]] = []

        def callback(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
                return True
            window_pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            if int(window_pid.value) == process_id:
                length = int(user32.GetWindowTextLengthW(hwnd))
                title_buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, title_buffer, length + 1)
                found.append((int(hwnd), title_buffer.value))
            return True

        user32.EnumWindows(enum_proc_type(callback), 0)
        if not found:
            return None
        hint = title_hint.casefold().strip()
        if hint:
            exact = next((hwnd for hwnd, title in found if title.casefold() == hint), None)
            if exact is not None:
                return exact
            hinted = next((hwnd for hwnd, title in found if hint in title.casefold() or title.casefold() in hint), None)
            if hinted is not None:
                return hinted
        return found[0][0]

    while True:
        hwnd = find_once()
        if hwnd is not None:
            return hwnd
        if time.perf_counter() >= deadline:
            return None
        time.sleep(0.05)


def _process_executable_path(process_id: int) -> str:
    if sys.platform != "win32" or not process_id:
        return ""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, process_id)  # PROCESS_QUERY_LIMITED_INFORMATION
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


def _find_top_level_window_for_executable(executable: str, *, timeout: float, title_hint: str = "") -> int | None:
    expected = str(executable).casefold().strip()
    if sys.platform != "win32" or not expected:
        return None
    deadline = time.perf_counter() + timeout
    while True:
        candidates = [window for window in list_open_windows() if str(window.get("process_path", "")).casefold() == expected]
        if candidates:
            hint = title_hint.casefold().strip()
            if hint:
                exact = next((window for window in candidates if str(window.get("title", "")).casefold() == hint), None)
                if exact is not None:
                    return int(exact["handle"])
                hinted = next(
                    (
                        window
                        for window in candidates
                        if hint in str(window.get("title", "")).casefold()
                        or str(window.get("title", "")).casefold() in hint
                    ),
                    None,
                )
                if hinted is not None:
                    return int(hinted["handle"])
            return int(candidates[0]["handle"])
        if time.perf_counter() >= deadline:
            return None
        time.sleep(0.05)


def _monitor_index_for_rect(x: int, y: int, width: int, height: int, monitors: list[MonitorInfo]) -> int:
    best_index = -1
    best_overlap = -1
    right = x + width
    bottom = y + height
    for index, monitor in enumerate(monitors):
        bounds = monitor.bounds
        overlap_width = max(0, min(right, bounds.right) - max(x, bounds.left))
        overlap_height = max(0, min(bottom, bounds.bottom) - max(y, bounds.top))
        overlap = overlap_width * overlap_height
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = index
    return best_index


def _restore_window_placement(hwnd: int, placement: dict[str, Any]) -> None:
    user32 = ctypes.windll.user32
    monitors = get_monitor_layout().monitors
    monitor: MonitorInfo | None = None
    identifier = str(placement.get("monitor_identifier", ""))
    if identifier:
        monitor = next((candidate for candidate in monitors if candidate.identifier == identifier), None)
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
        work = monitor.work_area
        width = min(width, max(1, work.width))
        height = min(height, max(1, work.height))
        x = work.left + int(placement.get("offset_x", 0) or 0)
        y = work.top + int(placement.get("offset_y", 0) or 0)
        x = min(max(x, work.left), work.right - width)
        y = min(max(y, work.top), work.bottom - height)
    else:
        x = int(placement.get("x", 0) or 0)
        y = int(placement.get("y", 0) or 0)
    user32.SetWindowPos(hwnd, 0, x, y, width, height, 0x0004)  # SWP_NOZORDER
    if bool(placement.get("maximized", False)):
        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE


def _select_target_monitor(target_monitor: str) -> MonitorInfo | None:
    value = str(target_monitor or "default").lower()
    if value == "default":
        return None
    monitors = get_monitor_layout().monitors
    if not monitors:
        return None
    if value == "primary":
        return next((monitor for monitor in monitors if monitor.primary), monitors[0])
    if value.isdigit():
        index = int(value) - 1
        if 0 <= index < len(monitors):
            return monitors[index]
    return None


def _move_window_to_monitor(hwnd: int, monitor: MonitorInfo) -> None:
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    user32 = ctypes.windll.user32
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return
    width = max(1, int(rect.right - rect.left))
    height = max(1, int(rect.bottom - rect.top))
    work = monitor.work_area
    target_width = min(width, max(1, work.width))
    target_height = min(height, max(1, work.height))
    x = work.left + max(0, (work.width - target_width) // 2)
    y = work.top + max(0, (work.height - target_height) // 2)
    user32.SetWindowPos(hwnd, 0, x, y, target_width, target_height, 0x0004)  # SWP_NOZORDER


def _region_from_params(params: dict[str, Any]) -> tuple[int, int, int, int] | None:
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
