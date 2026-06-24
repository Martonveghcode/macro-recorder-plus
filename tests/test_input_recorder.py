from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.environment import MonitorInfo, Rect
from macro_recorder_plus.recorder.input_recorder import InputRecorder


def test_input_recorder_annotates_mouse_action_monitor(qtbot):
    recorder = InputRecorder()
    recorder._monitors = [
        MonitorInfo(
            identifier="DISPLAY1",
            bounds=Rect(0, 0, 100, 100),
            work_area=Rect(0, 0, 100, 100),
            primary=True,
        )
    ]
    action = MacroAction(type=ActionType.MOUSE_BUTTON, params={"x": 10, "y": 20, "button": "left", "phase": "click"})

    recorder._annotate_monitor(action)

    assert action.params["monitor"] == "DISPLAY1"
