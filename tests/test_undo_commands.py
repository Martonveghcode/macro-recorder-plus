from __future__ import annotations

from PySide6.QtGui import QUndoStack

from macro_recorder_plus.models.actions import ActionType, create_action
from macro_recorder_plus.ui.action_table_model import ActionTableModel
from macro_recorder_plus.ui.commands import InsertActionCommand, MoveActionCommand


def test_insert_undo_redo(qtbot):
    model = ActionTableModel([])
    stack = QUndoStack()

    stack.push(InsertActionCommand(model, 0, create_action(ActionType.COMMENT)))
    assert model.rowCount() == 1
    stack.undo()
    assert model.rowCount() == 0
    stack.redo()
    assert model.rowCount() == 1


def test_move_action_undo_redo(qtbot):
    model = ActionTableModel([create_action(ActionType.WAIT), create_action(ActionType.COMMENT)])
    stack = QUndoStack()

    stack.push(MoveActionCommand(model, 0, 1))
    assert model.actions[0].type == ActionType.COMMENT
    stack.undo()
    assert model.actions[0].type == ActionType.WAIT
