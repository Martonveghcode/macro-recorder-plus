# JSON Macro Schema

Macro files are UTF-8 JSON documents. The default extension is `.mrplus.json`.

```json
{
  "format_version": 1,
  "name": "Example Macro",
  "created_at": "2026-06-24T12:00:00+00:00",
  "updated_at": "2026-06-24T12:00:00+00:00",
  "recorded_environment": {
    "platform": "Windows",
    "virtual_desktop": {"left": 0, "top": 0, "right": 2560, "bottom": 1440},
    "monitors": [],
    "cursor_start": [100, 100]
  },
  "settings": {
    "playback_speed": 1.0,
    "macro_loop_count": 1,
    "coordinate_mode": "exact"
  },
  "pre_actions": [],
  "actions": []
}
```

`settings.macro_loop_count` repeats the complete macro during GUI playback and in exported runners. It defaults to `1` and is clamped to `1` through `99999`.

`pre_actions` uses the same action objects as `actions`, but runs once at the start of playback before the main action loop. Missing `pre_actions` in older files defaults to an empty list.

Each action contains:

- `id`: stable action identifier.
- `type`: one of `wait`, `open_url`, `open_file`, `launch_program`, `type_text`, `type_secret`, `key_press`, `hotkey`, `mouse_move`, `mouse_button`, `scroll`, `image_click`, `if_condition`, or `comment`.
- `enabled`: whether playback should execute the action.
- `delay`: seconds to wait after the previous action.
- `timestamp`: relative timestamp from recording start.
- `duration`: action duration where relevant.
- `loop_count`: how many times playback repeats this action before advancing. Values are clamped to `1` through `99999`.
- `label`: optional human-readable label.
- `params`: action-specific parameters.

Secret input actions store only an environment variable name:

```json
{
  "type": "type_secret",
  "params": {
    "environment_variable": "WEBSITE_PASSWORD"
  }
}
```

Secret actions never store the secret value in the macro file. During playback the app reads the value with `os.environ["WEBSITE_PASSWORD"]`, so it comes from the environment inherited by the running process:

- In the GUI, the shortcut-launched app reads Windows user/system environment variables that existed when the app started.
- In an exported script, a variable set in the launching terminal is also available, for example `$env:WEBSITE_PASSWORD="secret"; python exported_macro.py`.

If the value is missing, GUI playback reports an error. The exported standalone Python runner prompts for the value only when interactive terminal input is available.

Open file actions store a file path and open it with the operating system's default app:

```json
{
  "type": "open_file",
  "params": {
    "file_path": "C:\\Users\\marto\\Documents\\notes.pdf",
    "target_monitor": "default",
    "auto_focus": false,
    "window_placement": null
  }
}
```

`target_monitor` can be `default`, `primary`, or a 1-based monitor number as a string such as `"1"` or `"2"`. When `auto_focus` is true, Windows playback tries to bring the opened file or launched program window to the foreground after it appears.

When captured in the editor, `window_placement` stores the window's bounds, monitor identifier and index, monitor-relative offset, and maximized state. A saved placement takes precedence over the simpler centered `target_monitor` behavior.

Launch program actions support the same window-placement fields:

```json
{
  "type": "launch_program",
  "params": {
    "executable": "C:\\Windows\\System32\\notepad.exe",
    "arguments": "",
    "working_directory": "",
    "target_monitor": "primary",
    "auto_focus": true,
    "wait_for_startup": true,
    "startup_timeout": 10.0
  }
}
```

Image click actions store the path to a screenshot or image template plus detection and click settings:

```json
{
  "type": "image_click",
  "params": {
    "image_path": "macro_recorder_plus_assets/button.png",
    "click_action": "left_click",
    "confidence": 0.85,
    "wait_until_found": true,
    "timeout": 5.0,
    "checks_per_second": 4.0,
    "poll_interval": 0.25,
    "grayscale": true,
    "on_not_found": "error",
    "region_x": 0,
    "region_y": 0,
    "region_width": 0,
    "region_height": 0,
    "movement_start_offset": [0, 0],
    "movement_end_offset": [0, 0],
    "movement_duration": 0.5,
    "movement_button": "left",
    "movement_button_action": "none",
    "movement_path": []
  }
}
```

When exported as Python, referenced image files are copied into `macro_recorder_plus_assets` and the exported script uses the copied relative path.

`checks_per_second` controls how often the screen is checked while `wait_until_found` is enabled. A `timeout` of `0` means keep waiting until the image appears or playback is stopped. `poll_interval` is still read for older macro files.

Set `click_action` to `custom_movement` to move relative to the matched image center instead of clicking the center. `movement_start_offset` and `movement_end_offset` are `[x, y]` pixel offsets from the image center, `movement_duration` is seconds, and `movement_button_action` can be `none`, `click_at_start`, `click_at_end`, `double_click_at_start`, `double_click_at_end`, `hold_during_move`, `press_at_start`, or `release_at_end`.

Conditional image-result actions branch from the previous image click result:

```json
{
  "type": "if_condition",
  "params": {
    "image_found_action": 5,
    "image_not_found_action": 0
  }
}
```

Action numbers are 1-based table row numbers. `0` means continue normally to the next action. For the not-found branch to run, the previous `image_click` action must use `"on_not_found": "skip"`; otherwise playback stops with an image-not-found error before reaching the conditional action.
