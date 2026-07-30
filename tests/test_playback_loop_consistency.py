from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from macro_recorder_plus.models.actions import ActionType, MacroAction, create_action
from macro_recorder_plus.models.environment import RecordedEnvironment, Rect
from macro_recorder_plus.platform.windows_input import position_mouse
from macro_recorder_plus.playback import playback_worker
from macro_recorder_plus.playback.playback_worker import PlaybackWorker


class RecordingMouseController:
    def __init__(self) -> None:
        self._position = (100, 100)
        self.positions: list[tuple[int, int]] = []

    @property
    def position(self) -> tuple[int, int]:
        return self._position

    @position.setter
    def position(self, value: tuple[int, int]) -> None:
        self._position = (int(value[0]), int(value[1]))
        self.positions.append(self._position)


def _install_fake_pynput(monkeypatch, mouse_controller: object) -> None:
    pynput_module = ModuleType("pynput")
    pynput_module.keyboard = SimpleNamespace(Controller=lambda: SimpleNamespace(type=lambda text: None))
    pynput_module.mouse = SimpleNamespace(Controller=lambda: mouse_controller)
    monkeypatch.setitem(sys.modules, "pynput", pynput_module)


def test_each_macro_loop_reuses_exact_recorded_cursor_anchor(monkeypatch):
    mouse = RecordingMouseController()
    _install_fake_pynput(monkeypatch, mouse)
    environment = RecordedEnvironment(cursor_start=(25, -40))
    worker = PlaybackWorker(
        [create_action(ActionType.COMMENT)],
        repeat_count=100,
        recorded_environment=environment,
        current_environment_snapshot=environment,
    )

    finished: list[tuple[bool, str]] = []
    worker.finished.connect(lambda completed, message: finished.append((completed, message)))
    worker.run()

    assert mouse.positions == [(25, -40)] * 100
    assert finished == [(True, "Playback complete (100 loops)")]


def test_random_delay_is_chosen_between_each_whole_macro_loop(monkeypatch):
    mouse = RecordingMouseController()
    _install_fake_pynput(monkeypatch, mouse)
    environment = RecordedEnvironment()
    worker = PlaybackWorker(
        [create_action(ActionType.COMMENT)],
        repeat_count=3,
        loop_delay_min=1.0,
        loop_delay_max=2.0,
        recorded_environment=environment,
        current_environment_snapshot=environment,
    )
    chosen_ranges = []
    waits = []
    statuses = []

    def fake_uniform(minimum, maximum):
        chosen_ranges.append((minimum, maximum))
        return 1.25 if len(chosen_ranges) == 1 else 1.75

    monkeypatch.setattr(playback_worker.random, "uniform", fake_uniform)
    monkeypatch.setattr(worker, "_wait_seconds", lambda seconds, mouse_controller: waits.append(seconds) or True)
    worker.status.connect(statuses.append)

    worker.run()

    assert chosen_ranges == [(1.0, 2.0), (1.0, 2.0)]
    assert [seconds for seconds in waits if seconds > 0] == [1.25, 1.75]
    assert "Waiting 1.25s before macro loop 2 of 3" in statuses
    assert "Waiting 1.75s before macro loop 3 of 3" in statuses


def test_coordinate_transform_does_not_mutate_or_drift_between_loops():
    recorded = RecordedEnvironment(virtual_desktop=Rect(0, 0, 100, 100))
    current = RecordedEnvironment(virtual_desktop=Rect(-200, 0, 200, 200))
    action = MacroAction(type=ActionType.MOUSE_BUTTON, params={"x": 50, "y": 50, "button": "left"})
    worker = PlaybackWorker(
        [action],
        recorded_environment=recorded,
        current_environment_snapshot=current,
        coordinate_mode="scaled",
    )

    transformed = [worker._with_transformed_coordinates(action).params for _ in range(100)]

    assert transformed == [{"x": 0, "y": 100, "button": "left", "phase": "click"}] * 100
    assert action.params == {"x": 50, "y": 50, "button": "left", "phase": "click"}


def test_absolute_mouse_position_is_retried_until_verified():
    class LaggingMouseController:
        def __init__(self) -> None:
            self.assignments = 0
            self._position = (0, 0)

        @property
        def position(self) -> tuple[int, int]:
            return self._position

        @position.setter
        def position(self, value: tuple[int, int]) -> None:
            self.assignments += 1
            self._position = (0, 0) if self.assignments < 3 else value

    mouse = LaggingMouseController()

    assert position_mouse(mouse, 500, -200) == (500, -200)
    assert mouse.position == (500, -200)
    assert mouse.assignments == 3


def test_playback_errors_report_loop_and_action_and_release_inputs(monkeypatch):
    mouse = RecordingMouseController()
    _install_fake_pynput(monkeypatch, mouse)
    releases: list[str] = []

    class FailingExecutor:
        def __init__(self, keyboard_controller: object, mouse_controller: object) -> None:
            pass

        def execute(self, action: MacroAction) -> None:
            raise ValueError("test failure")

        def release_all(self) -> None:
            releases.append("release")

    monkeypatch.setattr(playback_worker, "ActionExecutor", FailingExecutor)
    environment = RecordedEnvironment()
    worker = PlaybackWorker(
        [create_action(ActionType.TYPE_TEXT)],
        repeat_count=20,
        recorded_environment=environment,
        current_environment_snapshot=environment,
    )
    errors: list[str] = []
    finished: list[tuple[bool, str]] = []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda completed, message: finished.append((completed, message)))

    worker.run()

    expected = "macro loop 1 of 20, action 1 (Type Text): test failure"
    assert errors == [expected]
    assert finished == [(False, expected)]
    assert releases == ["release", "release"]


def test_absolute_mouse_position_failure_is_explicit():
    class StuckMouseController:
        @property
        def position(self) -> tuple[int, int]:
            return (0, 0)

        @position.setter
        def position(self, value: tuple[int, int]) -> None:
            pass

    with pytest.raises(RuntimeError, match=r"Mouse did not reach \(20, 30\)"):
        position_mouse(StuckMouseController(), 20, 30)
