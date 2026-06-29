from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from macro_recorder_plus.models.actions import ActionType, MacroAction, create_action
from macro_recorder_plus.models.environment import RecordedEnvironment
from macro_recorder_plus.playback import playback_worker
from macro_recorder_plus.playback.playback_worker import PlaybackWorker


def _worker(actions: list[MacroAction]) -> PlaybackWorker:
    environment = RecordedEnvironment()
    return PlaybackWorker(actions, recorded_environment=environment, current_environment_snapshot=environment)


def test_if_image_result_uses_found_target():
    actions = [
        create_action(ActionType.IMAGE_CLICK),
        MacroAction(type=ActionType.IF_CONDITION, params={"image_found_action": 3, "image_not_found_action": 0}),
        create_action(ActionType.COMMENT),
    ]
    worker = _worker(actions)

    worker._last_image_found = True

    assert worker._conditional_jump_index(actions[1]) == 2


def test_if_image_result_continues_when_target_is_zero():
    actions = [
        create_action(ActionType.IMAGE_CLICK),
        MacroAction(type=ActionType.IF_CONDITION, params={"image_found_action": 3, "image_not_found_action": 0}),
        create_action(ActionType.COMMENT),
    ]
    worker = _worker(actions)

    worker._last_image_found = False

    assert worker._conditional_jump_index(actions[1]) is None


def test_if_image_result_continues_when_no_image_result_exists():
    actions = [
        MacroAction(type=ActionType.IF_CONDITION, params={"image_found_action": 2, "image_not_found_action": 2}),
        create_action(ActionType.COMMENT),
    ]
    worker = _worker(actions)

    assert worker._conditional_jump_index(actions[0]) is None


def test_if_image_result_rejects_out_of_range_target():
    actions = [
        create_action(ActionType.IMAGE_CLICK),
        MacroAction(type=ActionType.IF_CONDITION, params={"image_found_action": 99}),
    ]
    worker = _worker(actions)
    worker._last_image_found = True

    with pytest.raises(ValueError, match="outside the macro"):
        worker._conditional_jump_index(actions[1])


def test_skipped_image_click_records_not_found(monkeypatch):
    worker = _worker([create_action(ActionType.IMAGE_CLICK)])
    action = MacroAction(
        type=ActionType.IMAGE_CLICK,
        params={"image_path": "button.png", "on_not_found": "skip"},
    )
    executor = SimpleNamespace(click_image_match=lambda action, match: None)
    mouse_controller = SimpleNamespace(position=(100, 100))

    monkeypatch.setattr(playback_worker, "find_image_match_for_action", lambda action, stop_check=None: None)

    assert worker._play_image_click(action, executor, mouse_controller) is False


def test_backward_if_image_result_loop_runs_until_image_is_not_found(monkeypatch):
    class FakeMouseController:
        def __init__(self) -> None:
            self.position = (100, 100)

    pynput_module = ModuleType("pynput")
    pynput_module.keyboard = SimpleNamespace(Controller=lambda: SimpleNamespace(type=lambda text: None))
    pynput_module.mouse = SimpleNamespace(Controller=FakeMouseController)
    monkeypatch.setitem(sys.modules, "pynput", pynput_module)

    results = [SimpleNamespace(center=(50, 50)), None]

    def fake_find_image_match_for_action(action, stop_check=None):
        return results.pop(0)

    monkeypatch.setattr(playback_worker, "find_image_match_for_action", fake_find_image_match_for_action)

    actions = [create_action(ActionType.COMMENT) for _ in range(7)]
    actions.append(
        MacroAction(
            type=ActionType.IMAGE_CLICK,
            params={
                "image_path": "button.png",
                "click_action": "move_only",
                "on_not_found": "skip",
            },
        )
    )
    actions.append(
        MacroAction(
            type=ActionType.IF_CONDITION,
            params={"image_found_action": 7, "image_not_found_action": 0},
        )
    )
    worker = _worker(actions)
    progress_rows: list[int] = []
    statuses: list[str] = []
    finished: list[tuple[bool, str]] = []
    worker.progress.connect(lambda row, action: progress_rows.append(row + 1))
    worker.status.connect(statuses.append)
    worker.finished.connect(lambda completed, message: finished.append((completed, message)))

    worker.run()

    assert progress_rows == [1, 2, 3, 4, 5, 6, 7, 8, 9, 7, 8, 9]
    assert statuses == ["If Image Result jumped to action 7"]
    assert finished == [(True, "Playback complete")]
