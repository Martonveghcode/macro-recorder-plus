from __future__ import annotations

import py_compile
import runpy
import subprocess
import sys
from pathlib import Path

from PIL import Image

from macro_recorder_plus.exporters.python_exporter import (
    ASSETS_DIR_NAME,
    RUNTIME_DIR_NAME,
    PythonExporter,
    export_support_directory,
)
from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.environment import RecordedEnvironment, Rect
from macro_recorder_plus.models.macro import MacroDocument


def test_python_export_contains_cli_options_and_macro_data(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.TYPE_SECRET, params={"environment_variable": "WEBSITE_PASSWORD"})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    assert "--dry-run" in text
    assert "--start-action" in text
    assert "--end-action" in text
    assert "<f10>" in text
    assert "WEBSITE_PASSWORD" in text
    assert "set_dpi_awareness" in text
    assert "SetThreadDpiAwarenessContext" in text
    assert "interpolated_mouse_points" in text
    assert "mouse_move_points" in text
    assert "transform_action_coordinates" in text
    assert "begin_macro_loop" in text
    assert "position_mouse" in text
    assert "ensure_dependencies" in text
    assert "--log-file" in text
    assert "is_dedicated_console_launch" in text
    assert "hide_console_window" in text
    assert 'return sys.platform == "win32" and len(sys.argv) == 1' in text
    assert 'RUNTIME_DIR / f"{Path(__file__).stem}.log"' in text
    assert "traceback.print_exc()" in text
    assert "pending_window_placement" in text
    assert "Window placement reapplied after startup wait" in text
    main_text = text.split("def main():", 1)[1]
    assert main_text.index("set_dpi_awareness()") < main_text.index("hide_console_window()")


def test_python_export_is_valid_and_dry_run_does_not_need_pynput(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.COMMENT, params={"text": "check"})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")

    py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "0: comment" in result.stdout


def test_python_export_dry_run_repeats_looped_actions(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.COMMENT, loop_count=3, params={"text": "check"})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")

    py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.count("0: comment") == 3


