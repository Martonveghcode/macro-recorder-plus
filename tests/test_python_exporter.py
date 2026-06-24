from __future__ import annotations

import py_compile
import subprocess
import sys

from macro_recorder_plus.exporters.python_exporter import RUNTIME_DIR_NAME, PythonExporter
from macro_recorder_plus.models.actions import ActionType, MacroAction
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
    assert "<f10>" in text
    assert "WEBSITE_PASSWORD" in text
    assert "set_dpi_awareness" in text
    assert "interpolated_mouse_points" in text
    assert "mouse_move_points" in text


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


def test_python_export_writes_dependency_support_files(tmp_path):
    document = MacroDocument(name="export")

    path = PythonExporter().export(document, tmp_path / "exported.py")

    runtime_dir = path.parent / RUNTIME_DIR_NAME
    assert (runtime_dir / "requirements.txt").read_text(encoding="utf-8").strip() == "pynput>=1.7.7"
    assert (runtime_dir / "install_dependencies.bat").exists()
    assert (path.parent / "run_exported.bat").exists()
    assert (path.parent / "README_exported_macros.txt").exists()
