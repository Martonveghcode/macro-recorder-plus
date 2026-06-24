from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from macro_recorder_plus.recorder.input_recorder import RecordingOptions
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
