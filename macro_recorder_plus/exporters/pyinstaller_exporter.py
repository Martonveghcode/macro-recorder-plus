from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


class PyInstallerExporter(QObject):
    output = Signal(str)
    finished = Signal(bool, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None

    def build(self, script_path: str | Path, output_dir: str | Path, *, name: str = "exported_macro") -> None:
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setArguments(
            [
                "-m",
                "PyInstaller",
                "--onefile",
                "--name",
                name,
                "--distpath",
                str(output_dir),
                str(script_path),
            ]
        )
        self.process.readyReadStandardOutput.connect(
            lambda: self.output.emit(bytes(self.process.readAllStandardOutput()).decode(errors="replace"))
        )
        self.process.readyReadStandardError.connect(
            lambda: self.output.emit(bytes(self.process.readAllStandardError()).decode(errors="replace"))
        )
        self.process.finished.connect(lambda code, _status: self.finished.emit(code == 0, code))
        self.process.start()
