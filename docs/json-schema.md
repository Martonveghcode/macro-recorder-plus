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
    "coordinate_mode": "exact"
  },
  "actions": []
}
```

Each action contains:

- `id`: stable action identifier.
- `type`: one of `wait`, `open_url`, `launch_program`, `type_text`, `type_secret`, `key_press`, `hotkey`, `mouse_move`, `mouse_button`, `scroll`, or `comment`.
- `enabled`: whether playback should execute the action.
- `delay`: seconds to wait after the previous action.
- `timestamp`: relative timestamp from recording start.
- `duration`: action duration where relevant.
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

The exported standalone Python runner resolves the secret from the environment first, then prompts when interactive execution is available.
