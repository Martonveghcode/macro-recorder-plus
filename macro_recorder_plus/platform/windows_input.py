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
from macro_recorder_plus.utilities.validation import validate_url


def keyboard_key_to_name(key: Any) -> str:
    char = getattr(key, "char", None)
    if char:
        return char
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
            case ActionType.OPEN_FILE:
                open_file_with_default_app(
                    str(action.params.get("file_path", "")),
                    target_monitor=str(action.params.get("target_monitor", "default")),
                    auto_focus=bool(action.params.get("auto_focus", False)),
                )
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
                if wait_for_startup or auto_focus or target_monitor != "default":
                    arrange_process_window(
                        process.pid,
                        target_monitor=target_monitor,
                        auto_focus=auto_focus,
                        timeout=float(action.params.get("startup_timeout", 10.0)),
                    )
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
                self.mouse.position = (int(end[0]), int(end[1]))
            case ActionType.MOUSE_BUTTON:
                x = action.params.get("x")
                y = action.params.get("y")
                if x is not None and y is not None:
                    self.mouse.position = (int(x), int(y))
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
                    self.mouse.position = (int(x), int(y))
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
        self.mouse.position = match.center
        click_action = str(action.params.get("click_action", "left_click"))
        if click_action == "move_only":
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
) -> None:
    path = resolve_file_path(file_path, base_dir=base_dir)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if sys.platform == "win32":
        if auto_focus or target_monitor != "default":
            pid = _shell_execute_file_with_process_id(path)
            if pid is not None:
                arrange_process_window(pid, target_monitor=target_monitor, auto_focus=auto_focus, timeout=timeout)
                return
        os.startfile(str(path))  # type: ignore[attr-defined]
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
) -> bool:
    if sys.platform != "win32" or not process_id:
        return False
    hwnd = _find_top_level_window_for_process(int(process_id), timeout=max(0.0, timeout))
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    monitor = _select_target_monitor(target_monitor)
    if monitor is not None:
        _move_window_to_monitor(hwnd, monitor)
    if auto_focus:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    return True


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
        stop_check=stop_check,
    )


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


def _find_top_level_window_for_process(process_id: int, *, timeout: float) -> int | None:
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    deadline = time.perf_counter() + timeout
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def find_once() -> int | None:
        found: list[int] = []

        def callback(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # GW_OWNER
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
