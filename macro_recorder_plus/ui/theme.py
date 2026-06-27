from __future__ import annotations

import re
from dataclasses import dataclass

from PySide6.QtCore import QSettings


DEFAULT_THEME_MODE = "dark"
DEFAULT_PRIMARY_COLOR = "#D0BCFF"
DEFAULT_CORNER_SHAPE = "sharp"
THEME_MODES = ("dark", "light", "auto")
CORNER_SHAPES = ("sharp", "rounded")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class AppearanceSettings:
    theme_mode: str = DEFAULT_THEME_MODE
    primary_color: str = DEFAULT_PRIMARY_COLOR
    corner_shape: str = DEFAULT_CORNER_SHAPE


def load_appearance_settings(settings: QSettings) -> AppearanceSettings:
    theme_mode = str(settings.value("appearance/theme", DEFAULT_THEME_MODE))
    primary_color = str(settings.value("appearance/primary_color", DEFAULT_PRIMARY_COLOR)).strip()
    corner_shape = str(settings.value("appearance/corner_shape", DEFAULT_CORNER_SHAPE))
    if theme_mode not in THEME_MODES:
        theme_mode = DEFAULT_THEME_MODE
    if not HEX_COLOR_RE.fullmatch(primary_color):
        primary_color = DEFAULT_PRIMARY_COLOR
    if corner_shape not in CORNER_SHAPES:
        corner_shape = DEFAULT_CORNER_SHAPE
    return AppearanceSettings(theme_mode=theme_mode, primary_color=primary_color.upper(), corner_shape=corner_shape)


def corner_shape_stylesheet(corner_shape: str) -> str:
    radius = "6px" if corner_shape == "rounded" else "0px"
    return (
        "QPushButton, QToolButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, "
        "QPlainTextEdit, QTabBar::tab {"
        f"border-radius: {radius};"
        "}"
    )


def apply_theme(settings: QSettings) -> str | None:
    appearance = load_appearance_settings(settings)
    try:
        import qdarktheme
    except ImportError:
        return "PyQtDarkTheme is not installed. Install pyqtdarktheme-fork to enable the app theme."

    setup_theme = getattr(qdarktheme, "setup_theme", None)
    if setup_theme is None:
        return "The installed PyQtDarkTheme package is too old. Install pyqtdarktheme-fork 2.3.6 or newer."

    try:
        setup_theme(
            appearance.theme_mode,
            custom_colors={"primary": appearance.primary_color},
            corner_shape=appearance.corner_shape,
            additional_qss=corner_shape_stylesheet(appearance.corner_shape),
        )
    except (TypeError, ValueError, KeyError) as exc:
        return f"The installed PyQtDarkTheme package does not support these appearance settings: {exc}"
    return None
