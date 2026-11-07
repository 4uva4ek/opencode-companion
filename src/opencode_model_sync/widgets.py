"""Small widgets and helpers shared by the windows and dialogs."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea, QSizePolicy, QWidget

from . import icons, theme


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def scrolled(widget: QWidget) -> QScrollArea:
    """A list that scrolls vertically and never sideways, without a frame of its own."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(widget)
    return scroll


class WrappedLabel(QLabel):
    """A label that keeps every line its text needs.

    A layout asks a wrapping label how tall it would like to be before it has decided how wide the
    label will be, so the answer comes back as one line and the second line is painted below the
    widget's bottom edge — out of sight, with the word cut in half. This label answers once the
    width is known instead and raises its own floor to the height the words take, so the row it
    stands in grows rather than losing the end of the sentence.
    """

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # An empty label answers "no height at all", and a negative minimum is not a thing: only a
        # real number of lines is worth raising the floor to.
        needed = self.heightForWidth(self.width())
        if needed > 0 and needed != self.minimumHeight():
            self.setMinimumHeight(needed)


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    widget = WrappedLabel(text) if wrap else QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


class ElidedLabel(QLabel):
    """A label that shortens its text with an ellipsis instead of widening its parent."""

    def __init__(self, text: str, name: str | None = None, mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight) -> None:
        super().__init__()
        self.full = text
        self.mode = mode
        if name:
            self.setObjectName(name)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(30)
        self.setToolTip(text)
        self.setText(text)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full, self.mode, self.width()))


def pill(text: str, tone: str) -> QLabel:
    widget = label(text, "pill")
    widget.setProperty("tone", tone)
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return widget


def button(text: str, name: str | None = None, icon_name: str | None = None, color: str | None = None) -> QPushButton:
    widget = QPushButton(text)
    if name:
        widget.setObjectName(name)
    if icon_name:
        palette = theme.current()
        tint = color or (palette.accent_text if name == "primary" else palette.muted)
        widget.setIcon(icons.icon(icon_name, tint))
        widget.setIconSize(QSize(16, 16))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def tokens(count: int) -> str:
    return f"{count // 1024}K" if count >= 1024 and count % 1024 == 0 else f"{round(count / 1000)}K"
