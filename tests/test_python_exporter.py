from __future__ import annotations

import math
import py_compile
import random
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
from macro_recorder_plus.models.actions import ActionType, MacroAction, create_action
from macro_recorder_plus.models.environment import RecordedEnvironment, Rect
from macro_recorder_plus.models.macro import MacroDocument
from macro_recorder_plus.platform.windows_input import image_movement_points_for_match
from macro_recorder_plus.utilities.mouse_path import humanized_path_points, image_chain_transition_points


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
    assert "pending_window_placement" not in text
    assert "Window placement reapplied after startup wait" not in text
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


def test_python_export_uses_saved_random_delay_between_whole_macro_loops(tmp_path):
    document = MacroDocument(
        name="paced export",
        settings={
            "playback_speed": 1.0,
            "coordinate_mode": "exact",
            "macro_loop_count": 3,
            "macro_loop_delay_mode": "random",
            "macro_loop_delay_min": 1.0,
            "macro_loop_delay_max": 2.0,
        },
        actions=[MacroAction(type=ActionType.COMMENT, params={"text": "check"})],
    )
    path = PythonExporter().export(document, tmp_path / "paced.py")
    exported = runpy.run_path(str(path))

    assert exported["macro_loop_delay_range"](exported["MACRO"]["settings"]) == (1.0, 2.0)
    result = subprocess.run(
        [sys.executable, str(path), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.count("Waiting ") == 2


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


def test_python_export_humanizes_only_tagged_mouse_moves_and_keeps_click_at_varied_destination(tmp_path):
    document = MacroDocument(
        name="humanized export",
        actions=[
            MacroAction(
                type=ActionType.MOUSE_MOVE,
                timestamp=0.0,
                duration=1.0,
                params={
                    "start": [0, 0],
                    "end": [100, 0],
                    "path": [[0, 0, 0.0], [100, 0, 1.0]],
                    "humanize_playback": True,
                },
            )
        ],
    )
    path = PythonExporter().export(document, tmp_path / "humanized.py")
    exported = runpy.run_path(str(path))
    action = exported["MACRO"]["actions"][0]
    bounds = {"left": -1000, "top": -1000, "right": 1000, "bottom": 1000}

    varied = exported["playback_mouse_points"](action, bounds, rng=random.Random(7))
    legacy_action = {**action, "params": {**action["params"]}}
    legacy_action["params"].pop("humanize_playback")
    legacy = exported["playback_mouse_points"](legacy_action, bounds, rng=random.Random(7))
    app_varied = humanized_path_points([(0, 0, 0.0), (100, 0, 1.0)], rng=random.Random(7))
    destination = varied[-1][:2]
    state = {
        "humanized_mouse_source": (100, 0),
        "humanized_mouse_destination": destination,
    }

    assert math.hypot(destination[0] - 100, destination[1]) <= 5
    assert 0.1 <= abs(varied[-1][2] - 1.0) <= 0.2
    assert legacy[-1] == (100, 0, 1.0)
    assert varied == app_varied
    assert exported["resolved_mouse_target"]({"x": 100, "y": 0}, state) == destination


def test_python_export_preserves_natural_image_start_and_click_circles(tmp_path):
    action = MacroAction(
        type=ActionType.IMAGE_CLICK,
        params={
            "natural_movement": True,
            "movement_start_mode": "screen",
            "movement_start_center": [400, 300],
            "movement_start_radius": 100,
            "click_offset": [3, -2],
            "click_radius": 5,
            "path_variance": 8.0,
            "movement_duration": 0.75,
        },
    )
    path = PythonExporter().export(MacroDocument(name="image circles", actions=[action]), tmp_path / "image_circles.py")
    exported = runpy.run_path(str(path))
    params = exported["MACRO"]["actions"][0]["params"]
    bounds_dict = {"left": 0, "top": 0, "right": 1920, "bottom": 1080}
    exported_points = exported["image_movement_points"](
        params,
        {"center": (800, 500)},
        start_position=(10, 10),
        current_bounds=bounds_dict,
        rng=random.Random(7),
    )
    app_points = image_movement_points_for_match(
        action,
        type("Match", (), {"center": (800, 500)})(),
        start_position=(10, 10),
        bounds=Rect(0, 0, 1920, 1080),
        rng=random.Random(7),
    )

    assert exported_points == app_points


def test_python_export_preserves_consecutive_image_transition_behavior(tmp_path):
    document = MacroDocument(
        name="chained image actions",
        actions=[create_action(ActionType.IMAGE_CLICK), create_action(ActionType.IMAGE_CLICK)],
    )
    path = PythonExporter().export(document, tmp_path / "chained_images.py")
    exported = runpy.run_path(str(path))
    text = path.read_text(encoding="utf-8")

    exported_points = exported["image_chain_transition_points"](
        (120, 80),
        (700, 420),
        rng=random.Random(7),
    )
    app_points = image_chain_transition_points((120, 80), (700, 420), rng=random.Random(7))

    assert exported_points == app_points
    assert 0.3 <= exported_points[-1][2] <= 0.8
    assert 'runtime_state["previous_natural_image_index"]' in text
    assert "chain_from_previous_image=(chain_from_previous_image and action_loop_index == 0)" in text


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
    assert "browser.exe" in text
    main_text = text.split("def main():", 1)[1]
    wait_block, open_url_and_after = main_text.split('elif action_type == "open_url":', 1)
    open_url_block = open_url_and_after.split('elif action_type == "open_file":', 1)[0]
    assert "arrange_existing_window(" not in wait_block.split('if action_type == "wait":', 1)[1]
    assert open_url_block.count("arrange_existing_window(") == 1
    assert 'params["window_placement"]' in open_url_block
    assert 'webbrowser.open(params["url"])' in open_url_block
    assert "pending_window_placement" not in main_text
    assert "Window placement reapplied after startup wait" not in main_text


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
