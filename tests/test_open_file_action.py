from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform import windows_input
from macro_recorder_plus.platform.windows_input import ActionExecutor


def test_executor_dispatches_open_file_action(monkeypatch):
    opened = []
    monkeypatch.setattr(windows_input, "open_file_with_default_app", lambda path, **kwargs: opened.append((path, kwargs)))

    executor = ActionExecutor(None, None)
    executor.execute(
        MacroAction(
            type=ActionType.OPEN_FILE,
            params={"file_path": "notes.pdf", "target_monitor": "primary", "auto_focus": True},
        )
    )

    assert opened == [("notes.pdf", {"target_monitor": "primary", "auto_focus": True})]


def test_open_file_with_default_app_uses_windows_default_app(tmp_path, monkeypatch):
    file_path = tmp_path / "notes.txt"
    file_path.write_text("hello", encoding="utf-8")
    opened = []
    monkeypatch.setattr(windows_input.sys, "platform", "win32")
    monkeypatch.setattr(windows_input.os, "startfile", lambda path: opened.append(path), raising=False)

    windows_input.open_file_with_default_app(str(file_path))

    assert opened == [str(file_path)]


def test_launch_program_arranges_window_when_requested(monkeypatch):
    calls = []

    class FakeProcess:
        pid = 1234

    monkeypatch.setattr(windows_input.subprocess, "Popen", lambda command, cwd=None: FakeProcess())
    monkeypatch.setattr(windows_input, "arrange_process_window", lambda *args, **kwargs: calls.append((args, kwargs)))

    executor = ActionExecutor(None, None)
    executor.execute(
        MacroAction(
            type=ActionType.LAUNCH_PROGRAM,
            params={
                "executable": "notepad.exe",
                "target_monitor": "2",
                "auto_focus": True,
                "startup_timeout": 3.0,
            },
        )
    )

    assert calls == [((1234,), {"target_monitor": "2", "auto_focus": True, "timeout": 3.0})]
