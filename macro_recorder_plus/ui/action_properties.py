from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.models.actions import ACTION_LABELS, ActionType, MacroAction


class ActionProperties(QWidget):
    actionChanged = Signal(int, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = -1
        self._action: MacroAction | None = None
        self._updating = False

        layout = QVBoxLayout(self)
        self.empty_label = QLabel("No action selected")
        layout.addWidget(self.empty_label)

        self.form_widget = QWidget()
        form = QFormLayout(self.form_widget)
        self.type_combo = QComboBox()
        for action_type, label in ACTION_LABELS.items():
            self.type_combo.addItem(label, action_type.value)
        self.enabled_check = QCheckBox()
        self.label_edit = QLineEdit()
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0, 3600)
        self.delay_spin.setDecimals(3)
        self.delay_spin.setSingleStep(0.1)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0, 3600)
        self.duration_spin.setDecimals(3)
        self.duration_spin.setSingleStep(0.1)
        self.params_edit = QPlainTextEdit()
        self.params_edit.setMinimumHeight(180)
        self.apply_button = QPushButton("Apply")

        form.addRow("Type", self.type_combo)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Label", self.label_edit)
        form.addRow("Delay", self.delay_spin)
        form.addRow("Duration", self.duration_spin)
        form.addRow("Parameters", self.params_edit)
        form.addRow("", self.apply_button)
        layout.addWidget(self.form_widget)
        layout.addStretch(1)

        self.form_widget.hide()
        self.apply_button.clicked.connect(self._emit_change)

    def set_action(self, row: int, action: MacroAction | None) -> None:
        self._row = row
        self._action = action.clone(keep_id=True) if action else None
        self.empty_label.setVisible(action is None)
        self.form_widget.setVisible(action is not None)
        if action is None:
            return

        self._updating = True
        self.type_combo.setCurrentIndex(self.type_combo.findData(action.type.value))
        self.enabled_check.setChecked(action.enabled)
        self.label_edit.setText(action.label)
        self.delay_spin.setValue(action.delay)
        self.duration_spin.setValue(action.duration)
        self.params_edit.setPlainText(json.dumps(action.params, indent=2, sort_keys=True))
        self._updating = False

    def _emit_change(self) -> None:
        if self._action is None or self._row < 0 or self._updating:
            return
        try:
            params = json.loads(self.params_edit.toPlainText() or "{}")
            if not isinstance(params, dict):
                raise ValueError("parameters must be a JSON object")
        except Exception as exc:
            self.params_edit.setPlainText(json.dumps(self._action.params, indent=2, sort_keys=True))
            self.params_edit.setToolTip(str(exc))
            return

        action = self._action.with_changes(
            type=ActionType(self.type_combo.currentData()),
            enabled=self.enabled_check.isChecked(),
            label=self.label_edit.text(),
            delay=self.delay_spin.value(),
            duration=self.duration_spin.value(),
            params=params,
        )
        self._action = action.clone(keep_id=True)
        self.actionChanged.emit(self._row, action)
