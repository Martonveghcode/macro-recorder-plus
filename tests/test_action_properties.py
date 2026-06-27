from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton

from macro_recorder_plus.models.actions import ActionType, create_action
from macro_recorder_plus.ui.action_properties import ActionProperties


def test_action_properties_emits_typed_wait_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.WAIT)
    widget.set_action(0, action)

    widget.param_widgets["seconds"].setValue(2.25)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.params["seconds"] == 2.25
    assert updated.duration == 2.25


def test_action_properties_emits_image_wait_frequency_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.IMAGE_CLICK)
    widget.set_action(0, action)

    widget.param_widgets["wait_until_found"].setChecked(True)
    widget.param_widgets["timeout"].setValue(0.0)
    widget.param_widgets["checks_per_second"].setValue(8.0)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.params["wait_until_found"] is True
    assert updated.params["timeout"] == 0.0
    assert updated.params["checks_per_second"] == 8.0
    assert updated.params["poll_interval"] == 0.125


def test_action_properties_emits_open_file_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.OPEN_FILE)
    widget.set_action(0, action)

    widget.param_widgets["file_path"].setText(r"C:\Users\marto\Documents\notes.pdf")
    widget.param_widgets["target_monitor"].setCurrentIndex(widget.param_widgets["target_monitor"].findData("2"))
    widget.param_widgets["auto_focus"].setChecked(True)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.type == ActionType.OPEN_FILE
    assert updated.params["file_path"] == r"C:\Users\marto\Documents\notes.pdf"
    assert updated.params["target_monitor"] == "2"
    assert updated.params["auto_focus"] is True


def test_action_properties_emits_launch_program_window_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.LAUNCH_PROGRAM)
    widget.set_action(0, action)

    widget.param_widgets["executable"].setText(r"C:\Windows\System32\notepad.exe")
    widget.param_widgets["target_monitor"].setCurrentIndex(widget.param_widgets["target_monitor"].findData("primary"))
    widget.param_widgets["auto_focus"].setChecked(True)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.type == ActionType.LAUNCH_PROGRAM
    assert updated.params["executable"] == r"C:\Windows\System32\notepad.exe"
    assert updated.params["target_monitor"] == "primary"
    assert updated.params["auto_focus"] is True


def test_action_properties_info_button_shows_field_help(qtbot, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "macro_recorder_plus.ui.action_properties.QMessageBox.information",
        lambda parent, title, body: messages.append((title, body)),
    )
    widget = ActionProperties()
    qtbot.addWidget(widget)
    widget.set_action(0, create_action(ActionType.OPEN_FILE))

    buttons = widget.findChildren(QToolButton)
    file_info = next(button for button in buttons if button.accessibleName() == "File info")
    qtbot.mouseClick(file_info, Qt.LeftButton)

    assert messages
    assert messages[0][0] == "File"
    assert "default Windows app" in messages[0][1]
    assert "Example:" in messages[0][1]


def test_action_properties_secret_help_explains_environment_source(qtbot, monkeypatch):
    messages = []
    monkeypatch.setattr(
        "macro_recorder_plus.ui.action_properties.QMessageBox.information",
        lambda parent, title, body: messages.append((title, body)),
    )
    widget = ActionProperties()
    qtbot.addWidget(widget)
    widget.set_action(0, create_action(ActionType.TYPE_SECRET))

    secret_info = next(button for button in widget.findChildren(QToolButton) if button.accessibleName() == "Environment variable info")
    qtbot.mouseClick(secret_info, Qt.LeftButton)

    assert messages
    assert messages[0][0] == "Environment variable"
    assert "os.environ" in messages[0][1]
    assert "Windows environment variables" in messages[0][1]
