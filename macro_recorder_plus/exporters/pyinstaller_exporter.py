from __future__ import annotations

import shlex
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal


def split_pyinstaller_options(options: str) -> list[str]:
    value = str(options or "").strip()
    return shlex.split(value) if value else []


def pyinstaller_command(
    script_path: str | Path,
    output_dir: str | Path,
    *,
    name: str = "exported_macro",
    python_executable: str | Path | None = None,
    pyinstaller_executable: str | Path | None = None,
    extra_args: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, list[str]]:
    args = [
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(output_dir),
        *(extra_args or []),
        str(script_path),
    ]
    if pyinstaller_executable:
        return str(pyinstaller_executable), args
    return str(python_executable or sys.executable), ["-m", "PyInstaller", *args]


class PyInstallerExporter(QObject):
    output = Signal(str)
    finished = Signal(bool, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None

    def build(
        self,
        script_path: str | Path,
        output_dir: str | Path,
        *,
        name: str = "exported_macro",
        python_executable: str | Path | None = None,
        pyinstaller_executable: str | Path | None = None,
        extra_args: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        program, arguments = pyinstaller_command(
            script_path,
            output_dir,
            name=name,
            python_executable=python_executable,
            pyinstaller_executable=pyinstaller_executable,
            extra_args=extra_args,
        )
        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(arguments)
        self.process.readyReadStandardOutput.connect(
            lambda: self.output.emit(bytes(self.process.readAllStandardOutput()).decode(errors="replace"))
        )
        self.process.readyReadStandardError.connect(
            lambda: self.output.emit(bytes(self.process.readAllStandardError()).decode(errors="replace"))
        )
        self.process.finished.connect(lambda code, _status: self.finished.emit(code == 0, code))
        self.process.start()
