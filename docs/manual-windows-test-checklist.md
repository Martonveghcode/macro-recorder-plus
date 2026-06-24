# Manual Windows Test Checklist

Run these checks on Windows 10 or Windows 11 before trusting a macro for destructive workflows.

- Start the app from source with `python -m macro_recorder_plus`.
- Confirm the UI opens as a native Qt Widgets window with menu bar, toolbar, action table, properties panel, and status bar.
- Verify recording at 100%, 125%, and 150% display scaling.
- Verify recording on a 2560x1440 monitor at 125% scaling.
- Verify two monitors with different scaling.
- Verify a secondary monitor positioned left of the primary monitor, producing negative coordinates.
- Record mouse dragging and confirm it appears as grouped `mouse_move` plus button actions.
- Record vertical and horizontal scrolling.
- Record Ctrl+V, Ctrl+Shift+T, Alt+Tab, function keys, arrows, Enter, Escape, Delete, Home, and End.
- Cancel recording during countdown.
- Stop recording through the configured global hotkey.
- Start playback, pause playback, resume playback, and use the emergency-stop hotkey.
- Save, reopen, and edit a macro.
- Confirm unsaved-change prompts appear on open/exit.
- Confirm recent files are maintained.
- Export a Python script and run `--dry-run`.
- Export a Windows `.exe` through PyInstaller and inspect build output.
- Change monitor configuration after recording and confirm the display-layout warning appears.
