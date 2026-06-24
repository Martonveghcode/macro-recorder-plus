from __future__ import annotations


def play_notification() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        return
    except Exception:
        pass

    try:
        from PySide6.QtWidgets import QApplication

        QApplication.beep()
    except Exception:
        pass
