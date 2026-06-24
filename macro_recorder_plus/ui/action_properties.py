from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.models.actions import ACTION_LABELS, DEFAULT_PARAMS, ActionType, MacroAction


class ActionProperties(QWidget):
    actionChanged = Signal(int, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = -1
        self._action: MacroAction | None = None
        self._updating = False
        self.param_widgets: dict[str, QWidget] = {}

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
        self.params_widget = QWidget()
        self.params_form = QFormLayout(self.params_widget)
        self.apply_button = QPushButton("Apply")

        form.addRow("Type", self.type_combo)
        form.addRow("Enabled", self.enabled_check)
        form.addRow("Label", self.label_edit)
        form.addRow("Delay", self.delay_spin)
        form.addRow("Duration", self.duration_spin)
        form.addRow("Parameters", self.params_widget)
        form.addRow("", self.apply_button)
        layout.addWidget(self.form_widget)
        layout.addStretch(1)

        self.form_widget.hide()
        self.type_combo.currentIndexChanged.connect(self._type_changed)
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
        self._build_param_form(action.type, action.params)
        self._updating = False

    def _emit_change(self) -> None:
        if self._action is None or self._row < 0 or self._updating:
            return
        action_type = ActionType(self.type_combo.currentData())
        params = self._read_params(action_type)

        action = self._action.with_changes(
            type=action_type,
            enabled=self.enabled_check.isChecked(),
            label=self.label_edit.text(),
            delay=self.delay_spin.value(),
            duration=self.duration_spin.value(),
            params=params,
        )
        self._action = action.clone(keep_id=True)
        self.actionChanged.emit(self._row, action)

    def _type_changed(self) -> None:
        if self._updating or self._action is None:
            return
        action_type = ActionType(self.type_combo.currentData())
        self._build_param_form(action_type, dict(DEFAULT_PARAMS[action_type]))

    def _build_param_form(self, action_type: ActionType, params: dict) -> None:
        self._clear_param_form()
        match action_type:
            case ActionType.WAIT:
                self._add_double("seconds", "Seconds", float(params.get("seconds", 1.0)), 0, 3600)
            case ActionType.OPEN_URL:
                self._add_line("url", "URL", str(params.get("url", "")))
            case ActionType.LAUNCH_PROGRAM:
                self._add_line("executable", "Executable", str(params.get("executable", "")))
                self._add_line("arguments", "Arguments", str(params.get("arguments", "")))
                self._add_line("working_directory", "Working directory", str(params.get("working_directory", "")))
                self._add_bool("wait_for_startup", "Wait for startup", bool(params.get("wait_for_startup", False)))
                self._add_double("startup_timeout", "Startup timeout", float(params.get("startup_timeout", 10.0)), 0, 300)
            case ActionType.TYPE_TEXT:
                self._add_plain("text", "Text", str(params.get("text", "")))
            case ActionType.TYPE_SECRET:
                self._add_line("environment_variable", "Environment variable", str(params.get("environment_variable", "")))
            case ActionType.KEY_PRESS:
                self._add_line("key", "Key", str(params.get("key", "enter")))
                self._add_combo("phase", "Phase", ["press_release", "press", "release"], str(params.get("phase", "press_release")))
            case ActionType.HOTKEY:
                keys = params.get("keys", [])
                self._add_line("keys", "Keys", "+".join(keys) if isinstance(keys, list) else str(keys))
            case ActionType.MOUSE_MOVE:
                start = params.get("start", [0, 0])
                end = params.get("end", [0, 0])
                self._add_int("start_x", "Start X", int(start[0]), -100000, 100000)
                self._add_int("start_y", "Start Y", int(start[1]), -100000, 100000)
                self._add_int("end_x", "End X", int(end[0]), -100000, 100000)
                self._add_int("end_y", "End Y", int(end[1]), -100000, 100000)
            case ActionType.MOUSE_BUTTON:
                self._add_combo("button", "Button", ["left", "right", "middle"], str(params.get("button", "left")))
                self._add_combo("phase", "Phase", ["click", "press", "release", "double_click"], str(params.get("phase", "click")))
                self._add_int("x", "X", int(params.get("x", 0)), -100000, 100000)
                self._add_int("y", "Y", int(params.get("y", 0)), -100000, 100000)
            case ActionType.SCROLL:
                self._add_int("dx", "Delta X", int(params.get("dx", 0)), -1000, 1000)
                self._add_int("dy", "Delta Y", int(params.get("dy", -1)), -1000, 1000)
                self._add_int("x", "X", int(params.get("x", 0)), -100000, 100000)
                self._add_int("y", "Y", int(params.get("y", 0)), -100000, 100000)
            case ActionType.IMAGE_CLICK:
                self._add_file("image_path", "Image", str(params.get("image_path", "")))
                self._add_combo(
                    "click_action",
                    "Action",
                    ["left_click", "right_click", "middle_click", "double_click", "move_only"],
                    str(params.get("click_action", "left_click")),
                )
                self._add_double("confidence", "Min confidence", float(params.get("confidence", 0.85)), 0.1, 1.0)
                self._add_double("timeout", "Timeout seconds", float(params.get("timeout", 5.0)), 0.0, 300.0)
                self._add_double("poll_interval", "Poll interval", float(params.get("poll_interval", 0.25)), 0.05, 10.0)
                self._add_bool("grayscale", "Grayscale match", bool(params.get("grayscale", True)))
                self._add_combo("on_not_found", "If not found", ["error", "skip"], str(params.get("on_not_found", "error")))
                self._add_int("region_x", "Region X", int(params.get("region_x", 0)), -100000, 100000)
                self._add_int("region_y", "Region Y", int(params.get("region_y", 0)), -100000, 100000)
                self._add_int("region_width", "Region width", int(params.get("region_width", 0)), 0, 100000)
                self._add_int("region_height", "Region height", int(params.get("region_height", 0)), 0, 100000)
            case ActionType.COMMENT:
                self._add_plain("text", "Text", str(params.get("text", "")))

    def _read_params(self, action_type: ActionType) -> dict:
        params = dict(DEFAULT_PARAMS[action_type])
        if self._action is not None and self._action.type == action_type:
            params.update(self._action.params)
        match action_type:
            case ActionType.WAIT:
                params["seconds"] = self.param_widgets["seconds"].value()
                self.duration_spin.setValue(params["seconds"])
            case ActionType.OPEN_URL:
                params["url"] = self.param_widgets["url"].text()
            case ActionType.LAUNCH_PROGRAM:
                for key in ["executable", "arguments", "working_directory"]:
                    params[key] = self.param_widgets[key].text()
                params["wait_for_startup"] = self.param_widgets["wait_for_startup"].isChecked()
                params["startup_timeout"] = self.param_widgets["startup_timeout"].value()
            case ActionType.TYPE_TEXT:
                params["text"] = self.param_widgets["text"].toPlainText()
            case ActionType.TYPE_SECRET:
                params["environment_variable"] = self.param_widgets["environment_variable"].text()
            case ActionType.KEY_PRESS:
                params["key"] = self.param_widgets["key"].text()
                params["phase"] = self.param_widgets["phase"].currentText()
            case ActionType.HOTKEY:
                params["keys"] = [part.strip().lower() for part in self.param_widgets["keys"].text().replace(",", "+").split("+") if part.strip()]
            case ActionType.MOUSE_MOVE:
                params["start"] = [self.param_widgets["start_x"].value(), self.param_widgets["start_y"].value()]
                params["end"] = [self.param_widgets["end_x"].value(), self.param_widgets["end_y"].value()]
            case ActionType.MOUSE_BUTTON:
                params["button"] = self.param_widgets["button"].currentText()
                params["phase"] = self.param_widgets["phase"].currentText()
                params["x"] = self.param_widgets["x"].value()
                params["y"] = self.param_widgets["y"].value()
            case ActionType.SCROLL:
                for key in ["dx", "dy", "x", "y"]:
                    params[key] = self.param_widgets[key].value()
            case ActionType.IMAGE_CLICK:
                params["image_path"] = self.param_widgets["image_path"].text()
                params["click_action"] = self.param_widgets["click_action"].currentText()
                params["confidence"] = self.param_widgets["confidence"].value()
                params["timeout"] = self.param_widgets["timeout"].value()
                params["poll_interval"] = self.param_widgets["poll_interval"].value()
                params["grayscale"] = self.param_widgets["grayscale"].isChecked()
                params["on_not_found"] = self.param_widgets["on_not_found"].currentText()
                for key in ["region_x", "region_y", "region_width", "region_height"]:
                    params[key] = self.param_widgets[key].value()
            case ActionType.COMMENT:
                params["text"] = self.param_widgets["text"].toPlainText()
        return params

    def _clear_param_form(self) -> None:
        while self.params_form.count():
            item = self.params_form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.param_widgets.clear()

    def _add_line(self, key: str, label: str, value: str) -> None:
        widget = QLineEdit(value)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)

    def _add_file(self, key: str, label: str, value: str) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(value)
        button = QPushButton("Browse")
        button.clicked.connect(lambda _checked=False, target=edit: self._browse_image(target))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self.param_widgets[key] = edit
        self.params_form.addRow(label, row)

    def _add_plain(self, key: str, label: str, value: str) -> None:
        widget = QPlainTextEdit(value)
        widget.setMinimumHeight(120)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)

    def _add_bool(self, key: str, label: str, value: bool) -> None:
        widget = QCheckBox()
        widget.setChecked(value)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)

    def _add_combo(self, key: str, label: str, choices: list[str], value: str) -> None:
        widget = QComboBox()
        widget.addItems(choices)
        index = widget.findText(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)

    def _add_int(self, key: str, label: str, value: int, minimum: int, maximum: int) -> None:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)

    def _browse_image(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Image",
            target.text(),
            "Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*.*)",
        )
        if path:
            target.setText(path)

    def _add_double(self, key: str, label: str, value: float, minimum: float, maximum: float) -> None:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setSingleStep(0.1)
        widget.setValue(value)
        self.param_widgets[key] = widget
        self.params_form.addRow(label, widget)
