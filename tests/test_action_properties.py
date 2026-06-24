from __future__ import annotations

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
