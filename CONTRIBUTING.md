# Contributing

Thanks for helping improve Macro Recorder +. Keep changes focused and verify behavior on Windows when a change touches recording, playback, hotkeys, or exporting.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

## Checks

Run these before opening a pull request:

```powershell
pytest
python -m compileall macro_recorder_plus tests
```

For headless Qt runs:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest
```

## Manual Testing

Use [docs/manual-windows-test-checklist.md](docs/manual-windows-test-checklist.md) for changes that affect global hooks, playback safety, monitor placement, image recognition, export, or packaging.

## Pull Requests

- Describe the user-facing behavior changed.
- Include tests for new or changed logic where practical.
- Note any manual Windows checks that were run.
- Do not commit exported macros, local build folders, virtual environments, or logs.

## License

This repository does not currently include a license file. Clarify licensing before reusing code outside the project or accepting external contributions.
