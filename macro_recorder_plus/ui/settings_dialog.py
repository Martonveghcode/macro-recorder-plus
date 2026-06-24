from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.exporters.python_exporter import default_export_directory
from macro_recorder_plus.platform.windows_hotkeys import DEFAULT_HOTKEYS, validate_hotkey_conflicts


class SettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        self.countdown = QSpinBox()
        self.countdown.setRange(0, 60)
        self.mouse_hz = QSpinBox()
        self.mouse_hz.setRange(5, 240)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0, 50)
        self.record_mouse = QCheckBox()
        self.record_keyboard = QCheckBox()
        self.record_scroll = QCheckBox()
        self.sounds = QCheckBox()
        self.hide_recording = QCheckBox()
        tabs.addTab(self._form_tab(
            [
                ("Countdown duration", self.countdown),
                ("Mouse sample rate", self.mouse_hz),
                ("Path tolerance", self.tolerance),
                ("Record mouse movement", self.record_mouse),
                ("Record keyboard input", self.record_keyboard),
                ("Record scroll input", self.record_scroll),
                ("Play sounds", self.sounds),
                ("Hide during recording", self.hide_recording),
            ]
        ), "Recording")

        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 10.0)
        self.speed.setSingleStep(0.1)
        self.preplay_countdown = QSpinBox()
        self.preplay_countdown.setRange(0, 60)
        self.coordinate_mode = QLineEdit()
        self.emergency_hotkey = QLineEdit()
        self.corner_failsafe = QCheckBox()
        self.confirm_long = QCheckBox()
        tabs.addTab(self._form_tab(
            [
                ("Default speed", self.speed),
                ("Pre-playback countdown", self.preplay_countdown),
                ("Coordinate mode", self.coordinate_mode),
                ("Emergency-stop hotkey", self.emergency_hotkey),
                ("Corner failsafe", self.corner_failsafe),
                ("Confirm long macros", self.confirm_long),
            ]
        ), "Playback")

        self.start_hotkey = QLineEdit()
        self.stop_hotkey = QLineEdit()
        self.pause_record_hotkey = QLineEdit()
        self.pause_play_hotkey = QLineEdit()
        tabs.addTab(self._form_tab(
            [
                ("Start recording", self.start_hotkey),
                ("Stop recording", self.stop_hotkey),
                ("Pause/resume recording", self.pause_record_hotkey),
                ("Emergency stop", self.emergency_hotkey),
                ("Pause/resume playback", self.pause_play_hotkey),
            ]
        ), "Hotkeys")

        self.export_dir = QLineEdit()
        self.python_path = QLineEdit()
        self.pyinstaller_path = QLineEdit()
        self.exe_options = QLineEdit()
        tabs.addTab(self._form_tab(
            [
                ("Default export directory", self.export_dir),
                ("Python interpreter path", self.python_path),
                ("PyInstaller executable path", self.pyinstaller_path),
                ("Default .exe options", self.exe_options),
            ]
        ), "Export")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load()

    def _form_tab(self, rows: list[tuple[str, QWidget]]) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        for label, widget in rows:
            form.addRow(label, widget)
        return tab

    def _load(self) -> None:
        self.countdown.setValue(int(self.settings.value("recording/countdown", 5)))
        self.mouse_hz.setValue(int(self.settings.value("recording/mouse_hz", 60)))
        self.tolerance.setValue(float(self.settings.value("recording/tolerance", 2.0)))
        self.record_mouse.setChecked(self.settings.value("recording/record_mouse", True, bool))
        self.record_keyboard.setChecked(self.settings.value("recording/record_keyboard", True, bool))
        self.record_scroll.setChecked(self.settings.value("recording/record_scroll", True, bool))
        self.sounds.setChecked(self.settings.value("recording/sounds", True, bool))
        self.hide_recording.setChecked(self.settings.value("recording/hide", False, bool))
        self.speed.setValue(float(self.settings.value("playback/speed", 1.0)))
        self.preplay_countdown.setValue(int(self.settings.value("playback/countdown", 0)))
        self.coordinate_mode.setText(str(self.settings.value("playback/coordinate_mode", "exact")))
        self.emergency_hotkey.setText(str(self.settings.value("hotkeys/emergency_stop", DEFAULT_HOTKEYS["emergency_stop"])))
        self.corner_failsafe.setChecked(self.settings.value("playback/corner_failsafe", True, bool))
        self.confirm_long.setChecked(self.settings.value("playback/confirm_long", True, bool))
        self.start_hotkey.setText(str(self.settings.value("hotkeys/start_recording", DEFAULT_HOTKEYS["start_recording"])))
        self.stop_hotkey.setText(str(self.settings.value("hotkeys/stop_recording", DEFAULT_HOTKEYS["stop_recording"])))
        self.pause_record_hotkey.setText(str(self.settings.value("hotkeys/pause_recording", DEFAULT_HOTKEYS["pause_recording"])))
        self.pause_play_hotkey.setText(str(self.settings.value("hotkeys/pause_playback", DEFAULT_HOTKEYS["pause_playback"])))
        self.export_dir.setText(str(self.settings.value("export/directory", str(default_export_directory()))))
        self.python_path.setText(str(self.settings.value("export/python", "")))
        self.pyinstaller_path.setText(str(self.settings.value("export/pyinstaller", "")))
        self.exe_options.setText(str(self.settings.value("export/options", "")))

    def accept(self) -> None:
        hotkeys = {
            "start_recording": self.start_hotkey.text(),
            "stop_recording": self.stop_hotkey.text(),
            "pause_recording": self.pause_record_hotkey.text(),
            "emergency_stop": self.emergency_hotkey.text(),
            "pause_playback": self.pause_play_hotkey.text(),
        }
        duplicates = validate_hotkey_conflicts(hotkeys)
        if duplicates:
            self.start_hotkey.setToolTip(f"Duplicate hotkey: {', '.join(duplicates)}")
            return
        self.settings.setValue("recording/countdown", self.countdown.value())
        self.settings.setValue("recording/mouse_hz", self.mouse_hz.value())
        self.settings.setValue("recording/tolerance", self.tolerance.value())
        self.settings.setValue("recording/record_mouse", self.record_mouse.isChecked())
        self.settings.setValue("recording/record_keyboard", self.record_keyboard.isChecked())
        self.settings.setValue("recording/record_scroll", self.record_scroll.isChecked())
        self.settings.setValue("recording/sounds", self.sounds.isChecked())
        self.settings.setValue("recording/hide", self.hide_recording.isChecked())
        self.settings.setValue("playback/speed", self.speed.value())
        self.settings.setValue("playback/countdown", self.preplay_countdown.value())
        self.settings.setValue("playback/coordinate_mode", self.coordinate_mode.text())
        self.settings.setValue("playback/corner_failsafe", self.corner_failsafe.isChecked())
        self.settings.setValue("playback/confirm_long", self.confirm_long.isChecked())
        for name, value in hotkeys.items():
            self.settings.setValue(f"hotkeys/{name}", value)
        self.settings.setValue("export/directory", self.export_dir.text())
        self.settings.setValue("export/python", self.python_path.text())
        self.settings.setValue("export/pyinstaller", self.pyinstaller_path.text())
        self.settings.setValue("export/options", self.exe_options.text())
        self.settings.sync()
        super().accept()
