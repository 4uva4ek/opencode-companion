"""Colors and the Qt style sheet, in a dark and a light variant that follow the system scheme."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Palette:
    window: str
    sidebar: str
    surface: str
    surface_hover: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str


DARK = Palette(
    window="#111318",
    sidebar="#0c0e12",
    surface="#181b22",
    surface_hover="#1f232c",
    border="#262a34",
    text="#e8eaf0",
    muted="#9aa1b1",
    faint="#636a7a",
    accent="#7c6cf2",
    accent_hover="#8e80f5",
    accent_text="#ffffff",
    accent_soft="rgba(124, 108, 242, 15%)",
    success="#3ecf8e",
    success_soft="rgba(62, 207, 142, 13%)",
    warning="#f2b84b",
    warning_soft="rgba(242, 184, 75, 13%)",
    danger="#f2665f",
    danger_soft="rgba(242, 102, 95, 13%)",
)

LIGHT = Palette(
    window="#f6f7fb",
    sidebar="#eceef5",
    surface="#ffffff",
    surface_hover="#f1f2f8",
    border="#dfe2ec",
    text="#171a21",
    muted="#5d6475",
    faint="#8f96a6",
    accent="#5b4ce0",
    accent_hover="#4c3dd1",
    accent_text="#ffffff",
    accent_soft="rgba(91, 76, 224, 12%)",
    success="#169c62",
    success_soft="rgba(22, 156, 98, 11%)",
    warning="#b7791f",
    warning_soft="rgba(183, 121, 31, 12%)",
    danger="#d23c35",
    danger_soft="rgba(210, 60, 53, 10%)",
)


def current() -> Palette:
    hints = QGuiApplication.styleHints()
    return LIGHT if hints.colorScheme() == Qt.ColorScheme.Light else DARK


def style_sheet(p: Palette, check: str) -> str:
    from .icons import dash_file, down_file
    arrow = down_file(p.muted)
    dash = dash_file(p.muted)
    return f"""
* {{
    font-size: 13px;
    color: {p.text};
}}
QMainWindow, #content {{ background: {p.window}; }}
#sidebar {{ background: {p.sidebar}; border-right: 1px solid {p.border}; }}
#tabStrip {{ background: {p.sidebar}; border-bottom: 1px solid {p.border}; }}
QToolTip {{ background: {p.surface}; color: {p.text}; border: 1px solid {p.border}; padding: 6px 8px; border-radius: 6px; }}

/* The bar reaches one pixel past the bottom of the strip so the chosen tab can stand on it. */
QTabBar#tabs, QTabWidget > QTabBar {{ background: transparent; margin-bottom: -1px; }}
QTabBar#tabs::tab, QTabWidget > QTabBar::tab {{
    background: transparent;
    color: {p.muted};
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 7px 14px;
    font-weight: 600;
}}
QTabBar#tabs::tab:hover, QTabWidget > QTabBar::tab:hover {{ color: {p.text}; background: {p.surface_hover}; }}
/* The chosen tab is outlined on three sides only: along the bottom it becomes the page under it. */
QTabBar#tabs::tab:selected, QTabWidget > QTabBar::tab:selected {{
    color: {p.text};
    background: {p.window};
    border: 1px solid {p.border};
    border-bottom: none;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    padding-bottom: 8px;
}}

/* Tabs that divide one window rather than the whole app wear the same pills as the strip above.
   The frame is only the line they stand on, and it runs from edge to edge as the strip's line does;
   the chosen tab is the same colour as the page, so it merges into it. The bar alone steps back
   inside, by the room the dialog keeps at its sides, so no tab sits on the corner of the window. */
QTabWidget::pane {{ border: none; border-top: 1px solid {p.border}; background: transparent; }}
QTabWidget::tab-bar {{ left: 18px; }}

#brand {{ font-size: 16px; font-weight: 700; }}
#brandSub {{ color: {p.faint}; font-size: 12px; }}
#sectionLabel {{ color: {p.faint}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}

QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border: none; padding: 0; margin: 0; }}
QListWidget::item:selected {{ background: transparent; }}

#providerCard {{ background: transparent; border-radius: 10px; }}
#providerCard[hover="true"] {{ background: {p.surface_hover}; }}
#providerCard[selected="true"] {{ background: {p.surface}; border: 1px solid {p.border}; }}
#providerName {{ font-weight: 600; }}
#providerUrl {{ color: {p.faint}; font-size: 11px; }}
#countBadge {{ color: {p.muted}; background: {p.surface_hover}; border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 600; }}

#title {{ font-size: 22px; font-weight: 700; }}
#subtitle {{ color: {p.muted}; }}
#mono {{ font-family: "JetBrains Mono", "SF Mono", "Cascadia Mono", "Consolas", monospace; color: {p.muted}; font-size: 12px; }}
#configPath {{ color: {p.faint}; font-size: 12px; }}

QPushButton {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {p.surface_hover}; }}
QPushButton:disabled {{ color: {p.faint}; }}
QPushButton#primary {{ background: {p.accent}; border-color: {p.accent}; color: {p.accent_text}; }}
QPushButton#primary:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#primary:disabled {{ background: {p.accent_soft}; border-color: transparent; color: {p.faint}; }}
QPushButton#danger {{ color: {p.danger}; }}
QPushButton#danger:hover {{ background: {p.danger_soft}; }}
QPushButton#ghost {{ background: transparent; border: none; color: {p.muted}; padding: 6px 8px; }}
QPushButton#ghost:hover {{ color: {p.text}; background: {p.surface_hover}; }}
QPushButton#link {{ background: transparent; border: none; color: {p.accent}; padding: 0; font-weight: 500; }}
QPushButton#link:hover {{ color: {p.accent_hover}; text-decoration: underline; }}

#modelList {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; }}
#modelRow {{ border-bottom: 1px solid {p.border}; }}
#modelRow[last="true"] {{ border-bottom: none; }}
#modelName {{ font-weight: 600; }}
/* A model opencode has been told not to offer reads as a name that is put away. */
#modelRow[off="true"] #modelName {{ color: {p.muted}; }}

QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.faint}; background: transparent; }}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({check}); }}
/* A dash, not an empty box: the third state says the config never chose, which is its own answer. */
QCheckBox::indicator:indeterminate {{ border-color: {p.muted}; image: url({dash}); }}
QCheckBox::indicator:disabled {{ border-color: {p.border}; }}

/* A slider is a range made visible: the groove is the whole of it, the filled part says how far
   along the value sits, and the two ends are printed beside it as words. The groove is painted in
   the faintest ink the palette has, because a range nobody can see cannot be aimed at. The handle
   is wider than the groove it rides, so the control keeps a little room at its own sides: without
   it the handle at the first or the last step hangs past the widget and is drawn in half. */
QSlider {{ background: transparent; padding: 0 8px; }}
QSlider::groove:horizontal {{ height: 4px; border: none; border-radius: 2px; background: {p.faint}; }}
QSlider::sub-page:horizontal {{ height: 4px; border-radius: 2px; background: {p.accent}; }}
QSlider::add-page:horizontal {{ height: 4px; border-radius: 2px; background: {p.faint}; }}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -5px -7px;
    border: none;
    border-radius: 7px;
    background: {p.text};
}}
QSlider::handle:horizontal:hover {{ background: {p.accent_hover}; }}
/* A field left to the provider is greyed, but the range it would have used stays readable: the
   groove darkens and the handle keeps a colour of its own instead of vanishing into it. */
QSlider::groove:horizontal:disabled, QSlider::add-page:horizontal:disabled,
QSlider::sub-page:horizontal:disabled {{ background: {p.border}; }}
QSlider::handle:horizontal:disabled {{ background: {p.muted}; }}

