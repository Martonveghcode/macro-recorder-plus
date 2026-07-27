from __future__ import annotations

from dataclasses import dataclass

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.utilities.key_sequences import normalize_key_name


@dataclass(frozen=True, slots=True)
class LogicalActionStep:
    """A half-open range of recorded rows that should be tested atomically."""

    start: int
    end: int


def logical_action_steps(actions: list[MacroAction]) -> list[LogicalActionStep]:
    """Group low-level press/release rows into user-visible playback steps.

    New recordings store shortcuts as one HOTKEY row. Older recordings may
    contain a modifier/key press/release sequence instead, while mouse clicks
    and ordinary key taps are also represented by separate rows. Keeping these
    rows in one logical step prevents step playback from leaving input held.
    """

    steps: list[LogicalActionStep] = []
    index = 0
    while index < len(actions):
        action = actions[index]
        end = index + 1
        if _is_press(action, ActionType.KEY_PRESS):
            key = normalize_key_name(str(action.params.get("key", "")))
            end = _matching_release_end(actions, index, ActionType.KEY_PRESS, key)
        elif _is_press(action, ActionType.MOUSE_BUTTON):
            button = str(action.params.get("button", "left")).lower()
            end = _matching_release_end(actions, index, ActionType.MOUSE_BUTTON, button)
        steps.append(LogicalActionStep(index, end))
        index = end
    return steps


def step_at_or_after(steps: list[LogicalActionStep], row: int) -> LogicalActionStep | None:
    """Return the step containing row, or the next step after it."""

    for step in steps:
        if step.end > row:
            return step
    return None


def step_before(steps: list[LogicalActionStep], cursor: int) -> LogicalActionStep | None:
    """Return the logical step immediately before a playback cursor."""

    previous = None
    for step in steps:
        if step.start >= cursor:
            break
        previous = step
    return previous


def _is_press(action: MacroAction, action_type: ActionType) -> bool:
    return action.type == action_type and str(action.params.get("phase", "")).lower() in {"press", "down"}


def _matching_release_end(
    actions: list[MacroAction],
    start: int,
    action_type: ActionType,
    input_name: str,
) -> int:
    for index in range(start + 1, len(actions)):
        candidate = actions[index]
        if candidate.type != action_type:
            continue
        if action_type == ActionType.KEY_PRESS:
            candidate_name = normalize_key_name(str(candidate.params.get("key", "")))
        else:
            candidate_name = str(candidate.params.get("button", "left")).lower()
        phase = str(candidate.params.get("phase", "")).lower()
        if candidate_name == input_name and phase in {"release", "up"}:
            return index + 1
    return start + 1
