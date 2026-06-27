from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel

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


def test_settings_dialog_persists_appearance_values(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    dialog.theme_mode.setCurrentText("dark")
    dialog.primary_color.setText("#12abEF")
    dialog.corner_shape.setCurrentText("rounded")
    dialog.accept()

    assert settings.value("appearance/theme") == "dark"
    assert settings.value("appearance/primary_color") == "#12ABEF"
    assert settings.value("appearance/corner_shape") == "rounded"


def test_settings_dialog_does_not_reuse_emergency_hotkey_widget(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    assert dialog.playback_emergency_hotkey is not dialog.emergency_hotkey
    assert dialog.playback_emergency_hotkey.text() == "<f10>"

    dialog.emergency_hotkey.setText("<f11>")

    assert dialog.playback_emergency_hotkey.text() == "<f11>"


def test_export_tab_explains_export_settings(tmp_path, qtbot):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)

    help_text = "\n".join(label.text() for label in dialog.findChildren(QLabel, "settingsHelpText"))

    assert "standalone Python script" in help_text
    assert "PyInstaller" in help_text
