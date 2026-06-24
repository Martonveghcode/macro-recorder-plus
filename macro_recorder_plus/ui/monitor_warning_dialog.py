from __future__ import annotations

import json

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QPlainTextEdit, QVBoxLayout

from macro_recorder_plus.models.environment import RecordedEnvironment


class MonitorWarningDialog(QDialog):
    def __init__(self, recorded: RecordedEnvironment, current: RecordedEnvironment, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Display Layout Check")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["exact", "scaled"])
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(
            json.dumps({"recorded": recorded.to_dict(), "current": current.to_dict()}, indent=2, sort_keys=True)
        )
        form.addRow("Coordinate mode", self.mode_combo)
        form.addRow("Layouts", self.details)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def coordinate_mode(self) -> str:
        return self.mode_combo.currentText()
