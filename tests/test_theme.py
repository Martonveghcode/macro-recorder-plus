from __future__ import annotations

import sys
from types import SimpleNamespace

from PySide6.QtCore import QSettings

from macro_recorder_plus.ui.theme import apply_theme, corner_shape_stylesheet, load_appearance_settings


def test_theme_defaults_to_dark_accent_and_sharp_corners(tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)

    appearance = load_appearance_settings(settings)

    assert appearance.theme_mode == "dark"
    assert appearance.primary_color == "#D0BCFF"
    assert appearance.corner_shape == "sharp"


def test_apply_theme_passes_settings_to_qdarktheme(tmp_path, monkeypatch):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    settings.setValue("appearance/theme", "dark")
    settings.setValue("appearance/primary_color", "#abcdef")
    settings.setValue("appearance/corner_shape", "rounded")
    calls = []
    fake_qdarktheme = SimpleNamespace(setup_theme=lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setitem(sys.modules, "qdarktheme", fake_qdarktheme)

    error = apply_theme(settings)

    assert error is None
    assert calls == [
        (
            ("dark",),
            {
                "custom_colors": {"primary": "#ABCDEF"},
                "corner_shape": "rounded",
                "additional_qss": corner_shape_stylesheet("rounded"),
            },
        )
    ]


def test_corner_shape_stylesheet_changes_radius():
    assert "border-radius: 0px" in corner_shape_stylesheet("sharp")
    assert "border-radius: 6px" in corner_shape_stylesheet("rounded")
