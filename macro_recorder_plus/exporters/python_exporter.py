from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

from macro_recorder_plus.models.macro import MacroDocument


class PythonExporter:
    def render(self, document: MacroDocument) -> str:
        payload = json.dumps(document.to_dict(), indent=2, sort_keys=True)
        return dedent(
            f'''\
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

            MACRO = json.loads(r"""{payload}""")


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


            def key_from_name(name, keyboard):
                lookup = {{
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
                }}
                key = str(name).lower().replace("key.", "")
                return lookup.get(key) or keyboard.KeyCode.from_char(key)


            def button_from_name(name, mouse):
                return getattr(mouse.Button, str(name).lower().replace("button.", ""))


            def mouse_move_points(action):
                params = action.get("params", {{}})
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
                args = parser.parse_args()
                set_dpi_awareness()

                try:
                    from pynput import keyboard, mouse
                except Exception as exc:
                    print(f"pynput is required: {{exc}}", file=sys.stderr)
                    return 2

                keyboard_controller = keyboard.Controller()
                mouse_controller = mouse.Controller()
                stop_event = threading.Event()
                hotkey_listener = keyboard.GlobalHotKeys({{"<f10>": stop_event.set}})
                hotkey_listener.start()
                held_keys = []
                held_buttons = []

                def release_all():
                    for key in reversed(held_keys):
                        try:
                            keyboard_controller.release(key)
                        except Exception:
                            pass
                    for button in reversed(held_buttons):
                        try:
                            mouse_controller.release(button)
                        except Exception:
                            pass
                    held_keys.clear()
                    held_buttons.clear()

                try:
                    previous = 0.0
                    for index, action in enumerate(MACRO["actions"][args.start_action:], start=args.start_action):
                        if stop_event.is_set():
                            print("Emergency stop requested", file=sys.stderr)
                            return 130
                        if not action.get("enabled", True):
                            continue
                        delay = max(0.0, float(action.get("delay", 0.0))) / max(0.01, args.speed)
                        if delay:
                            time.sleep(delay)
                        print(f"{{index}}: {{action['type']}} {{action.get('label') or action.get('params', '')}}")
                        if args.dry_run:
                            continue

                        params = action.get("params", {{}})
                        action_type = action["type"]
                        if action_type == "wait":
                            time.sleep(float(params.get("seconds", action.get("duration", 0))) / max(0.01, args.speed))
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
                                secret = getpass(f"{{env_name}}: ")
                            if secret is None:
                                raise RuntimeError(f"Missing environment variable {{env_name}}")
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
                                if not sleep_until(start_time + (relative_time / max(0.01, args.speed)), stop_event):
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
                    print(f"Playback failed: {{exc}}", file=sys.stderr)
                    return 1
                finally:
                    try:
                        hotkey_listener.stop()
                    except Exception:
                        pass
                    release_all()


            if __name__ == "__main__":
                raise SystemExit(main())
            '''
        )

    def export(self, document: MacroDocument, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != ".py":
            target = target.with_suffix(".py")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.render(document), encoding="utf-8")
        return target
