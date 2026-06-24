from __future__ import annotations

import importlib.util
import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.exporters.pyinstaller_exporter import PyInstallerExporter
from macro_recorder_plus.exporters.python_exporter import PythonExporter
from macro_recorder_plus.models.actions import ACTION_LABELS, ActionType, MacroAction, create_action
from macro_recorder_plus.models.environment import current_environment
from macro_recorder_plus.models.macro import MacroDocument
from macro_recorder_plus.platform.windows_hotkeys import DEFAULT_HOTKEYS, HotkeyManager
from macro_recorder_plus.playback.playback_engine import PlaybackEngine
from macro_recorder_plus.recorder.input_recorder import InputRecorder
from macro_recorder_plus.storage.json_store import MacroFileError, load_macro, save_macro
from macro_recorder_plus.ui.action_properties import ActionProperties
from macro_recorder_plus.ui.action_table_model import ActionTableModel
from macro_recorder_plus.ui.commands import DeleteActionsCommand, InsertActionCommand, MoveActionCommand, ReplaceActionCommand
from macro_recorder_plus.ui.countdown_overlay import CountdownOverlay
from macro_recorder_plus.ui.export_dialog import ExportDialog
from macro_recorder_plus.ui.monitor_warning_dialog import MonitorWarningDialog
from macro_recorder_plus.ui.recording_dialog import RecordingDialog
from macro_recorder_plus.ui.settings_dialog import SettingsDialog
from macro_recorder_plus.ui.state import AppState


