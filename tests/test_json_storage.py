from __future__ import annotations

import json

import pytest

from macro_recorder_plus.models.actions import ActionType, MacroAction, create_action
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
    assert document.settings["macro_loop_delay_mode"] == "none"
    assert document.settings["macro_loop_delay_min"] == 0.0
    assert document.settings["macro_loop_delay_max"] == 0.0


def test_random_macro_loop_delay_settings_round_trip(tmp_path):
    document = MacroDocument(
        name="paced",
        settings={
            "playback_speed": 1.0,
            "coordinate_mode": "exact",
            "macro_loop_count": 3,
            "macro_loop_delay_mode": "random",
            "macro_loop_delay_min": 1.0,
            "macro_loop_delay_max": 2.0,
        },
    )

    loaded = load_macro(save_macro(document, tmp_path / "paced.mrplus.json"))

    assert loaded.settings["macro_loop_delay_mode"] == "random"
    assert loaded.settings["macro_loop_delay_min"] == 1.0
    assert loaded.settings["macro_loop_delay_max"] == 2.0


def test_existing_mouse_move_is_not_upgraded_to_humanized_playback():
    document = MacroDocument.from_dict(
        {
            "format_version": 1,
            "name": "old mouse macro",
            "actions": [
                {
                    "type": "mouse_move",
                    "duration": 1.0,
                    "params": {"start": [0, 0], "end": [100, 100], "path": []},
                }
            ],
        }
    )

    assert "humanize_playback" not in document.actions[0].params


def test_old_image_action_stays_exact_but_new_image_action_uses_circle_movement():
    document = MacroDocument.from_dict(
        {
            "format_version": 1,
            "name": "old image macro",
            "actions": [{"type": "image_click", "params": {"image_path": "button.png"}}],
        }
    )

    assert document.actions[0].params["natural_movement"] is False
    assert create_action(ActionType.IMAGE_CLICK).params["natural_movement"] is True


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
