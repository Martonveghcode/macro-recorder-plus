from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from macro_recorder_plus.platform.windows_hotkeys import DEFAULT_HOTKEYS, validate_hotkey_conflicts
from macro_recorder_plus.recorder.input_recorder import RecordingOptions


class RecordingDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recording Setup")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.countdown_spin = QSpinBox()
        self.countdown_spin.setRange(0, 60)
        self.countdown_spin.setValue(5)
        self.mouse_check = QCheckBox()
        self.mouse_check.setChecked(True)
        self.keyboard_check = QCheckBox()
        self.keyboard_check.setChecked(True)
        self.scroll_check = QCheckBox()
        self.scroll_check.setChecked(True)
        self.hide_check = QCheckBox()
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(5, 240)
        self.sample_spin.setValue(60)
        self.tolerance_spin = QSpinBox()
        self.tolerance_spin.setRange(0, 30)
        self.tolerance_spin.setValue(2)
        self.stop_hotkey = QLineEdit(DEFAULT_HOTKEYS["stop_recording"])
        self.pause_hotkey = QLineEdit(DEFAULT_HOTKEYS["pause_recording"])

        form.addRow("Countdown seconds", self.countdown_spin)
        form.addRow("Record mouse movement", self.mouse_check)
        form.addRow("Record keyboard", self.keyboard_check)
        form.addRow("Record scrolling", self.scroll_check)
        form.addRow("Hide during recording", self.hide_check)
        form.addRow("Mouse sample rate", self.sample_spin)
        form.addRow("Path tolerance", self.tolerance_spin)
        form.addRow("Stop hotkey", self.stop_hotkey)
        form.addRow("Pause hotkey", self.pause_hotkey)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        duplicates = validate_hotkey_conflicts(
            {"stop_recording": self.stop_hotkey.text(), "pause_recording": self.pause_hotkey.text()}
        )
        if duplicates:
            self.stop_hotkey.setToolTip(f"Duplicate hotkey: {', '.join(duplicates)}")
            return
        super().accept()

    def options(self) -> RecordingOptions:
        return RecordingOptions(
            record_mouse_movement=self.mouse_check.isChecked(),
            record_keyboard=self.keyboard_check.isChecked(),
            record_scroll=self.scroll_check.isChecked(),
            mouse_sample_hz=self.sample_spin.value(),
            simplification_tolerance=float(self.tolerance_spin.value()),
            ignored_keys={"f8", "f9", "f7", "f10", "f6"},
        )