LOGGER = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, *, settings: QSettings, log_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.log_path = log_path
        self.document = MacroDocument(recorded_environment=current_environment())
        self.current_path: Path | None = None
        self.state = AppState.IDLE
        self.recording_hidden = False

        self.undo_stack = QUndoStack(self)
        self.model = ActionTableModel(self.document.actions, self)
        self.model.dirtyChanged.connect(self._on_dirty_changed)
        self.recorder = InputRecorder(self)
        self.recorder.actionRecorded.connect(self._append_recorded_action)
        self.recorder.started.connect(lambda: self._set_state(AppState.RECORDING))
        self.recorder.stopped.connect(self._recording_stopped)
        self.recorder.pausedChanged.connect(self._recording_pause_changed)
        self.recorder.error.connect(self._show_error)

        self.playback = PlaybackEngine(self)
        self.playback.progress.connect(self._playback_progress)
        self.playback.finished.connect(self._playback_finished)
        self.playback.error.connect(self._show_error)
        self.playback.status.connect(lambda message: self.statusBar().showMessage(message))

        self.hotkeys = HotkeyManager(self)
        self.hotkeys.startRecording.connect(self.record_new_macro)
        self.hotkeys.stopRecording.connect(self.stop_recording)
        self.hotkeys.pauseRecording.connect(self.pause_recording)
        self.hotkeys.emergencyStop.connect(self.stop_playback)
        self.hotkeys.pausePlayback.connect(self.pause_playback)
        self.hotkeys.registrationFailed.connect(lambda message: self.statusBar().showMessage(f"Hotkeys unavailable: {message}"))

        self.countdown = CountdownOverlay(self)
        self.export_process: PyInstallerExporter | None = None
        self.export_progress: QProgressDialog | None = None

        self._build_actions()
        self._build_ui()
        self._restore_window_state()
        self._restart_hotkeys()
        self._update_title()
        self._set_state(AppState.IDLE)

    def _build_actions(self) -> None:
        style = self.style()
        self.act_new = QAction(style.standardIcon(QStyle.SP_FileIcon), "Record New Macro", self)
        self.act_new.setShortcut(QKeySequence.New)
        self.act_new.triggered.connect(self.record_new_macro)

        self.act_open = QAction(style.standardIcon(QStyle.SP_DialogOpenButton), "Open Macro", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_macro)

        self.act_save = QAction(style.standardIcon(QStyle.SP_DialogSaveButton), "Save Macro", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.triggered.connect(self.save_macro)

        self.act_save_as = QAction("Save Macro As", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self.save_macro_as)

        self.act_run = QAction(style.standardIcon(QStyle.SP_MediaPlay), "Run Macro", self)
        self.act_run.setShortcut(QKeySequence("Ctrl+R"))
        self.act_run.triggered.connect(self.run_macro)

        self.act_run_selected = QAction("Run From Selected Action", self)
        self.act_run_selected.triggered.connect(self.run_from_selected)

        self.act_pause_playback = QAction(style.standardIcon(QStyle.SP_MediaPause), "Pause Playback", self)
        self.act_pause_playback.triggered.connect(self.pause_playback)

        self.act_stop_playback = QAction(style.standardIcon(QStyle.SP_MediaStop), "Stop Playback", self)
        self.act_stop_playback.triggered.connect(self.stop_playback)

        self.act_export_py = QAction("Export Python Script", self)
        self.act_export_py.triggered.connect(self.export_python)

        self.act_export_exe = QAction("Export Windows EXE", self)
        self.act_export_exe.triggered.connect(self.export_exe)

        self.act_settings = QAction("Open Settings", self)
        self.act_settings.triggered.connect(self.open_settings)

        self.act_exit = QAction("Exit", self)
        self.act_exit.setShortcut(QKeySequence.Quit)
        self.act_exit.triggered.connect(self.close)

        self.act_delete = QAction("Delete Selected Action", self)
        self.act_delete.setShortcut(QKeySequence.Delete)
        self.act_delete.triggered.connect(self.delete_selected)

        self.act_duplicate = QAction("Duplicate Action", self)
        self.act_duplicate.setShortcut(QKeySequence("Ctrl+D"))
        self.act_duplicate.triggered.connect(self.duplicate_selected)

        self.act_move_up = QAction("Move Up", self)
        self.act_move_up.triggered.connect(lambda: self.move_selected(-1))

        self.act_move_down = QAction("Move Down", self)
        self.act_move_down.triggered.connect(lambda: self.move_selected(1))

        self.act_undo = self.undo_stack.createUndoAction(self, "Undo")
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_redo = self.undo_stack.createRedoAction(self, "Redo")
        self.act_redo.setShortcut(QKeySequence.Redo)

        self.act_open_logs = QAction("Open Log Folder", self)
        self.act_open_logs.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path.parent))))

    def _build_ui(self) -> None:
        self.setWindowTitle("Macro Recorder +")
        self.resize(1200, 760)
        self.setMinimumSize(900, 560)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.act_new)
        file_menu.addAction(self.act_open)
        self.recent_menu = file_menu.addMenu("Recent Files")
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_export_py)
        file_menu.addAction(self.act_export_exe)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_delete)
        edit_menu.addAction(self.act_duplicate)
        edit_menu.addAction(self.act_move_up)
        edit_menu.addAction(self.act_move_down)
        insert_menu = edit_menu.addMenu("Insert Action")
        for action_type, label in ACTION_LABELS.items():
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, kind=action_type: self.insert_action(kind))
            insert_menu.addAction(action)

        playback_menu = self.menuBar().addMenu("&Playback")
        playback_menu.addAction(self.act_run)
        playback_menu.addAction(self.act_run_selected)
        playback_menu.addAction(self.act_pause_playback)
        playback_menu.addAction(self.act_stop_playback)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.act_settings)
        tools_menu.addAction(self.act_open_logs)

        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for action in [self.act_new, self.act_open, self.act_save, self.act_run, self.act_pause_playback, self.act_stop_playback]:
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_export_py)
        toolbar.addAction(self.act_settings)

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        controls = QHBoxLayout()
        self.state_label = QLabel(AppState.IDLE.value)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(QLabel("State"))
        controls.addWidget(self.state_label)
        controls.addStretch(1)
        controls.addWidget(QLabel("Progress"))
        controls.addWidget(self.progress)
        central_layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(lambda _index: self.properties.apply_button.setFocus())
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        splitter.addWidget(self.table)

        self.properties = ActionProperties()
        self.properties.setMinimumWidth(320)
        self.properties.actionChanged.connect(self._replace_action_from_properties)
        splitter.addWidget(self.properties)
        splitter.setSizes([820, 360])
        central_layout.addWidget(splitter)
        self.splitter = splitter
        self.setCentralWidget(central)

        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon() or QIcon(), self)
            self.tray.setToolTip("Macro Recorder +")
            self.tray.show()
        else:
            self.tray = None

        self._refresh_recent_menu()

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def _selected_row(self) -> int:
        rows = self._selected_rows()
        return rows[0] if rows else -1

    def _selection_changed(self) -> None:
        row = self._selected_row()
        action = self.model.actions[row] if 0 <= row < len(self.model.actions) else None
        self.properties.set_action(row, action)

    def _show_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.act_run_selected)
        menu.addSeparator()
        menu.addAction(self.act_duplicate)
        menu.addAction(self.act_delete)
        menu.addAction(self.act_move_up)
        menu.addAction(self.act_move_down)
        menu.exec(self.table.viewport().mapToGlobal(position))

    def record_new_macro(self) -> None:
        if self.state in {AppState.RECORDING, AppState.RECORDING_PAUSED}:
            self.stop_recording()
            return
        if not self._maybe_save():
            return
        dialog = RecordingDialog(self)
        if dialog.exec() != dialog.Accepted:
            return
        self.document = MacroDocument(name="Recorded Macro", recorded_environment=current_environment())
        self.current_path = None
        self.model.replace_actions(self.document.actions)
        self.undo_stack.clear()
        self.recording_hidden = dialog.hide_check.isChecked()
        self._set_state(AppState.COUNTING_DOWN)
        self.countdown.start_countdown(dialog.countdown_spin.value(), lambda: self._begin_recording(dialog.options()))

    def _begin_recording(self, options) -> None:
        if self.recording_hidden:
            self.showMinimized()
        QApplication.beep()
        self.recorder.start(options)

    def stop_recording(self) -> None:
        self.recorder.stop()

    def pause_recording(self) -> None:
        self.recorder.pause_or_resume()

    def _recording_pause_changed(self, paused: bool) -> None:
        self._set_state(AppState.RECORDING_PAUSED if paused else AppState.RECORDING)

    def _recording_stopped(self) -> None:
        QApplication.beep()
        if self.recording_hidden:
            self.showNormal()
            self.raise_()
        self._set_state(AppState.IDLE)
        self.status.showMessage(f"Recording loaded with {len(self.model.actions)} action(s)")

    def _append_recorded_action(self, action: MacroAction) -> None:
        self.model.insert_action(len(self.model.actions), action)
        last = self.model.index(len(self.model.actions) - 1, 0)
        self.table.scrollTo(last)

    def run_macro(self) -> None:
        self._run_from_index(0)

    def run_from_selected(self) -> None:
        self._run_from_index(max(0, self._selected_row()))

    def _run_from_index(self, row: int) -> None:
        if not self.model.actions:
            self.status.showMessage("No actions to run")
            return
        current = current_environment()
        if self.document.recorded_environment.monitors and len(self.document.recorded_environment.monitors) != len(current.monitors):
            dialog = MonitorWarningDialog(self.document.recorded_environment, current, self)
            if dialog.exec() != dialog.Accepted:
                return
            self.document.settings["coordinate_mode"] = dialog.coordinate_mode
        countdown_seconds = int(self.settings.value("playback/countdown", 0))
        self._set_state(AppState.COUNTING_DOWN)
        self.countdown.start_countdown(countdown_seconds, lambda: self._start_playback(row))

    def _start_playback(self, row: int) -> None:
        speed = float(self.settings.value("playback/speed", self.document.settings.get("playback_speed", 1.0)))
        self.progress.setRange(0, max(1, len(self.model.actions) - row))
        self.progress.setValue(0)
        self.playback.play(list(self.model.actions), start_index=row, speed=speed)
        self._set_state(AppState.PLAYING)

    def pause_playback(self) -> None:
        if self.playback.running:
            self.playback.pause_or_resume()
            self._set_state(AppState.PLAYBACK_PAUSED if self.state == AppState.PLAYING else AppState.PLAYING)

    def stop_playback(self) -> None:
        self.playback.stop()

    def _playback_progress(self, row: int, action: MacroAction) -> None:
        self.model.set_playback_row(row)
        self.table.scrollTo(self.model.index(row, 0))
        self.progress.setValue(min(self.progress.maximum(), self.progress.value() + 1))
        self.status.showMessage(action.description)

    def _playback_finished(self, completed: bool, message: str) -> None:
        self.model.set_playback_row(-1)
        self.progress.setValue(0)
        self.status.showMessage(message)
        self._set_state(AppState.IDLE if completed else AppState.ERROR)
        if not completed:
            self._set_state(AppState.IDLE)

    def insert_action(self, action_type: ActionType) -> None:
        row = self._selected_row()
        target = row + 1 if row >= 0 else len(self.model.actions)
        self.undo_stack.push(InsertActionCommand(self.model, target, create_action(action_type)))

    def delete_selected(self) -> None:
        rows = self._selected_rows()
        if rows:
            self.undo_stack.push(DeleteActionsCommand(self.model, rows))

    def duplicate_selected(self) -> None:
        rows = self._selected_rows()
        for row in rows:
            self.undo_stack.push(InsertActionCommand(self.model, row + 1, self.model.actions[row].clone()))

    def move_selected(self, offset: int) -> None:
        row = self._selected_row()
        if row >= 0:
            self.undo_stack.push(MoveActionCommand(self.model, row, offset))

    def _replace_action_from_properties(self, row: int, action: MacroAction) -> None:
        self.undo_stack.push(ReplaceActionCommand(self.model, row, action))

    def new_empty_macro(self) -> None:
        if not self._maybe_save():
            return
        self.document = MacroDocument(recorded_environment=current_environment())
        self.current_path = None
        self.model.replace_actions(self.document.actions)
        self.undo_stack.clear()
        self._update_title()

    def open_macro(self) -> None:
        if not self._maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Macro", "", "Macro files (*.mrplus.json *.json);;All files (*.*)")
        if not path:
            return
        self._open_path(Path(path))

    def _open_path(self, path: Path) -> None:
        try:
            self.document = load_macro(path)
        except MacroFileError as exc:
            self._show_error(str(exc))
            return
        self.current_path = path
        self.model.replace_actions(self.document.actions)
        self.undo_stack.clear()
        self._add_recent_file(path)
        self._update_title()
        self.status.showMessage(f"Loaded {path.name}")

    def save_macro(self) -> bool:
        if self.current_path is None:
            return self.save_macro_as()
        self._sync_document()
        self.current_path = save_macro(self.document, self.current_path)
        self.model.set_dirty(False)
        self._add_recent_file(self.current_path)
        self._update_title()
        self.status.showMessage(f"Saved {self.current_path.name}")
        return True

    def save_macro_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Macro", "", "Macro files (*.mrplus.json);;JSON (*.json)")
        if not path:
            return False
        self.current_path = Path(path)
        return self.save_macro()

    def export_python(self) -> None:
        self._sync_document()
        path, _ = QFileDialog.getSaveFileName(self, "Export Python Script", "", "Python scripts (*.py)")
        if not path:
            return
        target = PythonExporter().export(self.document, path)
        self.status.showMessage(f"Exported {target.name}")

    def export_exe(self) -> None:
        if importlib.util.find_spec("PyInstaller") is None:
            QMessageBox.warning(self, "PyInstaller unavailable", "Install PyInstaller to export a Windows .exe.")
            return
        self._sync_document()
        output_dir = QFileDialog.getExistingDirectory(self, "Choose EXE output folder")
        if not output_dir:
            return
        script_path = Path(output_dir) / f"{self.document.name.replace(' ', '_').lower()}_macro.py"
        PythonExporter().export(self.document, script_path)
        dialog = ExportDialog(self)
        self.export_process = PyInstallerExporter(self)
        self.export_process.output.connect(dialog.append_output)
        self.export_process.finished.connect(lambda ok, code: self._pyinstaller_finished(ok, code, dialog))
        self.export_progress = QProgressDialog("Building executable...", "Cancel", 0, 0, self)
        self.export_progress.setWindowTitle("Export Windows EXE")
        self.export_progress.canceled.connect(lambda: self.export_process.process.kill() if self.export_process and self.export_process.process else None)
        self._set_state(AppState.EXPORTING)
        self.export_process.build(script_path, output_dir, name=script_path.stem)
        dialog.show()
        self.export_progress.show()

    def _pyinstaller_finished(self, ok: bool, code: int, dialog: ExportDialog) -> None:
        dialog.append_output(f"\nFinished with exit code {code}\n")
        if self.export_progress is not None:
            self.export_progress.close()
            self.export_progress = None
        self._set_state(AppState.IDLE if ok else AppState.ERROR)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == dialog.Accepted:
            self._restart_hotkeys()

    def _restart_hotkeys(self) -> None:
        hotkeys = {name: str(self.settings.value(f"hotkeys/{name}", default)) for name, default in DEFAULT_HOTKEYS.items()}
        self.hotkeys.start(hotkeys)

    def _maybe_save(self) -> bool:
        if not self.model.dirty:
            return True
        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save changes to the current macro?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if result == QMessageBox.Cancel:
            return False
        if result == QMessageBox.Save:
            return self.save_macro()
        return True

    def _sync_document(self) -> None:
        self.document.actions = self.model.actions
        self.document.settings["playback_speed"] = float(self.settings.value("playback/speed", 1.0))
        self.document.settings["coordinate_mode"] = str(self.settings.value("playback/coordinate_mode", "exact"))

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._update_title()

    def _update_title(self) -> None:
        marker = "*" if self.model.dirty else ""
        name = self.current_path.name if self.current_path else self.document.name
        self.setWindowTitle(f"{marker}{name} - Macro Recorder +")

    def _set_state(self, state: AppState) -> None:
        self.state = state
        self.state_label.setText(state.value)
        self.status.showMessage(state.value)
        is_idle = state == AppState.IDLE
        is_recording = state in {AppState.RECORDING, AppState.RECORDING_PAUSED}
        is_playing = state in {AppState.PLAYING, AppState.PLAYBACK_PAUSED}
        self.act_new.setEnabled(not is_playing)
        self.act_open.setEnabled(is_idle)
        self.act_save.setEnabled(is_idle)
        self.act_run.setEnabled(is_idle and bool(self.model.actions))
        self.act_run_selected.setEnabled(is_idle and bool(self.model.actions))
        self.act_pause_playback.setEnabled(is_playing)
        self.act_stop_playback.setEnabled(is_playing)
        self.act_export_py.setEnabled(is_idle and bool(self.model.actions))
        self.act_export_exe.setEnabled(is_idle and bool(self.model.actions))
        self.act_delete.setEnabled(is_idle)
        self.act_duplicate.setEnabled(is_idle)

    def _add_recent_file(self, path: Path) -> None:
        files = [file for file in self.settings.value("recent/files", [], list) if file != str(path)]
        files.insert(0, str(path))
        self.settings.setValue("recent/files", files[:8])
        self._refresh_recent_menu()

    def _refresh_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.settings.value("recent/files", [], list)
        if not files:
            self.recent_menu.setEnabled(False)
            return
        self.recent_menu.setEnabled(True)
        for file in files:
            action = QAction(Path(file).name, self)
            action.setToolTip(file)
            action.triggered.connect(lambda _checked=False, path=file: self._open_path(Path(path)))
            self.recent_menu.addAction(action)

    def _restore_window_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        splitter_state = self.settings.value("window/splitter")
        if splitter_state:
            self.splitter.restoreState(splitter_state)

    def _save_window_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/splitter", self.splitter.saveState())
        self.settings.sync()

    def _show_error(self, message: str) -> None:
        LOGGER.error(message)
        self._set_state(AppState.ERROR)
        QMessageBox.critical(self, "Macro Recorder +", message)
        self._set_state(AppState.IDLE)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_save():
            event.ignore()
            return
        self.recorder.stop()
        self.playback.stop()
        self.hotkeys.stop()
        self._save_window_state()
        event.accept()
