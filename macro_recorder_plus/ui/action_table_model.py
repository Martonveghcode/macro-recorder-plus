from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt, Signal

from macro_recorder_plus.models.actions import ACTION_LABELS, ActionType, MacroAction


class ActionTableModel(QAbstractTableModel):
    dirtyChanged = Signal(bool)

    COLUMNS = ["Index", "Enabled", "Action type", "Description", "Delay", "Timestamp", "Duration", "Target", "Label"]

    def __init__(self, actions: list[MacroAction] | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.actions = actions or []
        self.current_playback_row = -1
        self._dirty = False

    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, dirty: bool = True) -> None:
        if self._dirty != dirty:
            self._dirty = dirty
            self.dirtyChanged.emit(dirty)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.actions)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        action = self.actions[index.row()]
        column = index.column()

        if role == Qt.BackgroundRole and index.row() == self.current_playback_row:
            from PySide6.QtGui import QColor

            return QColor(225, 240, 255)
        if role == Qt.CheckStateRole and column == 1:
            return Qt.Checked if action.enabled else Qt.Unchecked
        if role not in {Qt.DisplayRole, Qt.EditRole}:
            return None

        values = [
            index.row() + 1,
            action.enabled,
            ACTION_LABELS[action.type],
            action.description,
            f"{action.delay:.3f}",
            f"{action.timestamp:.3f}",
            f"{action.duration:.3f}",
            action.target,
            action.label,
        ]
        return values[column]

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemIsEnabled
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if index.column() in {1, 4, 8}:
            flags |= Qt.ItemIsEditable
        if index.column() == 1:
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        action = self.actions[index.row()]
        column = index.column()
        if column == 1 and role in {Qt.CheckStateRole, Qt.EditRole}:
            action.enabled = value == Qt.Checked or value is True
        elif column == 4 and role == Qt.EditRole:
            action.delay = max(0.0, float(value))
        elif column == 8 and role == Qt.EditRole:
            action.label = str(value)
        else:
            return False
        self.dataChanged.emit(index, index, [role])
        self.set_dirty(True)
        return True

    def replace_actions(self, actions: list[MacroAction]) -> None:
        self.beginResetModel()
        self.actions = actions
        self.current_playback_row = -1
        self.endResetModel()
        self.set_dirty(False)

    def insert_action(self, row: int, action: MacroAction) -> None:
        row = min(max(0, row), len(self.actions))
        self.beginInsertRows(QModelIndex(), row, row)
        self.actions.insert(row, action)
        self.endInsertRows()
        self._renumber_timestamps()
        self.set_dirty(True)

    def remove_rows(self, rows: list[int]) -> list[MacroAction]:
        removed: list[MacroAction] = []
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.actions):
                self.beginRemoveRows(QModelIndex(), row, row)
                removed.append(self.actions.pop(row))
                self.endRemoveRows()
        self._renumber_timestamps()
        self.set_dirty(True)
        return list(reversed(removed))

    def replace_action(self, row: int, action: MacroAction) -> MacroAction | None:
        if not 0 <= row < len(self.actions):
            return None
        old = self.actions[row]
        self.actions[row] = action
        self._renumber_timestamps()
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1), [])
        self.set_dirty(True)
        return old

    def move_row(self, row: int, offset: int) -> bool:
        target = row + offset
        if not (0 <= row < len(self.actions) and 0 <= target < len(self.actions)):
            return False
        self.layoutAboutToBeChanged.emit()
        action = self.actions.pop(row)
        self.actions.insert(target, action)
        self._renumber_timestamps()
        self.layoutChanged.emit()
        self.set_dirty(True)
        return True

    def set_playback_row(self, row: int) -> None:
        previous = self.current_playback_row
        self.current_playback_row = row
        for candidate in {previous, row}:
            if 0 <= candidate < len(self.actions):
                self.dataChanged.emit(self.index(candidate, 0), self.index(candidate, self.columnCount() - 1), [])

    def _renumber_timestamps(self) -> None:
        timestamp = 0.0
        for action in self.actions:
            action.timestamp = timestamp
            timestamp += action.delay + action.duration