def test_python_export_dry_run_repeats_whole_macro_and_allows_override(tmp_path):
    document = MacroDocument(
        name="export",
        settings={"playback_speed": 1.0, "coordinate_mode": "exact", "macro_loop_count": 3},
        actions=[MacroAction(type=ActionType.COMMENT, params={"text": "check"})],
    )
    path = PythonExporter().export(document, tmp_path / "exported.py")

    saved_result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    override_result = subprocess.run(
        [sys.executable, str(path), "--dry-run", "--loops", "2"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert saved_result.returncode == 0
    assert saved_result.stdout.count("0: comment") == 3
    assert override_result.returncode == 0
    assert override_result.stdout.count("0: comment") == 2


def test_python_export_can_limit_playback_to_an_action_range(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[
            MacroAction(type=ActionType.COMMENT, label="first"),
            MacroAction(type=ActionType.COMMENT, label="second"),
            MacroAction(type=ActionType.COMMENT, label="third"),
        ],
    )
    path = PythonExporter().export(document, tmp_path / "exported.py")

    result = subprocess.run(
        [sys.executable, str(path), "--dry-run", "--start-action", "1", "--end-action", "2"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "first" not in result.stdout
    assert "second" in result.stdout
    assert "third" not in result.stdout


def test_python_export_uses_saved_playback_speed_by_default(tmp_path):
    document = MacroDocument(
        name="export",
        settings={"playback_speed": 1.75, "coordinate_mode": "exact", "macro_loop_count": 1},
    )
    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    assert 'parser.add_argument("--speed", type=float, default=None' in text
    assert 'MACRO.get("settings", {}).get("playback_speed", 1.0)' in text


def test_python_export_coordinate_transform_and_verified_mouse_match_app(tmp_path):
    document = MacroDocument(
        name="export",
        recorded_environment=RecordedEnvironment(virtual_desktop=Rect(0, 0, 100, 100), cursor_start=[25, 50]),
        settings={"playback_speed": 1.0, "coordinate_mode": "scaled", "macro_loop_count": 1},
    )
    path = PythonExporter().export(document, tmp_path / "exported.py")
    exported = runpy.run_path(str(path))

    transformed = exported["transform_point"](
        50,
        50,
        document.recorded_environment.to_dict(),
        {"left": -200, "top": 0, "right": 200, "bottom": 200},
        "scaled",
    )

    class LaggingMouse:
        def __init__(self):
            self.assignments = 0
            self._position = (0, 0)

        @property
        def position(self):
            return self._position

        @position.setter
        def position(self, value):
            self.assignments += 1
            self._position = (0, 0) if self.assignments < 3 else value

    mouse = LaggingMouse()

    assert transformed == (0, 100)
    assert exported["position_mouse"](mouse, 500, -200) == (500, -200)
    assert mouse.assignments == 3


def test_python_export_runs_pre_actions_once_before_looped_actions(tmp_path):
    document = MacroDocument(
        name="export",
        settings={"playback_speed": 1.0, "coordinate_mode": "exact", "macro_loop_count": 3},
        pre_actions=[MacroAction(type=ActionType.COMMENT, label="setup", params={"text": "setup"})],
        actions=[MacroAction(type=ActionType.COMMENT, label="main", params={"text": "main"})],
    )
    path = PythonExporter().export(document, tmp_path / "exported.py")

    result = subprocess.run([sys.executable, str(path), "--dry-run"], capture_output=True, text=True, check=False)

    assert result.returncode == 0
    assert result.stdout.count("setup") == 1
    assert result.stdout.count("main") == 3
    assert result.stdout.index("setup") < result.stdout.index("main")


def test_python_export_supports_open_file_dry_run(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.OPEN_FILE, params={"file_path": "notes.pdf"})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert "open_file_with_default_app" in text
    assert result.returncode == 0
    assert "0: open_file" in result.stdout


def test_python_export_supports_open_url_window_placement(tmp_path):
    placement = {
        "process_path": r"C:\Program Files\Browser\browser.exe",
        "window_title": "Browser",
        "monitor_index": 0,
        "x": 10,
        "y": 20,
        "width": 900,
        "height": 700,
    }
    document = MacroDocument(
        name="export",
        actions=[MacroAction(type=ActionType.OPEN_URL, params={"url": "https://example.com", "window_placement": placement})],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    py_compile.compile(str(path), doraise=True)
    assert "arrange_existing_window" in text
    assert "browser.exe" in text


def test_python_export_supports_if_image_result_dry_run(tmp_path):
    document = MacroDocument(
        name="export",
        actions=[
            MacroAction(type=ActionType.IF_CONDITION, params={"image_found_action": 1, "image_not_found_action": 0}),
        ],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")

    py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert "conditional_jump_target" in text
    assert result.returncode == 0
    assert "0: if_condition" in result.stdout


def test_python_export_writes_dependency_support_files(tmp_path):
    document = MacroDocument(name="export")

    path = PythonExporter().export(document, tmp_path / "exported.py")

    runtime_dir = path.parent / RUNTIME_DIR_NAME
    requirements = (runtime_dir / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "pynput>=1.7.7" in requirements
    assert "Pillow>=10" in requirements
    assert "numpy>=1.26" in requirements
    assert (runtime_dir / "install_dependencies.bat").exists()
    assert (path.parent / "run_exported.bat").exists()
    assert (path.parent / "README_exported_macros.txt").exists()
    assert "Secret actions read from environment variables" in (path.parent / "README_exported_macros.txt").read_text(encoding="utf-8")


def test_desktop_export_keeps_only_python_file_visible_and_uses_misc_for_support(tmp_path):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    target = desktop / "news_macro.py"

    path = PythonExporter().export(MacroDocument(name="news"), target)
    support_dir = desktop / "misc"
    text = path.read_text(encoding="utf-8")

    assert export_support_directory(target) == support_dir
    assert path == target
    assert sorted(item.name for item in desktop.iterdir()) == ["misc", "news_macro.py"]
    assert (support_dir / RUNTIME_DIR_NAME / "requirements.txt").exists()
    assert (support_dir / RUNTIME_DIR_NAME / "install_dependencies.bat").exists()
    assert (support_dir / "README_exported_macros.txt").exists()
    assert target.exists()
    assert not (desktop / "run_news_macro.bat").exists()
    assert repr(str(Path("misc") / RUNTIME_DIR_NAME)) in text
    assert "Missing export dependencies" in text
    assert "Double-click the exported .py file" in (support_dir / "README_exported_macros.txt").read_text(encoding="utf-8")


def test_python_export_uses_configured_python_in_batch_files(tmp_path):
    document = MacroDocument(name="export")
    python_executable = r"C:\Tools\Python312\python.exe"

    path = PythonExporter(python_executable=python_executable).export(document, tmp_path / "exported.py")

    assert python_executable in (path.parent / "run_exported.bat").read_text(encoding="utf-8")
    assert python_executable in (path.parent / RUNTIME_DIR_NAME / "install_dependencies.bat").read_text(encoding="utf-8")


def test_python_export_copies_image_click_assets(tmp_path):
    image_path = tmp_path / "button.png"
    Image.new("RGB", (4, 4), "red").save(image_path)
    document = MacroDocument(
        name="export",
        actions=[
            MacroAction(
                type=ActionType.IMAGE_CLICK,
                params={"image_path": str(image_path), "click_action": "left_click"},
            )
        ],
    )

    path = PythonExporter().export(document, tmp_path / "exported.py")
    text = path.read_text(encoding="utf-8")
    assets = list((path.parent / ASSETS_DIR_NAME).glob("*.png"))

    assert len(assets) == 1
    assert str(image_path) not in text
    assert ASSETS_DIR_NAME in text
