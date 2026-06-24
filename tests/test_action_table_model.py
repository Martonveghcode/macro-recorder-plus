from __future__ import annotations

from PySide6.QtCore import Qt

from macro_recorder_plus.models.actions import ActionType, create_action
from macro_recorder_plus.ui.action_table_model import ActionTableModel


def test_action_table_model_insert_edit_remove(qtbot):
    model = ActionTableModel([])
    action = create_action(ActionType.WAIT)

    model.insert_action(0, action)
    assert model.rowCount() == 1

    delay_index = model.index(0, 4)
    assert model.setData(delay_index, 2.5, Qt.EditRole)
    assert model.actions[0].delay == 2.5
    assert model.dirty

    removed = model.remove_rows([0])
    assert removed[0].type == ActionType.WAIT
    assert model.rowCount() == 0


def test_action_table_model_highlights_current_playback_row(qtbot):
    model = ActionTableModel([create_action(ActionType.WAIT)])

    model.set_playback_row(0)

    assert model.current_playback_row == 0
