# Macro Recorder +

Macro Recorder + is a small desktop macro recorder for keyboard and mouse workflows. It records global keyboard and mouse events, shows them in an editable event list, plays them back with loop and speed controls, and saves macros as JSON-based `.mrplus` files.

## Features

- Record keyboard presses/releases, mouse clicks, wheel scrolls, and optional pointer movement.
- Play macros back with configurable speed and repeat count.
- Save and load macros as portable `.mrplus` files.
- Delete selected events and clear recordings from the event list.
- Global controls: `F8` toggles recording, and `F9` stops playback.
- Countdown before recording or playback so you can switch to the target app.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python -m macro_recorder_plus
```

On macOS and some Linux desktops, global keyboard and mouse capture may require accessibility/input-monitoring permissions for the Python interpreter or terminal.

## Test

```powershell
python -m unittest
```

## Macro Format

Macros are saved as UTF-8 JSON with a schema version, macro metadata, and an ordered list of timestamped events. The extension `.mrplus` is used by convention; the files remain plain JSON.
