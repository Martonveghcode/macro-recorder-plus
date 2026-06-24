from __future__ import annotations

from PySide6.QtCore import QSettings

from macro_recorder_plus.ui.settings_dialog import SettingsDialog


def test_settings_dialog_persists_values(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    dialog.countdown.setValue(7)
    dialog.speed.setValue(1.5)
    dialog.accept()

    assert int(settings.value("recording/countdown")) == 7
    assert float(settings.value("playback/speed")) == 1.5
