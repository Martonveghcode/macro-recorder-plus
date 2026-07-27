from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform import windows_input
from macro_recorder_plus.platform.windows_input import ActionExecutor


def test_open_url_restores_captured_browser_window(monkeypatch):
    opened = []
    arranged = []
    placement = {
        "process_path": r"C:\Program Files\Browser\browser.exe",
        "window_title": "Browser",
        "monitor_index": 1,
        "x": 1200,
        "y": 50,
        "width": 1000,
        "height": 800,
    }
    monkeypatch.setattr(windows_input.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        windows_input,
        "_arrange_existing_window",
        lambda saved, **kwargs: arranged.append((saved, kwargs)) or True,
    )

    ActionExecutor(None, None).execute(
        MacroAction(
            type=ActionType.OPEN_URL,
            params={
                "url": "https://example.com/dashboard",
                "auto_focus": True,
                "window_placement": placement,
            },
        )
    )

    assert opened == ["https://example.com/dashboard"]
    assert arranged == [(placement, {"auto_focus": True, "timeout": 10.0})]


def test_open_url_without_saved_position_only_opens_url(monkeypatch):
    opened = []
    monkeypatch.setattr(windows_input.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        windows_input,
        "_arrange_existing_window",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("placement should not be restored")),
    )

    ActionExecutor(None, None).execute(MacroAction(type=ActionType.OPEN_URL, params={"url": "https://example.com"}))

    assert opened == ["https://example.com"]
