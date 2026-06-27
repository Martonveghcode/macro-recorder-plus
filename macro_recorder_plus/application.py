from __future__ import annotations

import sys
import os
import logging

from PySide6.QtCore import QCoreApplication, QSettings, QTimer
from PySide6.QtWidgets import QApplication

from macro_recorder_plus.platform.windows_dpi import set_process_dpi_awareness
from macro_recorder_plus.ui.main_window import MainWindow
from macro_recorder_plus.ui.theme import apply_theme
from macro_recorder_plus.utilities.logging import configure_logging


def run() -> int:
    set_process_dpi_awareness()
    QCoreApplication.setOrganizationName("MacroRecorderPlus")
    QCoreApplication.setApplicationName("Macro Recorder +")
    app = QApplication(sys.argv)
    log_path = configure_logging()
    settings = QSettings()
    theme_error = apply_theme(settings)
    if theme_error:
        logging.getLogger(__name__).warning(theme_error)
    window = MainWindow(settings=settings, log_path=log_path)
    window.show()
    smoke_exit_ms = os.environ.get("MACRO_RECORDER_PLUS_SMOKE_EXIT_MS")
    if smoke_exit_ms:
        delay = max(0, int(smoke_exit_ms))
        QTimer.singleShot(delay, window.close)
        QTimer.singleShot(delay + 250, app.quit)
    return app.exec()
