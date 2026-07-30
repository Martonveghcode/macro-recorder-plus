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

    widget.loop_spin.setValue(4)
    widget.param_widgets["seconds"].setValue(2.25)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.loop_count == 4
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
    widget.param_widgets["verification_attempts"].setValue(3)
    widget.param_widgets["stable_match_pixels"].setValue(12)
    widget.param_widgets["scale_tolerance"].setValue(0.08)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.params["wait_until_found"] is True
    assert updated.params["timeout"] == 0.0
    assert updated.params["checks_per_second"] == 8.0
    assert updated.params["poll_interval"] == 0.125
    assert updated.params["verification_attempts"] == 3
    assert updated.params["stable_match_pixels"] == 12
    assert updated.params["scale_tolerance"] == 0.08


def test_action_properties_region_picker_updates_region_fields(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    widget.set_action(0, create_action(ActionType.IMAGE_CLICK))

    widget._set_image_region(100, 200, 320, 180)

    assert widget.param_widgets["region_x"].value() == 100
    assert widget.param_widgets["region_y"].value() == 200
    assert widget.param_widgets["region_width"].value() == 320
    assert widget.param_widgets["region_height"].value() == 180



def test_action_properties_emits_image_custom_movement_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.IMAGE_CLICK)
    widget.set_action(0, action)

    widget.param_widgets["click_action"].setCurrentIndex(widget.param_widgets["click_action"].findText("custom_movement"))
    widget.param_widgets["natural_movement"].setChecked(True)
    widget.param_widgets["movement_start_mode"].setCurrentIndex(widget.param_widgets["movement_start_mode"].findData("screen"))
    widget.param_widgets["movement_start_x"].setValue(500)
    widget.param_widgets["movement_start_y"].setValue(300)
    widget.param_widgets["movement_start_radius"].setValue(100)
    widget.param_widgets["click_offset_x"].setValue(4)
    widget.param_widgets["click_offset_y"].setValue(-2)
    widget.param_widgets["click_radius"].setValue(5)
    widget.param_widgets["path_variance"].setValue(9.0)
    widget.param_widgets["movement_duration"].setValue(0.75)
    widget.param_widgets["movement_button"].setCurrentIndex(widget.param_widgets["movement_button"].findText("right"))
    widget.param_widgets["movement_button_action"].setCurrentIndex(widget.param_widgets["movement_button_action"].findText("hold_during_move"))

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.params["click_action"] == "custom_movement"
    assert updated.params["natural_movement"] is True
    assert updated.params["movement_start_mode"] == "screen"
    assert updated.params["movement_start_center"] == [500, 300]
    assert updated.params["movement_start_radius"] == 100
    assert updated.params["click_offset"] == [4, -2]
    assert updated.params["click_radius"] == 5
    assert updated.params["path_variance"] == 9.0
    assert updated.params["movement_duration"] == 0.75
    assert updated.params["movement_button"] == "right"
    assert updated.params["movement_button_action"] == "hold_during_move"


def test_start_circle_picker_updates_center_and_mode(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    widget.set_action(0, create_action(ActionType.IMAGE_CLICK))

    widget._set_start_circle_center(725, 410)

    assert widget.param_widgets["movement_start_x"].value() == 725
    assert widget.param_widgets["movement_start_y"].value() == 410
    assert widget.param_widgets["movement_start_mode"].currentData() == "screen"


def test_changing_an_action_to_image_enables_new_circle_movement(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    widget.set_action(0, create_action(ActionType.COMMENT))

    widget.type_combo.setCurrentIndex(widget.type_combo.findData(ActionType.IMAGE_CLICK.value))

    assert widget.param_widgets["natural_movement"].isChecked()


def test_action_properties_emits_if_image_result_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.IF_CONDITION)
    widget.set_action(0, action)

    widget.param_widgets["image_found_action"].setValue(5)
    widget.param_widgets["image_not_found_action"].setValue(0)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.type == ActionType.IF_CONDITION
    assert updated.params["image_found_action"] == 5
    assert updated.params["image_not_found_action"] == 0


def test_action_properties_emits_open_file_params(qtbot):
    widget = ActionProperties()
    qtbot.addWidget(widget)
    action = create_action(ActionType.OPEN_FILE)
    widget.set_action(0, action)

    widget.param_widgets["file_path"].setText(r"C:\TestData\notes.pdf")
    widget.param_widgets["target_monitor"].setCurrentIndex(widget.param_widgets["target_monitor"].findData("2"))
    widget.param_widgets["auto_focus"].setChecked(True)

    with qtbot.waitSignal(widget.actionChanged, timeout=1000) as blocker:
        widget.apply_button.click()

    row, updated = blocker.args
    assert row == 0
    assert updated.type == ActionType.OPEN_FILE
    assert updated.params["file_path"] == r"C:\TestData\notes.pdf"
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
