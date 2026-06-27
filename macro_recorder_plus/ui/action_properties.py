from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.models.actions import ACTION_LABELS, DEFAULT_PARAMS, ActionType, MacroAction


FIELD_HELP: dict[str, tuple[str, str]] = {
    "type": ("Chooses the kind of action this macro row will perform.", "Open File opens a PDF with its default app."),
    "enabled": ("Controls whether playback runs this action or skips it.", "Turn this off to test a macro without running a risky click."),
    "label": ("Gives the action a friendly name shown in the table.", "Use Login document for a file-opening step."),
    "delay": ("Waits this many seconds before the action starts.", "0.500 waits half a second after the previous step."),
    "duration": ("Stores how long timed actions should last.", "A mouse move duration of 1.000 moves over one second."),
    "wait.seconds": ("Pauses playback for the entered number of seconds.", "2.000 waits two seconds."),
    "open_url.url": ("Opens this web address in the default browser.", "https://example.com"),
    "open_file.file_path": ("Opens this file with the default Windows app for its type.", r"C:\Users\marto\Documents\notes.txt"),
    "open_file.target_monitor": ("Moves the opened file window to this monitor when Windows exposes a matching window.", "Monitor 2"),
    "open_file.auto_focus": ("Brings the opened file window to the foreground after it appears.", "Enable it before typing into the opened document."),
    "launch_program.executable": ("Starts this program or executable file.", r"C:\Windows\System32\notepad.exe"),
    "launch_program.arguments": ("Passes extra command-line values to the program.", r'"C:\Users\marto\Documents\notes.txt"'),
    "launch_program.working_directory": ("Runs the program as if it was started from this folder.", r"C:\Users\marto\Documents"),
    "launch_program.target_monitor": ("Moves the launched program window to this monitor when Windows exposes a matching window.", "Primary"),
    "launch_program.auto_focus": ("Brings the launched program window to the foreground after it appears.", "Enable it when the next macro step types into that app."),
    "launch_program.wait_for_startup": ("Records whether the macro should wait briefly after starting the program.", "Enable it when the next step needs the app window to appear first."),
    "launch_program.startup_timeout": ("Limits how many seconds startup waiting may take.", "10.000 stops waiting after ten seconds."),
    "type_text.text": ("Types this exact text during playback.", "hello world"),
    "type_secret.environment_variable": (
        "Reads os.environ[NAME] from the running app or exported script, so the secret comes from Windows environment variables or the terminal environment that launched it.",
        r"$env:WEBSITE_PASSWORD='secret'; python exported_macro.py",
    ),
    "key_press.key": ("Presses or releases a single keyboard key.", "enter"),
    "key_press.phase": ("Chooses whether to press, release, or tap the key.", "press_release taps the key once."),
    "hotkey.keys": ("Runs a keyboard shortcut from keys separated by plus signs.", "ctrl+shift+t"),
    "mouse_move.start_x": ("Sets the starting horizontal screen coordinate for a mouse move.", "100"),
    "mouse_move.start_y": ("Sets the starting vertical screen coordinate for a mouse move.", "200"),
    "mouse_move.end_x": ("Sets the ending horizontal screen coordinate for a mouse move.", "800"),
    "mouse_move.end_y": ("Sets the ending vertical screen coordinate for a mouse move.", "500"),
    "mouse_button.button": ("Chooses which mouse button the action uses.", "left"),
    "mouse_button.phase": ("Chooses whether to click, press, release, or double-click.", "double_click"),
    "mouse_button.x": ("Moves the pointer to this horizontal coordinate before the mouse action.", "500"),
    "mouse_button.y": ("Moves the pointer to this vertical coordinate before the mouse action.", "300"),
    "scroll.dx": ("Scrolls horizontally by this amount.", "-1 scrolls left."),
    "scroll.dy": ("Scrolls vertically by this amount.", "-3 scrolls down."),
    "scroll.x": ("Moves the pointer to this horizontal coordinate before scrolling.", "500"),
    "scroll.y": ("Moves the pointer to this vertical coordinate before scrolling.", "300"),
    "image_click.image_path": ("Finds this image on screen before clicking or moving.", r"C:\Users\marto\Pictures\button.png"),
    "image_click.click_action": ("Chooses what to do when the image is found.", "left_click clicks the image center."),
    "image_click.confidence": ("Sets how closely the screen must match the image.", "0.850 allows a small visual difference."),
    "image_click.wait_until_found": ("Keeps checking until the image appears or the timeout is reached.", "Enable it for buttons that load slowly."),
    "image_click.timeout": ("Limits how long image searching may wait.", "0.000 waits forever until stopped."),
    "image_click.checks_per_second": ("Controls how often the screen is checked for the image.", "4.000 checks four times per second."),
    "image_click.grayscale": ("Matches images without relying on color.", "Enable it when dark mode changes button colors."),
    "image_click.on_not_found": ("Chooses whether playback errors or skips when the image is missing.", "skip continues to the next action."),
    "image_click.region_x": ("Limits image searching to a region starting at this horizontal coordinate.", "0 starts at the left edge."),
    "image_click.region_y": ("Limits image searching to a region starting at this vertical coordinate.", "0 starts at the top edge."),
    "image_click.region_width": ("Limits image searching to this region width.", "800 searches an 800-pixel-wide area."),
    "image_click.region_height": ("Limits image searching to this region height.", "600 searches a 600-pixel-tall area."),
    "comment.text": ("Stores a note for humans and does nothing during playback.", "Remember to log in first."),
}


MONITOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("Default", "default"),
    ("Primary", "primary"),
    ("Monitor 1", "1"),
    ("Monitor 2", "2"),
    ("Monitor 3", "3"),
    ("Monitor 4", "4"),
)


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

        self._add_form_row(form, "Type", self.type_combo, "type")
        self._add_form_row(form, "Enabled", self.enabled_check, "enabled")
        self._add_form_row(form, "Label", self.label_edit, "label")
        self._add_form_row(form, "Delay", self.delay_spin, "delay")
        self._add_form_row(form, "Duration", self.duration_spin, "duration")
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
                self._add_double("seconds", "Seconds", float(params.get("seconds", 1.0)), 0, 3600, "wait.seconds")
            case ActionType.OPEN_URL:
                self._add_line("url", "URL", str(params.get("url", "")), "open_url.url")
            case ActionType.OPEN_FILE:
                self._add_file(
                    "file_path",
                    "File",
                    str(params.get("file_path", "")),
                    dialog_title="Choose File to Open",
                    file_filter="Documents (*.txt *.pdf *.doc *.docx *.rtf);;All files (*.*)",
                    help_key="open_file.file_path",
                )
                self._add_monitor_combo("target_monitor", "Monitor", str(params.get("target_monitor", "default")), "open_file.target_monitor")
                self._add_bool("auto_focus", "Auto focus", bool(params.get("auto_focus", False)), "open_file.auto_focus")
            case ActionType.LAUNCH_PROGRAM:
                self._add_file(
                    "executable",
                    "Executable",
                    str(params.get("executable", "")),
                    dialog_title="Choose Executable",
                    file_filter="Programs (*.exe *.bat *.cmd *.com);;All files (*.*)",
                    help_key="launch_program.executable",
                )
                self._add_line("arguments", "Arguments", str(params.get("arguments", "")), "launch_program.arguments")
                self._add_directory(
                    "working_directory",
                    "Working directory",
                    str(params.get("working_directory", "")),
                    "launch_program.working_directory",
                )
                self._add_monitor_combo("target_monitor", "Monitor", str(params.get("target_monitor", "default")), "launch_program.target_monitor")
                self._add_bool("auto_focus", "Auto focus", bool(params.get("auto_focus", False)), "launch_program.auto_focus")
                self._add_bool("wait_for_startup", "Wait for startup", bool(params.get("wait_for_startup", False)), "launch_program.wait_for_startup")
                self._add_double("startup_timeout", "Startup timeout", float(params.get("startup_timeout", 10.0)), 0, 300, "launch_program.startup_timeout")
            case ActionType.TYPE_TEXT:
                self._add_plain("text", "Text", str(params.get("text", "")), "type_text.text")
            case ActionType.TYPE_SECRET:
                self._add_line("environment_variable", "Environment variable", str(params.get("environment_variable", "")), "type_secret.environment_variable")
            case ActionType.KEY_PRESS:
                self._add_line("key", "Key", str(params.get("key", "enter")), "key_press.key")
                self._add_combo("phase", "Phase", ["press_release", "press", "release"], str(params.get("phase", "press_release")), "key_press.phase")
            case ActionType.HOTKEY:
                keys = params.get("keys", [])
                self._add_line("keys", "Keys", "+".join(keys) if isinstance(keys, list) else str(keys), "hotkey.keys")
            case ActionType.MOUSE_MOVE:
                start = params.get("start", [0, 0])
                end = params.get("end", [0, 0])
                self._add_int("start_x", "Start X", int(start[0]), -100000, 100000, "mouse_move.start_x")
                self._add_int("start_y", "Start Y", int(start[1]), -100000, 100000, "mouse_move.start_y")
                self._add_int("end_x", "End X", int(end[0]), -100000, 100000, "mouse_move.end_x")
                self._add_int("end_y", "End Y", int(end[1]), -100000, 100000, "mouse_move.end_y")
            case ActionType.MOUSE_BUTTON:
                self._add_combo("button", "Button", ["left", "right", "middle"], str(params.get("button", "left")), "mouse_button.button")
                self._add_combo("phase", "Phase", ["click", "press", "release", "double_click"], str(params.get("phase", "click")), "mouse_button.phase")
                self._add_int("x", "X", int(params.get("x", 0)), -100000, 100000, "mouse_button.x")
                self._add_int("y", "Y", int(params.get("y", 0)), -100000, 100000, "mouse_button.y")
            case ActionType.SCROLL:
                self._add_int("dx", "Delta X", int(params.get("dx", 0)), -1000, 1000, "scroll.dx")
                self._add_int("dy", "Delta Y", int(params.get("dy", -1)), -1000, 1000, "scroll.dy")
                self._add_int("x", "X", int(params.get("x", 0)), -100000, 100000, "scroll.x")
                self._add_int("y", "Y", int(params.get("y", 0)), -100000, 100000, "scroll.y")
            case ActionType.IMAGE_CLICK:
                self._add_file(
                    "image_path",
                    "Image",
                    str(params.get("image_path", "")),
                    dialog_title="Choose Image",
                    file_filter="Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*.*)",
                    help_key="image_click.image_path",
                )
                self._add_combo(
                    "click_action",
                    "Action",
                    ["left_click", "right_click", "middle_click", "double_click", "move_only"],
                    str(params.get("click_action", "left_click")),
                    "image_click.click_action",
                )
                self._add_double("confidence", "Min confidence", float(params.get("confidence", 0.85)), 0.1, 1.0, "image_click.confidence")
                self._add_bool("wait_until_found", "Wait until found", bool(params.get("wait_until_found", True)), "image_click.wait_until_found")
                self._add_double("timeout", "Max wait seconds (0 = forever)", float(params.get("timeout", 5.0)), 0.0, 3600.0, "image_click.timeout")
                self._add_double("checks_per_second", "Checks per second", _checks_per_second_from_params(params), 0.1, 60.0, "image_click.checks_per_second")
                self._add_bool("grayscale", "Grayscale match", bool(params.get("grayscale", True)), "image_click.grayscale")
                self._add_combo("on_not_found", "If not found", ["error", "skip"], str(params.get("on_not_found", "error")), "image_click.on_not_found")
                self._add_int("region_x", "Region X", int(params.get("region_x", 0)), -100000, 100000, "image_click.region_x")
                self._add_int("region_y", "Region Y", int(params.get("region_y", 0)), -100000, 100000, "image_click.region_y")
                self._add_int("region_width", "Region width", int(params.get("region_width", 0)), 0, 100000, "image_click.region_width")
                self._add_int("region_height", "Region height", int(params.get("region_height", 0)), 0, 100000, "image_click.region_height")
            case ActionType.COMMENT:
                self._add_plain("text", "Text", str(params.get("text", "")), "comment.text")

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
            case ActionType.OPEN_FILE:
                params["file_path"] = self.param_widgets["file_path"].text()
                params["target_monitor"] = str(self.param_widgets["target_monitor"].currentData() or "default")
                params["auto_focus"] = self.param_widgets["auto_focus"].isChecked()
            case ActionType.LAUNCH_PROGRAM:
                for key in ["executable", "arguments", "working_directory"]:
                    params[key] = self.param_widgets[key].text()
                params["target_monitor"] = str(self.param_widgets["target_monitor"].currentData() or "default")
                params["auto_focus"] = self.param_widgets["auto_focus"].isChecked()
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
                params["wait_until_found"] = self.param_widgets["wait_until_found"].isChecked()
                params["timeout"] = self.param_widgets["timeout"].value()
                params["checks_per_second"] = self.param_widgets["checks_per_second"].value()
                params["poll_interval"] = 1.0 / max(0.1, params["checks_per_second"])
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

    def _add_form_row(self, form: QFormLayout, label: str, widget: QWidget, help_key: str) -> None:
        form.addRow(label, self._with_info_button(label, widget, help_key))

    def _add_param_row(self, label: str, widget: QWidget, help_key: str) -> None:
        self.params_form.addRow(label, self._with_info_button(label, widget, help_key))

    def _with_info_button(self, label: str, widget: QWidget, help_key: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        if isinstance(widget, QCheckBox):
            layout.addWidget(widget)
            layout.addStretch(1)
        else:
            layout.addWidget(widget, 1)
        layout.addWidget(self._info_button(label, help_key), 0, Qt.AlignTop)
        return row

    def _info_button(self, label: str, help_key: str) -> QToolButton:
        description, example = FIELD_HELP.get(
            help_key,
            (f"Sets the {label.lower()} value for this action.", f"Enter a value for {label.lower()}."),
        )
        message = f"{description}\n\nExample: {example}"
        button = QToolButton(self)
        button.setText("i")
        button.setAutoRaise(True)
        button.setFixedSize(22, 22)
        button.setCursor(Qt.PointingHandCursor)
        button.setAccessibleName(f"{label} info")
        button.setToolTip(message.replace("\n\n", " "))
        button.clicked.connect(lambda _checked=False, title=label, body=message: QMessageBox.information(self, title, body))
        return button

    def _add_line(self, key: str, label: str, value: str, help_key: str) -> None:
        widget = QLineEdit(value)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _add_file(
        self,
        key: str,
        label: str,
        value: str,
        *,
        dialog_title: str,
        file_filter: str,
        help_key: str,
    ) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = QLineEdit(value)
        button = QPushButton("Browse")
        button.setToolTip(f"Browse for {label.lower()}")
        button.clicked.connect(
            lambda _checked=False, target=edit, title=dialog_title, filters=file_filter: self._browse_file(target, title, filters)
        )
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self.param_widgets[key] = edit
        self._add_param_row(label, row, help_key)

    def _add_directory(self, key: str, label: str, value: str, help_key: str) -> None:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        edit = QLineEdit(value)
        button = QPushButton("Browse")
        button.setToolTip(f"Browse for {label.lower()}")
        button.clicked.connect(lambda _checked=False, target=edit: self._browse_directory(target))
        layout.addWidget(edit, 1)
        layout.addWidget(button)
        self.param_widgets[key] = edit
        self._add_param_row(label, row, help_key)

    def _add_plain(self, key: str, label: str, value: str, help_key: str) -> None:
        widget = QPlainTextEdit(value)
        widget.setMinimumHeight(120)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _add_bool(self, key: str, label: str, value: bool, help_key: str) -> None:
        widget = QCheckBox()
        widget.setChecked(value)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _add_combo(self, key: str, label: str, choices: list[str], value: str, help_key: str) -> None:
        widget = QComboBox()
        widget.addItems(choices)
        index = widget.findText(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _add_monitor_combo(self, key: str, label: str, value: str, help_key: str) -> None:
        widget = QComboBox()
        for display, data in MONITOR_CHOICES:
            widget.addItem(display, data)
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _add_int(self, key: str, label: str, value: int, minimum: int, maximum: int, help_key: str) -> None:
        widget = QSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)

    def _browse_file(self, target: QLineEdit, title: str, file_filter: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, title, target.text(), file_filter)
        if path:
            target.setText(path)

    def _browse_directory(self, target: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Working Directory", target.text())
        if path:
            target.setText(path)

    def _add_double(self, key: str, label: str, value: float, minimum: float, maximum: float, help_key: str) -> None:
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(3)
        widget.setSingleStep(0.1)
        widget.setValue(value)
        self.param_widgets[key] = widget
        self._add_param_row(label, widget, help_key)


def _checks_per_second_from_params(params: dict) -> float:
    if "checks_per_second" in params:
        return max(0.1, float(params.get("checks_per_second") or 4.0))
    poll_interval = max(0.05, float(params.get("poll_interval", 0.25) or 0.25))
    return max(0.1, 1.0 / poll_interval)
