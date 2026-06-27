from __future__ import annotations

from macro_recorder_plus.exporters.pyinstaller_exporter import pyinstaller_command, split_pyinstaller_options


def test_split_pyinstaller_options_handles_quoted_values():
    assert split_pyinstaller_options('--windowed --name "My Macro"') == ["--windowed", "--name", "My Macro"]


def test_pyinstaller_command_uses_python_module_by_default():
    program, args = pyinstaller_command(
        "macro.py",
        "dist",
        name="macro",
        python_executable=r"C:\Python312\python.exe",
        extra_args=["--windowed"],
    )

    assert program == r"C:\Python312\python.exe"
    assert args[:3] == ["-m", "PyInstaller", "--onefile"]
    assert "--windowed" in args
    assert args[-1] == "macro.py"


def test_pyinstaller_command_uses_configured_executable():
    program, args = pyinstaller_command(
        "macro.py",
        "dist",
        name="macro",
        pyinstaller_executable=r"C:\Tools\pyinstaller.exe",
    )

    assert program == r"C:\Tools\pyinstaller.exe"
    assert args[0] == "--onefile"
    assert "-m" not in args
