from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

from macro_recorder_plus.models.macro import MacroDocument


RUNTIME_DIR_NAME = "macro_recorder_plus_runtime"
DEPENDENCIES_DIR_NAME = "dependencies"
RUNTIME_REQUIREMENTS = ("pynput>=1.7.7",)
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


class PythonExporter:
    def render(self, document: MacroDocument) -> str:
        payload = json.dumps(document.to_dict(), separators=(",", ":"), sort_keys=True)
        template = '''\
#!/usr/bin/env python3
"""Standalone macro exported by Macro Recorder +."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
import webbrowser
from getpass import getpass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR / "__RUNTIME_DIR_NAME__"
LOCAL_DEPS = RUNTIME_DIR / "__DEPENDENCIES_DIR_NAME__"
if LOCAL_DEPS.exists():
    sys.path.insert(0, str(LOCAL_DEPS))

REQUIRED_PACKAGES = __REQUIRED_PACKAGES__
MACRO = json.loads(__MACRO_JSON__)


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


def import_input_modules():
    try:
        from pynput import keyboard, mouse
        return keyboard, mouse
    except Exception as exc:
        print(f"pynput is required: {exc}", file=sys.stderr)
        print("Run the generated run_*.bat file, or run this script with --install-deps first.", file=sys.stderr)
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
        "tab": keyboard.Key.tab,
        "space": keyboard.Key.space,
        "left": keyboard.Key.left,
        "right": keyboard.Key.right,
        "up": keyboard.Key.up,
        "down": keyboard.Key.down,
    }
    key = str(name).lower().replace("key.", "")
    return lookup.get(key) or keyboard.KeyCode.from_char(key)


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


def main():
    parser = argparse.ArgumentParser(description="Run an exported Macro Recorder + macro.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--start-action", type=int, default=0)
    parser.add_argument("--install-deps", action="store_true", help="Install runtime dependencies into the local export folder.")
    parser.add_argument("--no-hotkey", action="store_true", help="Disable the F10 emergency-stop listener.")
    args = parser.parse_args()

    if args.install_deps:
        return install_dependencies()

    set_dpi_awareness()
    speed = max(0.01, args.speed)
    stop_event = threading.Event()
    hotkey_listener = None
    held_keys = []
    held_buttons = []
    keyboard_controller = None
    mouse_controller = None
    keyboard = None
    mouse = None

    if not args.dry_run:
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

    try:
        for index, action in enumerate(MACRO["actions"][args.start_action:], start=args.start_action):
            if stop_event.is_set():
                print("Emergency stop requested", file=sys.stderr)
                return 130
            if not action.get("enabled", True):
                continue
            delay = max(0.0, float(action.get("delay", 0.0))) / speed
            if delay and not args.dry_run:
                if not sleep_until(time.perf_counter() + delay, stop_event):
                    print("Emergency stop requested", file=sys.stderr)
                    return 130
            print(f"{index}: {action['type']} {action.get('label') or action.get('params', '')}")
            if args.dry_run:
                continue

            params = action.get("params", {})
            action_type = action["type"]
            if action_type == "wait":
                seconds = float(params.get("seconds", action.get("duration", 0))) / speed
                if not sleep_until(time.perf_counter() + seconds, stop_event):
                    print("Emergency stop requested", file=sys.stderr)
                    return 130
            elif action_type == "open_url":
                webbrowser.open(params["url"])
            elif action_type == "launch_program":
                command = [params["executable"]]
                if params.get("arguments"):
                    command.append(params["arguments"])
                subprocess.Popen(command, cwd=params.get("working_directory") or None)
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
                for x, y, relative_time in interpolated_mouse_points(mouse_move_points(action)):
                    if not sleep_until(start_time + (relative_time / speed), stop_event):
                        print("Emergency stop requested", file=sys.stderr)
                        return 130
                    mouse_controller.position = (int(x), int(y))
            elif action_type == "mouse_button":
                mouse_controller.position = (int(params.get("x", 0)), int(params.get("y", 0)))
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
                mouse_controller.position = (int(params.get("x", 0)), int(params.get("y", 0)))
                mouse_controller.scroll(int(params.get("dx", 0)), int(params.get("dy", 0)))
        return 0
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Playback failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if hotkey_listener is not None:
            try:
                hotkey_listener.stop()
            except Exception:
                pass
        release_all()


if __name__ == "__main__":
    raise SystemExit(main())
'''
        return (
            dedent(template)
            .replace("__RUNTIME_DIR_NAME__", RUNTIME_DIR_NAME)
            .replace("__DEPENDENCIES_DIR_NAME__", DEPENDENCIES_DIR_NAME)
            .replace("__REQUIRED_PACKAGES__", repr(list(RUNTIME_REQUIREMENTS)))
            .replace("__MACRO_JSON__", repr(payload))
        )

    def export(self, document: MacroDocument, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != ".py":
            target = target.with_suffix(".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(document), encoding="utf-8")
        self.write_support_files(target)
        return target

    def write_support_files(self, target: str | Path) -> None:
        target = Path(target)
        runtime_dir = target.parent / RUNTIME_DIR_NAME
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "requirements.txt").write_text("\n".join(RUNTIME_REQUIREMENTS) + "\n", encoding="utf-8")
        (runtime_dir / "install_dependencies.bat").write_text(self._install_batch(), encoding="utf-8")
        (target.parent / safe_batch_filename(target)).write_text(self._run_batch(target), encoding="utf-8")
        readme = target.parent / "README_exported_macros.txt"
        if not readme.exists():
            readme.write_text(self._readme_text(), encoding="utf-8")

    def _install_batch(self) -> str:
        python_exe = str(Path(sys.executable))
        return dedent(
            f'''\
            @echo off
            setlocal
            cd /d "%~dp0"
            set "PYTHON_EXE={python_exe}"
            if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
            if not exist "dependencies" mkdir "dependencies"
            "%PYTHON_EXE%" -m pip install --upgrade --target "%~dp0dependencies" -r "%~dp0requirements.txt"
            if errorlevel 1 (
                echo Failed to install Macro Recorder + export dependencies.
                pause
                exit /b 1
            )
            echo Dependencies installed in "%~dp0dependencies".
            '''
        )

    def _run_batch(self, target: Path) -> str:
        python_exe = str(Path(sys.executable))
        return dedent(
            f'''\
            @echo off
            setlocal
            cd /d "%~dp0"
            set "PYTHON_EXE={python_exe}"
            if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"
            set "RUNTIME_DIR=%~dp0{RUNTIME_DIR_NAME}"
            set "DEPS_DIR=%RUNTIME_DIR%\\{DEPENDENCIES_DIR_NAME}"
            if not exist "%DEPS_DIR%\\pynput" (
                call "%RUNTIME_DIR%\\install_dependencies.bat"
                if errorlevel 1 exit /b 1
            )
            "%PYTHON_EXE%" "%~dp0{target.name}" %*
            '''
        )

    def _readme_text(self) -> str:
        return dedent(
            '''\
            Macro Recorder + exported Python macros

            Run a macro with its generated run_*.bat file. The batch file installs pynput into
            macro_recorder_plus_runtime\\dependencies on first run, then starts the exported script.

            Useful direct commands:
              python your_macro.py --install-deps
              python your_macro.py --dry-run
              python your_macro.py --speed 1.5
              python your_macro.py --start-action 12

            Press F10 while a macro is running to request an emergency stop.
            '''
        )
