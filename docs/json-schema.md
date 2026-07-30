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
    "macro_loop_delay_mode": "random",
    "macro_loop_delay_min": 1.0,
    "macro_loop_delay_max": 2.0,
    "coordinate_mode": "exact"
  },
  "pre_actions": [],
  "actions": []
}
```

`settings.macro_loop_count` repeats the complete macro during GUI playback and in exported runners. It defaults to `1` and is clamped to `1` through `99999`.

`settings.macro_loop_delay_mode` is `none`, `fixed`, or `random`. `macro_loop_delay_min` and `macro_loop_delay_max` are seconds, clamped to `0` through `86400`. A fresh random duration is selected between completed whole-macro loops; no delay is added after the final loop. Missing fields in older macros default to `none` and do not change their playback.

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

Newly recorded mouse movements opt into varied playback on each run:

```json
{
  "type": "mouse_move",
  "duration": 0.75,
  "params": {
    "start": [100, 100],
    "end": [500, 300],
    "path": [[100, 100, 0.0], [500, 300, 0.75]],
    "coordinate_mode": "exact",
    "humanize_playback": true
  }
}
```

`humanize_playback` adds a smooth variation of up to 2 pixels around the recorded path, selects an endpoint within a 5-pixel-radius circle, and makes the movement 0.1 to 0.2 seconds faster or slower. A following click, release, or scroll at the recorded endpoint uses the same varied destination. The field is absent from older macros, which preserves their exact playback behavior.

New image-click actions can use circle-based natural movement:

```json
{
  "type": "image_click",
  "params": {
    "image_path": "button.png",
    "click_action": "left_click",
    "natural_movement": true,
    "movement_start_mode": "screen",
    "movement_start_center": [800, 500],
    "movement_start_radius": 100,
    "click_offset": [0, 0],
    "click_radius": 5,
    "path_variance": 8.0,
    "movement_duration": 0.75
  }
}
```

`movement_start_mode` is `cursor` or `screen`. The start point is chosen inside `movement_start_radius` around the current cursor or `movement_start_center`. The final point is chosen inside `click_radius` around the matched image center plus `click_offset`. `path_variance` adds a smooth curved deviation rather than per-pixel jitter. Imported actions without `natural_movement` retain their previous exact or legacy custom-offset behavior.

When two enabled image-click actions with natural movement run consecutively, playback automatically bridges the first click point to the next randomized start-circle point with a smooth 0.3 to 0.8 second transition. Three consecutive image actions produce two bridges. This behavior has no separate macro setting and does not affect a standalone image action or legacy actions without `natural_movement`.

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
