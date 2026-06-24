from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from macro_recorder_plus.models.actions import MacroAction
from macro_recorder_plus.ui.action_table_model import ActionTableModel


class InsertActionCommand(QUndoCommand):
    def __init__(self, model: ActionTableModel, row: int, action: MacroAction) -> None:
        super().__init__("Insert action")
        self.model = model
        self.row = row
        self.action = action

    def redo(self) -> None:
        self.model.insert_action(self.row, self.action)

    def undo(self) -> None:
        self.model.remove_rows([self.row])


class DeleteActionsCommand(QUndoCommand):
    def __init__(self, model: ActionTableModel, rows: list[int]) -> None:
        super().__init__("Delete action(s)")
        self.model = model
        self.rows = sorted(set(rows))
        self.removed: list[MacroAction] = []

    def redo(self) -> None:
        self.removed = self.model.remove_rows(self.rows)

    def undo(self) -> None:
        for row, action in zip(self.rows, self.removed, strict=False):
            self.model.insert_action(row, action)


class ReplaceActionCommand(QUndoCommand):
    def __init__(self, model: ActionTableModel, row: int, new_action: MacroAction) -> None:
        super().__init__("Edit action")
        self.model = model
        self.row = row
        self.new_action = new_action
        self.old_action: MacroAction | None = None

    def redo(self) -> None:
        old = self.model.replace_action(self.row, self.new_action)
        if self.old_action is None:
            self.old_action = old

    def undo(self) -> None:
        if self.old_action is not None:
            self.model.replace_action(self.row, self.old_action)


class MoveActionCommand(QUndoCommand):
    def __init__(self, model: ActionTableModel, row: int, offset: int) -> None:
        super().__init__("Move action")
        self.model = model
        self.row = row
        self.offset = offset

    def redo(self) -> None:
        self.model.move_row(self.row, self.offset)

    def undo(self) -> None:
        self.model.move_row(self.row + self.offset, -self.offset)