#pill {{ border-radius: 9px; padding: 2px 9px; font-size: 11px; font-weight: 600; }}
QPushButton#pill {{ border: 1px solid transparent; }}
QPushButton#pill:hover {{ border-color: {p.faint}; }}
#pill[tone="accent"] {{ color: {p.accent}; background: {p.accent_soft}; }}
#pill[tone="success"] {{ color: {p.success}; background: {p.success_soft}; }}
#pill[tone="warning"] {{ color: {p.warning}; background: {p.warning_soft}; }}
#pill[tone="danger"] {{ color: {p.danger}; background: {p.danger_soft}; }}
#pill[tone="muted"] {{ color: {p.muted}; background: {p.surface_hover}; }}

#banner {{ border-radius: 10px; padding: 10px 14px; }}
#banner[tone="success"] {{ background: {p.success_soft}; color: {p.success}; }}
#banner[tone="danger"] {{ background: {p.danger_soft}; color: {p.danger}; }}
#banner[tone="accent"] {{ background: {p.accent_soft}; color: {p.accent}; }}
#banner[tone="success"] QLabel {{ color: {p.success}; background: transparent; }}
#banner[tone="danger"] QLabel {{ color: {p.danger}; background: transparent; }}
#banner[tone="accent"] QLabel {{ color: {p.accent}; background: transparent; }}

#suggestion {{ background: {p.accent_soft}; border-radius: 10px; }}
#suggestionText {{ color: {p.text}; font-size: 12px; }}

#empty {{ color: {p.faint}; font-size: 14px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.faint}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QDialog {{ background: {p.window}; }}
QLineEdit {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {p.accent};
}}
QLineEdit:focus {{ border-color: {p.accent}; }}
QLineEdit:disabled {{ color: {p.faint}; }}
/* There is deliberately no QSpinBox rule here. A spin box takes its digits from its own palette,
   which a style sheet does not move, so a dark field came out with black ink in it. The fields of
   this app are line edits, and window.CountField is the one of them that holds a number. */
QPlainTextEdit {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {p.accent};
}}
QPlainTextEdit:focus {{ border-color: {p.accent}; }}
QComboBox {{
    background: {p.surface};
    border: 1px solid {p.border};
    border-radius: 8px;
    padding: 7px 10px;
}}
QComboBox:hover {{ background: {p.surface_hover}; }}
QComboBox:disabled {{ color: {p.faint}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({arrow}); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.border};
    selection-background-color: {p.surface_hover};
    selection-color: {p.text};
    outline: none;
}}
#workerRow {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
#settingRow {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
#settingsNotice {{ color: {p.warning}; background: {p.warning_soft}; border-radius: 8px; padding: 10px; }}
QListWidget#settingsCategories {{ background: transparent; border: none; outline: none; }}
QListWidget#settingsCategories::item {{ padding: 10px 8px; border-radius: 7px; }}
QListWidget#settingsCategories::item:selected {{ background: {p.accent_soft}; color: {p.accent}; }}
QListWidget#settingsCollection {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 5px; }}
QListWidget#settingsCollection::item {{ padding: 9px; border-radius: 6px; }}
QListWidget#settingsCollection::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QListWidget#settingsCollection::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {p.faint}; }}
QListWidget#settingsCollection::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; image: url({check}); }}
QTreeWidget#pickerList {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; padding: 4px; outline: none; }}
QTreeWidget#pickerList::item {{ padding: 7px 10px; border: none; border-radius: 6px; }}
QTreeWidget#pickerList::item:hover {{ background: {p.surface_hover}; }}
QTreeWidget#pickerList::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}
QTreeWidget#pickerList::branch:selected {{ background: {p.accent_soft}; }}
#fieldLabel {{ color: {p.muted}; font-size: 12px; font-weight: 600; }}
#hint {{ color: {p.faint}; font-size: 12px; }}
#error {{ color: {p.danger}; font-size: 12px; }}

QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p.surface_hover}; }}
"""
