from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType
from macro_recorder_plus.recorder.event_normalizer import EventNormalizer


def test_event_normalizer_emits_hotkey_action():
    normalizer = EventNormalizer()
    normalizer.reset(10.0)

    actions = normalizer.add_hotkey(["ctrl", "v"], 10.25)

    assert len(actions) == 1
    assert actions[0].type == ActionType.HOTKEY
    assert actions[0].params["keys"] == ["ctrl", "v"]
