from __future__ import annotations

import json

import pytest

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.macro import MacroDocument
from macro_recorder_plus.storage.json_store import MacroFileError, load_macro, save_macro


def test_macro_round_trip(tmp_path):
    document = MacroDocument(
        name="demo",
        settings={"playback_speed": 1.0, "coordinate_mode": "exact", "macro_loop_count": 4},
        pre_actions=[MacroAction(type=ActionType.LAUNCH_PROGRAM, params={"executable": "notepad.exe"})],
        actions=[
            MacroAction(type=ActionType.WAIT, delay=0.0, duration=1.0, params={"seconds": 1.0}),
            MacroAction(type=ActionType.HOTKEY, delay=0.2, loop_count=3, params={"keys": ["ctrl", "v"]}),
        ],
    )

    path = save_macro(document, tmp_path / "demo.mrplus.json")
    loaded = load_macro(path)

    assert loaded.name == "demo"
    assert loaded.format_version == 1
    assert [action.type for action in loaded.actions] == [ActionType.WAIT, ActionType.HOTKEY]
    assert loaded.actions[0].loop_count == 1
    assert loaded.actions[1].loop_count == 3
    assert loaded.actions[1].params["keys"] == ["ctrl", "v"]
    assert loaded.settings["macro_loop_count"] == 4
    assert [action.type for action in loaded.pre_actions] == [ActionType.LAUNCH_PROGRAM]


def test_old_macro_defaults_to_one_whole_macro_loop():
    document = MacroDocument.from_dict({"format_version": 1, "name": "old", "settings": {"playback_speed": 1.0}})

    assert document.settings["macro_loop_count"] == 1


def test_invalid_macro_file_reports_error(tmp_path):
    path = tmp_path / "broken.mrplus.json"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(MacroFileError):
        load_macro(path)


def test_saved_format_uses_actions_key(tmp_path):
    path = save_macro(MacroDocument(name="schema"), tmp_path / "schema.json")
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["format_version"] == 1
    assert "actions" in data
    assert "recorded_environment" in data
