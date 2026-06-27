from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog

from macro_recorder_plus.models.actions import ActionType, create_action
from macro_recorder_plus.models.macro import MacroDocument
from macro_recorder_plus.recorder.input_recorder import RecordingOptions
from macro_recorder_plus.storage.json_store import save_macro
from macro_recorder_plus.ui.state import AppState
from macro_recorder_plus.ui.main_window import MainWindow


def test_primary_controls_are_clickable_at_startup(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)

    assert window.record_button.isEnabled()
    assert window.run_button.isEnabled()
    assert window.pause_button.isEnabled()
    assert window.stop_button.isEnabled()
    assert window.act_run.isEnabled()
    assert window.act_pause_active.isEnabled()
    assert window.act_stop_active.isEnabled()


def test_run_without_macro_reports_status(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)

    window.run_button.click()

    assert window.status.currentMessage() == "No actions to run"


def test_open_saved_macro_enables_export_actions(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    path = save_macro(MacroDocument(name="saved", actions=[create_action(ActionType.WAIT)]), tmp_path / "saved.mrplus.json")

    assert not window.act_export_py.isEnabled()

    window._open_path(path)

    assert window.act_export_py.isEnabled()
    assert window.act_export_exe.isEnabled()


def test_countdown_has_visible_main_window_feedback(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)

    window._start_countdown(5, "Recording", lambda: None)

    assert window.state == AppState.COUNTING_DOWN
    assert window.record_button.text() == "Cancel Countdown"
    assert window.stop_button.text() == "Cancel"
    assert not window.countdown_banner.isHidden()
    assert window.countdown_banner.text().startswith("Recording starts in")
    assert "Recording starts in" in window.status.currentMessage()
    window._cancel_countdown()


def test_record_command_uses_direct_recording_path(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    calls = []

    def fake_start_new_recording(*, options, countdown_seconds, hide_during_recording):
        calls.append((options, countdown_seconds, hide_during_recording))

    window._start_new_recording = fake_start_new_recording

    window.record_new_macro()

    assert len(calls) == 1
    options, countdown_seconds, hide_during_recording = calls[0]
    assert isinstance(options, RecordingOptions)
    assert countdown_seconds == 5
    assert hide_during_recording is False


def test_open_settings_restarts_hotkeys_when_dialog_is_accepted(tmp_path, qtbot, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    calls = []

    class FakeSettingsDialog:
        def __init__(self, settings, parent=None):
            self.settings = settings
            self.parent = parent

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr("macro_recorder_plus.ui.main_window.SettingsDialog", FakeSettingsDialog)
    monkeypatch.setattr("macro_recorder_plus.ui.main_window.apply_theme", lambda settings: calls.append("theme") or None)
    monkeypatch.setattr(window, "_refresh_themed_widgets", lambda: calls.append("refresh"))
    monkeypatch.setattr(window, "_restart_hotkeys", lambda: calls.append("restart"))

    window.open_settings()

    assert calls == ["theme", "refresh", "restart"]
