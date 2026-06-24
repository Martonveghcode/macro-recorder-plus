# Macro Recorder +

Macro Recorder + is a Windows-focused desktop macro recorder and player built with Python, PySide6, Qt Widgets, and pynput. It records global keyboard and mouse activity, normalizes recordings into editable actions, saves a documented JSON macro file, exports standalone Python playback scripts, and can hand those scripts to PyInstaller for optional `.exe` builds.

## Library Choices

- PySide6 and Qt Widgets provide the native desktop interface, model/view action table, menus, toolbars, dialogs, settings, and worker-thread integration required by the prompt.
- pynput provides global keyboard/mouse hooks and playback controllers without requiring a browser, server, Electron, QML, or Tkinter.
- ctypes calls declare Windows DPI awareness and inspect physical monitor layout without adding a pywin32 runtime dependency.
- PyInstaller is optional and is launched through Qt `QProcess` so build output streams into the GUI.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Run

```powershell
python -m macro_recorder_plus
```

The application declares per-monitor DPI awareness before creating `QApplication`. Global hooks may require running from a normal interactive desktop session.

## Test

```powershell
pytest
python -m compileall macro_recorder_plus tests
```

For headless Qt test runs:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest
```

## Export

Use **Export Python Script** to create a standalone `.py` macro runner. The generated script supports:

```powershell
python exported_macro.py
python exported_macro.py --speed 1.5
python exported_macro.py --dry-run
python exported_macro.py --start-action 12
```

Use **Export Windows EXE** to export the Python script first, then run PyInstaller through the GUI. PyInstaller is optional and is listed in `requirements-dev.txt`.

## Repository Structure

```text
macro_recorder_plus/
  application.py
  app.py
  exporters/
  models/
  platform/
  playback/
  recorder/
  storage/
  ui/
  utilities/
docs/
examples/
packaging/
tests/
```

## JSON Macro Schema

The schema is documented in [docs/json-schema.md](docs/json-schema.md). Macro files are UTF-8 JSON and use `format_version: 1`. Pickle and executable serialization are not used.

## Known Limitations

- The implementation records keyboard press/release events and mouse movement groups, but deeper semantic recognition of every possible shortcut is intentionally conservative.
- Display-layout transformation support includes exact/scaled coordinate modes and clamping helpers; complex per-monitor remapping should be manually checked before running destructive macros.
- PyInstaller packaging is configured but must be validated on the final target Windows machine because Qt plugin discovery can vary by Python environment.
- Secret actions read from environment variables or an interactive prompt in exported scripts; secrets are not stored in macro files.
