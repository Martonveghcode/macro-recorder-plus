from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

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
    assert "Recording starts in" in window.status.currentMessage()
    window._cancel_countdown()
