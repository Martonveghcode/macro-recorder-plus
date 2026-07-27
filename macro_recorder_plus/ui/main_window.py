from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QFileDialog,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSplitter,
    QSpinBox,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTableView,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from macro_recorder_plus.exporters.pyinstaller_exporter import PyInstallerExporter, split_pyinstaller_options
from macro_recorder_plus.exporters.python_exporter import PythonExporter, default_export_directory, safe_script_filename
from macro_recorder_plus.models.actions import ACTION_LABELS, ActionType, MacroAction, clamp_loop_count, create_action
from macro_recorder_plus.models.environment import current_environment
from macro_recorder_plus.models.macro import MAX_MACRO_LOOP_COUNT, MacroDocument, clamp_macro_loop_count
from macro_recorder_plus.platform.windows_hotkeys import DEFAULT_HOTKEYS, HotkeyManager
from macro_recorder_plus.playback.playback_engine import PlaybackEngine
from macro_recorder_plus.recorder.input_recorder import InputRecorder, RecordingOptions
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
from macro_recorder_plus.ui.theme import apply_theme
from macro_recorder_plus.utilities.action_steps import LogicalActionStep, logical_action_steps, step_at_or_after, step_before
from macro_recorder_plus.utilities.sound import play_notification


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
        self._step_cursor = 0
        self._step_mode = False
        self._step_active: LogicalActionStep | None = None
        self._step_pending_cursor: int | None = None
        self._step_pending_image_found: bool | None = None
        self._step_context: dict[int, bool | None] = {0: None}
        self._step_history: list[int] = []
        self._updating_step_selection = False

        self.undo_stack = QUndoStack(self)
        self.model = ActionTableModel(self.document.actions, self)
        self.model.dirtyChanged.connect(self._on_dirty_changed)
        self.model.modelReset.connect(self._refresh_controls)
        self.model.rowsInserted.connect(self._refresh_controls)
        self.model.rowsRemoved.connect(self._refresh_controls)
        self.model.layoutChanged.connect(self._refresh_controls)
        self.model.modelReset.connect(lambda *_args: self._reset_step_session())
        self.model.rowsInserted.connect(lambda *_args: self._reset_step_session())
        self.model.rowsRemoved.connect(lambda *_args: self._reset_step_session())
        self.model.layoutChanged.connect(lambda *_args: self._reset_step_session())
        self.pre_action_model = ActionTableModel(self.document.pre_actions, self)
        self.pre_action_model.dirtyChanged.connect(self._on_dirty_changed)
        self.pre_action_model.modelReset.connect(self._refresh_controls)
        self.pre_action_model.rowsInserted.connect(self._refresh_controls)
        self.pre_action_model.rowsRemoved.connect(self._refresh_controls)
        self.pre_action_model.layoutChanged.connect(self._refresh_controls)
        self.recorder = InputRecorder(self)
        self.recorder.actionRecorded.connect(self._append_recorded_action, Qt.ConnectionType.QueuedConnection)
        self.recorder.started.connect(self._recording_started)
        self.recorder.stopped.connect(self._recording_stopped)
        self.recorder.pausedChanged.connect(self._recording_pause_changed)
        self.recorder.error.connect(self._show_error)

        self.playback = PlaybackEngine(self)
        self.playback.progress.connect(self._playback_progress)
        self.playback.preActionProgress.connect(self._pre_action_progress)
        self.playback.playbackContext.connect(self._playback_context)
        self.playback.finished.connect(self._playback_finished)
        self.playback.error.connect(self._show_error)
        self.playback.status.connect(lambda message: self.statusBar().showMessage(message))

        self.hotkeys = HotkeyManager(self)
        self.hotkeys.startRecording.connect(self.record_new_macro)
        self.hotkeys.stopRecording.connect(self.stop_active)
        self.hotkeys.pauseRecording.connect(self.pause_active)
        self.hotkeys.emergencyStop.connect(self.stop_active)
        self.hotkeys.pausePlayback.connect(self.pause_active)
        self.hotkeys.registrationFailed.connect(lambda message: self.statusBar().showMessage(f"Hotkeys unavailable: {message}"))

        self.countdown = CountdownOverlay(self)
        self.countdown_status_timer = QTimer(self)
        self.countdown_status_timer.timeout.connect(self._update_countdown_status)
        self.countdown_label = ""
        self.countdown_total = 0
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

        self.act_record_setup = QAction("Recording Setup...", self)
        self.act_record_setup.triggered.connect(self.record_new_macro_with_setup)

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

        self.act_step_back = QAction(style.standardIcon(QStyle.SP_MediaSeekBackward), "Step Back", self)
        self.act_step_back.setShortcut(QKeySequence("Shift+F11"))
        self.act_step_back.setToolTip("Move the test cursor back one logical action (does not undo external effects)")
        self.act_step_back.triggered.connect(self.step_back)

        self.act_step_forward = QAction(style.standardIcon(QStyle.SP_MediaSeekForward), "Step Forward", self)
        self.act_step_forward.setShortcut(QKeySequence("F11"))
        self.act_step_forward.setToolTip("Execute the next logical action without its recorded idle delay")
        self.act_step_forward.triggered.connect(self.step_forward)

        self.act_pause_active = QAction(style.standardIcon(QStyle.SP_MediaPause), "Pause", self)
        self.act_pause_active.setShortcut(QKeySequence("F6"))
        self.act_pause_active.triggered.connect(self.pause_active)

        self.act_stop_active = QAction(style.standardIcon(QStyle.SP_MediaStop), "Stop", self)
        self.act_stop_active.setShortcut(QKeySequence("F9"))
        self.act_stop_active.triggered.connect(self.stop_active)

        self.act_pause_recording = QAction("Pause Recording", self)
        self.act_pause_recording.setShortcut(QKeySequence("F7"))
        self.act_pause_recording.triggered.connect(self.pause_recording)

        self.act_emergency_stop = QAction("Emergency Stop", self)
        self.act_emergency_stop.setShortcut(QKeySequence("F10"))
        self.act_emergency_stop.triggered.connect(self.stop_active)

        self.act_record_hotkey = QAction("Record Hotkey", self)
        self.act_record_hotkey.setShortcut(QKeySequence("F8"))
        self.act_record_hotkey.triggered.connect(self.record_new_macro)
        self.addAction(self.act_record_hotkey)
        self.addAction(self.act_pause_recording)
        self.addAction(self.act_emergency_stop)

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
        file_menu.addAction(self.act_record_setup)
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
        playback_menu.addSeparator()
        playback_menu.addAction(self.act_step_back)
        playback_menu.addAction(self.act_step_forward)
        playback_menu.addSeparator()
        playback_menu.addAction(self.act_pause_active)
        playback_menu.addAction(self.act_stop_active)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.act_settings)
        tools_menu.addAction(self.act_open_logs)

        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for action in [self.act_new, self.act_open, self.act_save, self.act_run, self.act_pause_active, self.act_stop_active]:
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_export_py)
        toolbar.addAction(self.act_settings)

        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        controls = QHBoxLayout()
        self.record_button = QPushButton("Record")
        self.record_button.setToolTip("Record new macro (F8)")
        self.record_button.clicked.connect(self.record_new_macro)
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Run macro from the beginning")
        self.run_button.clicked.connect(self.run_macro)
        self.step_back_button = QPushButton("\u25c0 Step Back")
        self.step_back_button.setToolTip("Move back one logical action; this does not undo actions already performed (Shift+F11)")
        self.step_back_button.clicked.connect(self.step_back)
        self.step_forward_button = QPushButton("Step Forward \u25b6")
        self.step_forward_button.setToolTip("Test one logical action at a time; shortcuts and clicks stay together (F11)")
        self.step_forward_button.clicked.connect(self.step_forward)
        self.macro_loop_spin = QSpinBox()
        self.macro_loop_spin.setRange(1, MAX_MACRO_LOOP_COUNT)
        self.macro_loop_spin.setValue(clamp_macro_loop_count(self.document.settings.get("macro_loop_count", 1)))
        self.macro_loop_spin.setToolTip("Run the whole macro this many times")
        self.macro_loop_spin.setSuffix(" times")
        self.macro_loop_spin.valueChanged.connect(self._macro_loop_count_changed)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setToolTip("Pause or resume recording/playback")
        self.pause_button.clicked.connect(self.pause_active)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop recording/playback or cancel countdown")
        self.stop_button.clicked.connect(self.stop_active)
        self.state_label = QLabel(AppState.IDLE.value)
        self.countdown_banner = QLabel("")
        self.countdown_banner.setAlignment(Qt.AlignCenter)
        self.countdown_banner.hide()
        countdown_font = self.countdown_banner.font()
        countdown_font.setPointSize(20)
        countdown_font.setBold(True)
        self.countdown_banner.setFont(countdown_font)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.record_button)
        controls.addWidget(self.run_button)
        controls.addWidget(self.step_back_button)
        controls.addWidget(self.step_forward_button)
        controls.addWidget(QLabel("Macro loops"))
        controls.addWidget(self.macro_loop_spin)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        controls.addSpacing(16)
        controls.addWidget(QLabel("State"))
        controls.addWidget(self.state_label)
        controls.addStretch(1)
        controls.addWidget(QLabel("Progress"))
        controls.addWidget(self.progress)
        central_layout.addLayout(controls)
        central_layout.addWidget(self.countdown_banner)

        splitter = QSplitter(Qt.Horizontal)
        self.action_tabs = QTabWidget()
        self.table = self._create_action_table(self.model)
        self.pre_action_table = self._create_action_table(self.pre_action_model)
        self.action_tabs.addTab(self.table, "Main actions (looped)")
        self.action_tabs.addTab(self.pre_action_table, "Pre-actions (run once)")
        self.action_tabs.setTabToolTip(0, "These actions repeat according to Macro loops")
        self.action_tabs.setTabToolTip(1, "These actions run once whenever the macro is started, before the main loop")
        self.action_tabs.currentChanged.connect(self._action_tab_changed)
        splitter.addWidget(self.action_tabs)

        self.properties = ActionProperties()
        self.properties.setMinimumWidth(320)
        self.properties.actionChanged.connect(self._replace_action_from_properties)
        splitter.addWidget(self.properties)
        splitter.setSizes([820, 360])
        central_layout.addWidget(splitter)
        self.splitter = splitter
        self.setCentralWidget(central)

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

    def _create_action_table(self, model: ActionTableModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(QTableView.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.doubleClicked.connect(lambda _index: self.properties.apply_button.setFocus())
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_context_menu)
        table.selectionModel().selectionChanged.connect(self._selection_changed)
        return table

    def _active_model(self) -> ActionTableModel:
        if hasattr(self, "action_tabs") and self.action_tabs.currentIndex() == 1:
            return self.pre_action_model
        return self.model

    def _active_table(self) -> QTableView:
        if hasattr(self, "action_tabs") and self.action_tabs.currentIndex() == 1:
            return self.pre_action_table
        return self.table

    def _action_tab_changed(self, _index: int) -> None:
        self._selection_changed()
        self._refresh_controls()

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self._active_table().selectionModel().selectedRows()})

    def _selected_row(self) -> int:
        rows = self._selected_rows()
        return rows[0] if rows else -1

    def _selection_changed(self) -> None:
        row = self._selected_row()
        active_model = self._active_model()
        action = active_model.actions[row] if 0 <= row < len(active_model.actions) else None
        self.properties.set_action(row, action)
        if active_model is self.model and not self._updating_step_selection and self.state == AppState.IDLE and row >= 0:
            self._reset_step_session(row)
            self.model.set_playback_row(-1)

    def _show_context_menu(self, position) -> None:
        menu = QMenu(self)
        menu.addAction(self.act_run_selected)
        menu.addSeparator()
        menu.addAction(self.act_duplicate)
        menu.addAction(self.act_delete)
        menu.addAction(self.act_move_up)
        menu.addAction(self.act_move_down)
        menu.exec(self._active_table().viewport().mapToGlobal(position))

    def record_new_macro(self) -> None:
        options = RecordingOptions(
            record_mouse_movement=True,
            record_keyboard=True,
            record_scroll=True,
            mouse_sample_hz=60,
            simplification_tolerance=2.0,
            ignored_keys={"f8", "f9", "f7", "f10", "f6"},
        )
        self._start_new_recording(options=options, countdown_seconds=5, hide_during_recording=False)

    def record_new_macro_with_setup(self) -> None:
        if self.state == AppState.COUNTING_DOWN:
            self._cancel_countdown()
            return
        if self.playback.running:
            self.status.showMessage("Stop playback before recording")
            return
        if self.state in {AppState.RECORDING, AppState.RECORDING_PAUSED}:
            self.stop_recording()
            return
        if not self._maybe_save():
            return
        dialog = RecordingDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._start_new_recording(
            options=dialog.options(),
            countdown_seconds=dialog.countdown_spin.value(),
            hide_during_recording=dialog.hide_check.isChecked(),
        )

    def _start_new_recording(
        self,
        *,
        options: RecordingOptions,
        countdown_seconds: int,
        hide_during_recording: bool,
    ) -> None:
        if self.state == AppState.COUNTING_DOWN:
            self._cancel_countdown()
            return
        if self.playback.running:
            self.status.showMessage("Stop playback before recording")
            return
        if self.state in {AppState.RECORDING, AppState.RECORDING_PAUSED}:
            self.stop_recording()
            return
        if not self._maybe_save():
            return
        self.document = MacroDocument(name="Recorded Macro", recorded_environment=current_environment())
        self.current_path = None
        self.model.replace_actions(self.document.actions)
        self.pre_action_model.replace_actions(self.document.pre_actions)
        self._load_document_settings()
        self.undo_stack.clear()
        self.recording_hidden = hide_during_recording
        self.status.showMessage("Starting recording...")
        self._start_countdown(
            countdown_seconds,
            "Recording",
            lambda: self._begin_recording(options),
        )

    def _start_countdown(self, seconds: int, label: str, callback) -> None:
        self.countdown_label = label
        self.countdown_total = max(0, int(seconds))
        self._set_state(AppState.COUNTING_DOWN)
        self.countdown_banner.show()
        self.progress.setRange(0, max(1, self.countdown_total))
        self.progress.setValue(0)
        self.countdown_status_timer.start(200)
        self.countdown.start_countdown(self.countdown_total, lambda: self._finish_countdown(callback))
        self._update_countdown_status()

    def _finish_countdown(self, callback) -> None:
        self.countdown_status_timer.stop()
        self.countdown_banner.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        callback()

    def _cancel_countdown(self) -> None:
        self.countdown.cancel()
        self.countdown_status_timer.stop()
        self.countdown_banner.hide()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_state(AppState.IDLE)
        self.status.showMessage("Countdown canceled")

    def _update_countdown_status(self) -> None:
        if self.state != AppState.COUNTING_DOWN:
            self.countdown_status_timer.stop()
            return
        remaining = max(0, self.countdown.remaining)
        message = f"{self.countdown_label} starts in {remaining}s. Press Stop or F9 to cancel."
        self.countdown_banner.setText(message)
        self.status.showMessage(message)
        self.progress.setValue(max(0, self.countdown_total - remaining))

    def _begin_recording(self, options) -> None:
        if self.recording_hidden:
            self.showMinimized()
        self.status.showMessage("Starting recording hooks...")
        try:
            from pynput import mouse

            x, y = mouse.Controller().position
            self.document.recorded_environment.cursor_start = [int(x), int(y)]
        except Exception as exc:
            LOGGER.info("Could not capture initial cursor position: %s", exc)
        play_notification()
        self.recorder.start(options)
        if not self.recorder.running:
            self.status.showMessage("Recording did not start. Check the error dialog or log.")

    def _recording_started(self) -> None:
        self._set_state(AppState.RECORDING)
        self.progress.setRange(0, 0)
        self.status.showMessage("Recording active. Press Stop or F9 to finish.")

    def stop_recording(self) -> None:
        self.recorder.stop()

    def pause_recording(self) -> None:
        if self.recorder.running:
            self.recorder.pause_or_resume()
        else:
            self.status.showMessage("Recording is not active")

    def _recording_pause_changed(self, paused: bool) -> None:
        self._set_state(AppState.RECORDING_PAUSED if paused else AppState.RECORDING)

    def _recording_stopped(self) -> None:
        play_notification()
        if self.recording_hidden:
            self.showNormal()
            self.raise_()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._set_state(AppState.IDLE)
        self.status.showMessage(f"Recording loaded with {len(self.model.actions)} action(s)")

    @Slot(object)
    def _append_recorded_action(self, action: MacroAction) -> None:
        self.model.insert_action(len(self.model.actions), action)
        last = self.model.index(len(self.model.actions) - 1, 0)
        self.table.scrollTo(last)
        self.status.showMessage(f"Recorded {len(self.model.actions)} action(s). Press Stop or F9 to finish.")

    def run_macro(self) -> None:
        self._run_from_index(0)

    def run_from_selected(self) -> None:
        if self._active_model() is self.pre_action_model:
            self._run_pre_actions_from_index(max(0, self._selected_row()))
            return
        self._run_from_index(max(0, self._selected_row()))

    def _run_pre_actions_from_index(self, row: int) -> None:
        if not self.pre_action_model.actions[row:]:
            self.status.showMessage("No pre-actions to run")
            return
        if self._playback_environment() is None:
            return
        countdown_seconds = int(self.settings.value("playback/countdown", 0))
        self._start_countdown(countdown_seconds, "Pre-actions", lambda: self._start_pre_action_playback(row))

    def _start_pre_action_playback(self, row: int) -> None:
        pre_actions = list(self.pre_action_model.actions[row:])
        iterations = sum(clamp_loop_count(action.loop_count) for action in pre_actions if action.enabled)
        self.progress.setRange(0, max(1, iterations))
        self.progress.setValue(0)
        self.playback.play(
            [],
            pre_actions=pre_actions,
            repeat_count=1,
            speed=float(self.settings.value("playback/speed", self.document.settings.get("playback_speed", 1.0))),
            recorded_environment=self.document.recorded_environment,
            current_environment_snapshot=current_environment(),
            coordinate_mode=str(self.document.settings.get("coordinate_mode", "exact")),
        )
        self._set_state(AppState.PLAYING)

    def step_forward(self) -> None:
        if self.state != AppState.IDLE or self.playback.running or self.recorder.running:
            self.status.showMessage("Stop the active recording or playback before stepping")
            return
        steps = self._enabled_logical_steps()
        step = step_at_or_after(steps, self._step_cursor)
        if step is None:
            self.status.showMessage("Reached the end of the macro")
            return
        playback_environment = self._playback_environment()
        if playback_environment is None:
            return

        self._step_mode = True
        self._step_active = step
        self._step_pending_cursor = step.end
        self._step_pending_image_found = self._step_context.get(step.start)
        step_actions = self.model.actions[step.start : step.end]
        step_iterations = sum(clamp_loop_count(action.loop_count) for action in step_actions if action.enabled)
        self.progress.setRange(0, max(1, step_iterations))
        self.progress.setValue(0)
        speed = float(self.settings.value("playback/speed", self.document.settings.get("playback_speed", 1.0)))
        coordinate_mode = str(self.document.settings.get("coordinate_mode", self.settings.value("playback/coordinate_mode", "exact")))
        self.playback.play(
            list(self.model.actions),
            start_index=step.start,
            end_index=step.end,
            repeat_count=1,
            speed=speed,
            respect_action_delays=False,
            initial_image_found=self._step_context.get(step.start),
            recorded_environment=self.document.recorded_environment,
            current_environment_snapshot=playback_environment,
            coordinate_mode=coordinate_mode,
        )
        self._set_state(AppState.PLAYING)
        self.status.showMessage(f"Testing action {step.start + 1}: {self.model.actions[step.start].description}")

    def step_back(self) -> None:
        if self.state != AppState.IDLE or self.playback.running or self.recorder.running:
            self.status.showMessage("Stop the active recording or playback before moving the test cursor")
            return
        steps = self._enabled_logical_steps()
        if not steps:
            self.status.showMessage("No enabled actions to test")
            return
        if self._step_history:
            target = step_at_or_after(steps, self._step_history.pop())
        else:
            target = step_before(steps, self._step_cursor)
        if target is None:
            self.status.showMessage("Already at the start of the macro")
            return
        self._step_cursor = target.start
        self._step_pending_cursor = None
        self._step_pending_image_found = self._step_context.get(target.start)
        self._select_step_row(target.start)
        self.model.set_playback_row(target.start)
        self.status.showMessage(
            f"Test cursor moved to action {target.start + 1}. Step Back does not undo actions already performed."
        )

    def _enabled_logical_steps(self) -> list[LogicalActionStep]:
        return [
            step
            for step in logical_action_steps(self.model.actions)
            if any(action.enabled for action in self.model.actions[step.start : step.end])
        ]

    def _select_step_row(self, row: int) -> None:
        if not 0 <= row < len(self.model.actions):
            return
        self._updating_step_selection = True
        try:
            self.table.selectRow(row)
            self.table.scrollTo(self.model.index(row, 0))
        finally:
            self._updating_step_selection = False

    def _reset_step_session(self, cursor: int = 0) -> None:
        self._step_cursor = min(max(0, cursor), len(self.model.actions))
        self._step_mode = False
        self._step_active = None
        self._step_pending_cursor = None
        self._step_pending_image_found = None
        self._step_context = {self._step_cursor: None}
        self._step_history.clear()

    def _playback_environment(self):
        current = current_environment()
        if self.document.recorded_environment.monitors and len(self.document.recorded_environment.monitors) != len(current.monitors):
            dialog = MonitorWarningDialog(self.document.recorded_environment, current, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            self.document.settings["coordinate_mode"] = dialog.coordinate_mode
        return current

    def _run_from_index(self, row: int) -> None:
        if not self.model.actions and not self.pre_action_model.actions:
            self.status.showMessage("No actions to run")
            return
        if self._playback_environment() is None:
            return
        self._reset_step_session(row)
        countdown_seconds = int(self.settings.value("playback/countdown", 0))
        self._start_countdown(countdown_seconds, "Playback", lambda: self._start_playback(row))

    def _start_playback(self, row: int) -> None:
        self._step_mode = False
        speed = float(self.settings.value("playback/speed", self.document.settings.get("playback_speed", 1.0)))
        coordinate_mode = str(self.document.settings.get("coordinate_mode", self.settings.value("playback/coordinate_mode", "exact")))
        steps_per_loop = sum(clamp_loop_count(action.loop_count) for action in self.model.actions[row:] if action.enabled)
        pre_action_steps = sum(clamp_loop_count(action.loop_count) for action in self.pre_action_model.actions if action.enabled)
        self.progress.setRange(0, max(1, pre_action_steps + steps_per_loop * self.macro_loop_spin.value()))
        self.progress.setValue(0)
        self.playback.play(
            list(self.model.actions),
            pre_actions=list(self.pre_action_model.actions),
            start_index=row,
            repeat_count=self.macro_loop_spin.value(),
            speed=speed,
            recorded_environment=self.document.recorded_environment,
            current_environment_snapshot=current_environment(),
            coordinate_mode=coordinate_mode,
        )
        self._set_state(AppState.PLAYING)

    def pause_playback(self) -> None:
        if self.playback.running:
            self.playback.pause_or_resume()
            self._set_state(AppState.PLAYBACK_PAUSED if self.state == AppState.PLAYING else AppState.PLAYING)
        else:
            self.status.showMessage("Playback is not active")

    def stop_playback(self) -> None:
        if self.playback.running:
            self.playback.stop()
        else:
            self.status.showMessage("Playback is not active")

    def pause_active(self) -> None:
        if self.recorder.running:
            self.pause_recording()
            return
        if self.playback.running:
            self.pause_playback()
            return
        self.status.showMessage("Nothing to pause")

    def stop_active(self) -> None:
        if self.state == AppState.COUNTING_DOWN:
            self._cancel_countdown()
            return
        if self.recorder.running:
            self.stop_recording()
            return
        if self.playback.running:
            self.stop_playback()
            return
        self.status.showMessage("Nothing to stop")

    def _playback_progress(self, row: int, action: MacroAction) -> None:
        self.model.set_playback_row(row)
        self.table.scrollTo(self.model.index(row, 0))
        self.progress.setValue(min(self.progress.maximum(), self.progress.value() + 1))
        self.status.showMessage(action.description)

    def _pre_action_progress(self, row: int, action: MacroAction) -> None:
        self.pre_action_model.set_playback_row(row)
        if 0 <= row < len(self.pre_action_model.actions):
            self.pre_action_table.scrollTo(self.pre_action_model.index(row, 0))
        self.progress.setValue(min(self.progress.maximum(), self.progress.value() + 1))
        self.status.showMessage(f"Pre-action: {action.description}")

    def _playback_context(self, next_index: int, image_found: bool | None) -> None:
        if not self._step_mode:
            return
        self._step_pending_cursor = min(max(0, next_index), len(self.model.actions))
        self._step_pending_image_found = image_found

    def _playback_finished(self, completed: bool, message: str) -> None:
        was_step = self._step_mode
        active_step = self._step_active
        if not was_step or not completed:
            self.model.set_playback_row(-1)
            self.pre_action_model.set_playback_row(-1)
        self.progress.setValue(0)
        self._step_mode = False
        self._step_active = None
        if was_step and completed and active_step is not None:
            self._step_history.append(active_step.start)
            self._step_cursor = self._step_pending_cursor if self._step_pending_cursor is not None else active_step.end
            self._step_context[self._step_cursor] = self._step_pending_image_found
        self._set_state(AppState.IDLE if completed else AppState.ERROR)
        if not completed:
            self._set_state(AppState.IDLE)
            self.status.showMessage(message)
            return
        if was_step:
            next_step = step_at_or_after(self._enabled_logical_steps(), self._step_cursor)
            if next_step is None:
                self.status.showMessage("Step complete. Reached the end of the macro.")
            else:
                self.status.showMessage(f"Step complete. Next is action {next_step.start + 1}.")
            return
        self.status.showMessage(message)

    def insert_action(self, action_type: ActionType) -> None:
        active_model = self._active_model()
        row = self._selected_row()
        target = row + 1 if row >= 0 else len(active_model.actions)
        self.undo_stack.push(InsertActionCommand(active_model, target, create_action(action_type)))

    def delete_selected(self) -> None:
        rows = self._selected_rows()
        if rows:
            self.undo_stack.push(DeleteActionsCommand(self._active_model(), rows))

    def duplicate_selected(self) -> None:
        rows = self._selected_rows()
        active_model = self._active_model()
        for row in rows:
            self.undo_stack.push(InsertActionCommand(active_model, row + 1, active_model.actions[row].clone()))

    def move_selected(self, offset: int) -> None:
        row = self._selected_row()
        if row >= 0:
            self.undo_stack.push(MoveActionCommand(self._active_model(), row, offset))

    def _replace_action_from_properties(self, row: int, action: MacroAction) -> None:
        active_model = self._active_model()
        self.undo_stack.push(ReplaceActionCommand(active_model, row, action))
        if active_model is self.model:
            self._reset_step_session(row)

    def new_empty_macro(self) -> None:
        if not self._maybe_save():
            return
        self.document = MacroDocument(recorded_environment=current_environment())
        self.current_path = None
        self.model.replace_actions(self.document.actions)
        self.pre_action_model.replace_actions(self.document.pre_actions)
        self._load_document_settings()
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
        self.pre_action_model.replace_actions(self.document.pre_actions)
        self._load_document_settings()
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
        self.pre_action_model.set_dirty(False)
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
        export_dir = Path(str(self.settings.value("export/directory", "")) or default_export_directory())
        default_path = export_dir / safe_script_filename(self.document.name)
        path, _ = QFileDialog.getSaveFileName(self, "Export Python Script", str(default_path), "Python scripts (*.py)")
        if not path:
            return
        target = PythonExporter(python_executable=self._configured_python_executable()).export(self.document, path)
        self.settings.setValue("export/directory", str(target.parent))
        self.settings.sync()
        self.status.showMessage(f"Exported {target.name} with runtime files")

    def export_exe(self) -> None:
        python_executable = self._configured_python_executable()
        pyinstaller_executable = self._setting_text("export/pyinstaller") or None
        using_current_python = python_executable == sys.executable
        if pyinstaller_executable is None and using_current_python and importlib.util.find_spec("PyInstaller") is None:
            QMessageBox.warning(self, "PyInstaller unavailable", "Install PyInstaller to export a Windows .exe.")
            return
        self._sync_document()
        default_dir = Path(self._setting_text("export/directory") or default_export_directory())
        output_dir = QFileDialog.getExistingDirectory(self, "Choose EXE output folder", str(default_dir))
        if not output_dir:
            return
        self.settings.setValue("export/directory", output_dir)
        self.settings.sync()
        script_path = Path(output_dir) / safe_script_filename(self.document.name)
        PythonExporter(python_executable=python_executable).export(self.document, script_path)
        dialog = ExportDialog(self)
        self.export_process = PyInstallerExporter(self)
        self.export_process.output.connect(dialog.append_output)
        self.export_process.finished.connect(lambda ok, code: self._pyinstaller_finished(ok, code, dialog))
        self.export_progress = QProgressDialog("Building executable...", "Cancel", 0, 0, self)
        self.export_progress.setWindowTitle("Export Windows EXE")
        self.export_progress.canceled.connect(lambda: self.export_process.process.kill() if self.export_process and self.export_process.process else None)
        self._set_state(AppState.EXPORTING)
        self.export_process.build(
            script_path,
            output_dir,
            name=script_path.stem,
            python_executable=python_executable,
            pyinstaller_executable=pyinstaller_executable,
            extra_args=split_pyinstaller_options(self._setting_text("export/options")),
        )
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
        if dialog.exec() == QDialog.DialogCode.Accepted:
            theme_error = apply_theme(self.settings)
            if theme_error:
                self.status.showMessage(theme_error)
            else:
                self._refresh_themed_widgets()
            self._restart_hotkeys()

    def _restart_hotkeys(self) -> None:
        hotkeys = {name: str(self.settings.value(f"hotkeys/{name}", default)) for name, default in DEFAULT_HOTKEYS.items()}
        self.hotkeys.start(hotkeys)

    def _setting_text(self, key: str, default: str = "") -> str:
        return str(self.settings.value(key, default) or "").strip()

    def _configured_python_executable(self) -> str:
        return self._setting_text("export/python") or sys.executable

    def _refresh_themed_widgets(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        for widget in app.allWidgets():
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _maybe_save(self) -> bool:
        if not self.model.dirty and not self.pre_action_model.dirty:
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
        self.document.pre_actions = self.pre_action_model.actions
        self.document.settings["playback_speed"] = float(self.settings.value("playback/speed", 1.0))
        self.document.settings["coordinate_mode"] = str(self.settings.value("playback/coordinate_mode", "exact"))
        self.document.settings["macro_loop_count"] = self.macro_loop_spin.value()

    def _load_document_settings(self) -> None:
        self.macro_loop_spin.blockSignals(True)
        self.macro_loop_spin.setValue(clamp_macro_loop_count(self.document.settings.get("macro_loop_count", 1)))
        self.macro_loop_spin.blockSignals(False)

    def _macro_loop_count_changed(self, value: int) -> None:
        self.document.settings["macro_loop_count"] = clamp_macro_loop_count(value)
        self.model.set_dirty(True)

    def _on_dirty_changed(self, dirty: bool) -> None:
        self._update_title()

    def _update_title(self) -> None:
        marker = "*" if self.model.dirty or self.pre_action_model.dirty else ""
        name = self.current_path.name if self.current_path else self.document.name
        self.setWindowTitle(f"{marker}{name} - Macro Recorder +")

    def _set_state(self, state: AppState) -> None:
        self.state = state
        self.state_label.setText(state.value)
        self.status.showMessage(state.value)
        self._refresh_controls()

    def _refresh_controls(self, *args) -> None:
        is_idle = self.state == AppState.IDLE
        is_recording = self.state in {AppState.RECORDING, AppState.RECORDING_PAUSED}
        has_enabled_actions = any(action.enabled for action in self.model.actions)
        has_any_actions = bool(self.model.actions or self.pre_action_model.actions)
        active_has_actions = bool(self._active_model().actions)
        self.act_new.setEnabled(True)
        self.act_open.setEnabled(is_idle)
        self.act_save.setEnabled(is_idle)
        self.act_run.setEnabled(True)
        self.act_run_selected.setEnabled(is_idle and active_has_actions)
        self.act_step_back.setEnabled(is_idle and has_enabled_actions)
        self.act_step_forward.setEnabled(is_idle and has_enabled_actions)
        self.act_pause_active.setEnabled(True)
        self.act_stop_active.setEnabled(True)
        self.act_pause_active.setText("Resume" if self.state in {AppState.RECORDING_PAUSED, AppState.PLAYBACK_PAUSED} else "Pause")
        if self.state == AppState.COUNTING_DOWN:
            self.record_button.setText("Cancel Countdown")
        else:
            self.record_button.setText("Stop Recording" if is_recording else "Record")
        self.run_button.setEnabled(True)
        self.step_back_button.setEnabled(is_idle and has_enabled_actions)
        self.step_forward_button.setEnabled(is_idle and has_enabled_actions)
        self.macro_loop_spin.setEnabled(is_idle)
        self.pause_button.setText("Resume" if self.state in {AppState.RECORDING_PAUSED, AppState.PLAYBACK_PAUSED} else "Pause")
        self.stop_button.setText("Cancel" if self.state == AppState.COUNTING_DOWN else "Stop")
        self.stop_button.setEnabled(True)
        self.act_export_py.setEnabled(is_idle and has_any_actions)
        self.act_export_exe.setEnabled(is_idle and has_any_actions)
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
        self.countdown.cancel()
        self.countdown_status_timer.stop()
        self.hotkeys.stop()
        self._save_window_state()
        event.accept()
