from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog

from macro_recorder_plus.models.actions import ActionType, MacroAction, create_action
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


def test_macro_loop_setting_is_saved_and_passed_to_playback(tmp_path, qtbot, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    window.document = MacroDocument(name="looped", actions=[create_action(ActionType.COMMENT)])
    window.model.replace_actions(window.document.actions)
    window.macro_loop_spin.setValue(5)
    calls = []
    monkeypatch.setattr(window.playback, "play", lambda actions, **kwargs: calls.append(kwargs))

    window._start_playback(0)

    assert window.document.settings["macro_loop_count"] == 5
    assert calls[0]["repeat_count"] == 5
    window.model.set_dirty(False)


def test_pre_actions_are_passed_once_outside_main_macro_loop(tmp_path, qtbot, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    pre_action = create_action(ActionType.LAUNCH_PROGRAM)
    main_action = create_action(ActionType.COMMENT)
    window.document = MacroDocument(name="prepared", pre_actions=[pre_action], actions=[main_action])
    window.model.replace_actions(window.document.actions)
    window.pre_action_model.replace_actions(window.document.pre_actions)
    window.macro_loop_spin.setValue(7)
    calls = []
    monkeypatch.setattr(window.playback, "play", lambda actions, **kwargs: calls.append((actions, kwargs)))

    window._start_playback(0)

    assert calls[0][0] == [main_action]
    assert calls[0][1]["pre_actions"] == [pre_action]
    assert calls[0][1]["repeat_count"] == 7
    window.model.set_dirty(False)


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


def test_step_forward_runs_a_shortcut_chord_as_one_unit_and_back_repositions(tmp_path, qtbot, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    actions = [
        MacroAction(type=ActionType.KEY_PRESS, params={"key": "ctrl", "phase": "press"}),
        MacroAction(type=ActionType.KEY_PRESS, params={"key": "v", "phase": "press"}),
        MacroAction(type=ActionType.KEY_PRESS, params={"key": "v", "phase": "release"}),
        MacroAction(type=ActionType.KEY_PRESS, params={"key": "ctrl", "phase": "release"}),
        create_action(ActionType.MOUSE_MOVE),
    ]
    window.document = MacroDocument(name="stepped", actions=actions)
    window.model.replace_actions(actions)
    calls = []
    monkeypatch.setattr(window.playback, "play", lambda recorded_actions, **kwargs: calls.append(kwargs))

    window.step_forward()

    assert calls[0]["start_index"] == 0
    assert calls[0]["end_index"] == 4
    assert calls[0]["repeat_count"] == 1
    assert calls[0]["respect_action_delays"] is False
    window._playback_context(4, None)
    window._playback_finished(True, "Playback complete")
    assert window._step_cursor == 4

    window.step_back()

    assert window._step_cursor == 0
    assert window.model.current_playback_row == 0


def test_step_forward_treats_common_shortcuts_as_individual_actions(tmp_path, qtbot, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    window = MainWindow(settings=settings, log_path=Path(tmp_path / "app.log"))
    qtbot.addWidget(window)
    actions = [
        MacroAction(type=ActionType.HOTKEY, params={"keys": ["ctrl", key]})
        for key in ["a", "c", "x", "v"]
    ]
    window.document = MacroDocument(name="shortcuts", actions=actions)
    window.model.replace_actions(actions)
    calls = []
    monkeypatch.setattr(window.playback, "play", lambda recorded_actions, **kwargs: calls.append(kwargs))

    window.step_forward()

    assert calls[0]["start_index"] == 0
    assert calls[0]["end_index"] == 1
