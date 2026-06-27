from __future__ import annotations

import sys

from PySide6.QtCore import QRegularExpression, QSettings, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.exporters.python_exporter import default_export_directory
from macro_recorder_plus.platform.windows_hotkeys import DEFAULT_HOTKEYS, validate_hotkey_conflicts
from macro_recorder_plus.ui.theme import CORNER_SHAPES, HEX_COLOR_RE, THEME_MODES, load_appearance_settings


class SettingsDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        self.theme_mode = QComboBox()
        self.theme_mode.addItems(THEME_MODES)
        self.primary_color = QLineEdit()
        self.primary_color.setPlaceholderText("#D0BCFF")
        self.primary_color.setValidator(QRegularExpressionValidator(QRegularExpression(r"^#[0-9A-Fa-f]{6}$"), self))
        self.corner_shape = QComboBox()
        self.corner_shape.addItems(CORNER_SHAPES)
        tabs.addTab(self._form_tab(
            [
                ("Theme", self.theme_mode),
                ("Primary accent color", self.primary_color),
                ("Corner shape", self.corner_shape),
            ]
        ), "Appearance Customisation")

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
        self.playback_emergency_hotkey = QLineEdit()
        self.playback_emergency_hotkey.setReadOnly(True)
        self.playback_emergency_hotkey.setFocusPolicy(Qt.NoFocus)
        self.playback_emergency_hotkey.setToolTip("Edit this key in the Hotkeys tab.")
        self.corner_failsafe = QCheckBox()
        self.confirm_long = QCheckBox()
        tabs.addTab(self._form_tab(
            [
                ("Default speed", self.speed),
                ("Pre-playback countdown", self.preplay_countdown),
                ("Coordinate mode", self.coordinate_mode),
                ("Emergency-stop hotkey", self.playback_emergency_hotkey),
                ("Corner failsafe", self.corner_failsafe),
                ("Confirm long macros", self.confirm_long),
            ]
        ), "Playback")

        self.start_hotkey = QLineEdit()
        self.stop_hotkey = QLineEdit()
        self.pause_record_hotkey = QLineEdit()
        self.emergency_hotkey = QLineEdit()
        self.pause_play_hotkey = QLineEdit()
        self.emergency_hotkey.textChanged.connect(self.playback_emergency_hotkey.setText)
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
        self.export_dir.setPlaceholderText(str(default_export_directory()))
        self.python_path.setPlaceholderText(f"Current Python: {sys.executable}")
        self.pyinstaller_path.setPlaceholderText("Leave blank to run Python with -m PyInstaller")
        self.exe_options.setPlaceholderText("--windowed --clean")
        self.export_dir.setToolTip("Folder offered first when exporting Python scripts or Windows EXE files.")
        self.python_path.setToolTip("Optional Python executable used by generated batch files and PyInstaller builds.")
        self.pyinstaller_path.setToolTip("Optional pyinstaller.exe path. Leave blank to run the selected Python with -m PyInstaller.")
        self.exe_options.setToolTip("Optional extra PyInstaller switches, split like a command line.")
        tabs.addTab(self._form_tab(
            [
                ("Default export directory", self._path_row(self.export_dir, "Browse...", self._browse_export_dir)),
                ("Python interpreter path", self._path_row(self.python_path, "Browse...", self._browse_python_path)),
                ("PyInstaller executable path", self._path_row(self.pyinstaller_path, "Browse...", self._browse_pyinstaller_path)),
                ("Default .exe options", self.exe_options),
            ],
            "Exports write a standalone Python script plus runtime files. Windows EXE export first creates that script, then runs PyInstaller. Leave Python and PyInstaller paths blank to use the app's current Python environment.",
        ), "Export")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load()

    def _form_tab(self, rows: list[tuple[str, QWidget]], help_text: str | None = None) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        form = QFormLayout()
        layout.addLayout(form)
        for label, widget in rows:
            form.addRow(label, widget)
        if help_text:
            help_label = QLabel(help_text)
            help_label.setWordWrap(True)
            help_label.setObjectName("settingsHelpText")
            layout.addWidget(help_label)
        layout.addStretch(1)
        return tab

    def _path_row(self, edit: QLineEdit, button_text: str, callback) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit, 1)
        button = QPushButton(button_text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return row

    def _browse_export_dir(self) -> None:
        start = self.export_dir.text().strip() or str(default_export_directory())
        path = QFileDialog.getExistingDirectory(self, "Default Export Directory", start)
        if path:
            self.export_dir.setText(path)

    def _browse_python_path(self) -> None:
        start = self.python_path.text().strip() or str(default_export_directory())
        path, _ = QFileDialog.getOpenFileName(self, "Python Interpreter", start, "Executables (*.exe);;All files (*.*)")
        if path:
            self.python_path.setText(path)

    def _browse_pyinstaller_path(self) -> None:
        start = self.pyinstaller_path.text().strip() or str(default_export_directory())
        path, _ = QFileDialog.getOpenFileName(self, "PyInstaller Executable", start, "Executables (*.exe);;All files (*.*)")
        if path:
            self.pyinstaller_path.setText(path)

    def _set_combo_text(self, combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _load(self) -> None:
        appearance = load_appearance_settings(self.settings)
        self._set_combo_text(self.theme_mode, appearance.theme_mode)
        self.primary_color.setText(appearance.primary_color)
        self._set_combo_text(self.corner_shape, appearance.corner_shape)
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
        emergency_hotkey = str(self.settings.value("hotkeys/emergency_stop", DEFAULT_HOTKEYS["emergency_stop"]))
        self.emergency_hotkey.setText(emergency_hotkey)
        self.playback_emergency_hotkey.setText(emergency_hotkey)
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
            "start_recording": self.start_hotkey.text().strip(),
            "stop_recording": self.stop_hotkey.text().strip(),
            "pause_recording": self.pause_record_hotkey.text().strip(),
            "emergency_stop": self.emergency_hotkey.text().strip(),
            "pause_playback": self.pause_play_hotkey.text().strip(),
        }
        duplicates = validate_hotkey_conflicts(hotkeys)
        if duplicates:
            self.start_hotkey.setToolTip(f"Duplicate hotkey: {', '.join(duplicates)}")
            return
        primary_color = self.primary_color.text().strip()
        if not HEX_COLOR_RE.fullmatch(primary_color):
            self.primary_color.setToolTip("Use a hex color like #D0BCFF.")
            self.primary_color.setFocus()
            return
        self.settings.setValue("appearance/theme", self.theme_mode.currentText())
        self.settings.setValue("appearance/primary_color", primary_color.upper())
        self.settings.setValue("appearance/corner_shape", self.corner_shape.currentText())
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
