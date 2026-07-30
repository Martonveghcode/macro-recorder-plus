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
- Open a saved macro with at least two actions, record another click, and confirm the new actions append without a save/discard prompt or loss of existing rows.
- For **Find Image and Click**, pick a 100px start circle, set a 5px click circle, and confirm repeated runs start/end at different in-circle points along smooth paths.
- Run three consecutive natural **Find Image and Click** actions and confirm exactly two smooth 0.3–0.8 second bridges occur between click endpoints and the following randomized start-circle points, with no teleport.
- Preview the red click circle over the chosen image and verify its dot follows the configured X/Y click offset.
- Select an image-search region on a scaled or secondary monitor (including a monitor left of the primary) and confirm the image is found inside that region.
- Set Macro loops to 3 and Between loops to a 1–2 second random range; confirm two independently chosen waits occur and no wait follows the final loop.
- Click an action, confirm the high-contrast properties panel opens over the table, close it, and confirm no idle properties-arrow button remains on the page.
- Change monitor configuration after recording and confirm the display-layout warning appears.
