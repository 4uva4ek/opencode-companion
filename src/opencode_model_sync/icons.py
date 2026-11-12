"""Line icons drawn from inline SVG, tinted to the current palette."""

from __future__ import annotations

import tempfile
from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "down": '<path d="M6 9l6 6 6-6"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/>'
    '<path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 4v5h-5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "folder": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    # The third state of a check box: neither a mark nor a blank, but a word left unsaid.
    "dash": '<path d="M7 12h10"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/>'
    '<path d="M15.5 4.7a3.5 3.5 0 0 1 0 6.6"/><path d="M18 14.3a6.5 6.5 0 0 1 3.5 5.7"/>',
    "server":'<rect x="4" y="4" width="16" height="7" rx="2"/><rect x="4" y="13" width="16" height="7" rx="2"/>'
    '<path d="M8 7.5h.01M8 16.5h.01"/>',
    # Feather's "settings": the gear the model row ends with, drawn in the same 24-unit grid.
    "gear": '<circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 '
    '1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 1 9 '
    '19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 '
    '.33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 1 4.6 9a1.65 1.65 '
    '0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 '
    '1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 '
    '1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 '
    '0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
}

_LOGO = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8b7bff"/><stop offset="1" stop-color="#4f46e5"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="16" fill="url(#g)"/>
  <g fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M45 29a13 13 0 0 0-23.2-7.9L19 24"/><path d="M19 17v7h7"/>
    <path d="M19 35a13 13 0 0 0 23.2 7.9L45 40"/><path d="M45 47v-7h-7"/>
  </g>
</svg>
"""


def svg(name: str, color: str, stroke: float = 2.0) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</svg>'
    )


def _render(source: str, size: int) -> QPixmap:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(QByteArray(source.encode())).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QPixmap.fromImage(image)


@cache
def icon(name: str, color: str) -> QIcon:
    result = QIcon()
    for size in (16, 20, 32, 40):
        result.addPixmap(_render(svg(name, color), size))
    return result


@cache
def logo() -> QIcon:
    result = QIcon()
    for size in (16, 22, 24, 32, 48, 64, 128, 256):
        result.addPixmap(_render(_LOGO, size))
    return result


@cache
def logo_app() -> QIcon:
    """The logo on Apple's icon grid. Qt hands the window icon to the macOS Dock, which
    scales the whole image into the tile, so this variant carries the same ~10% of air
    around the tile that every system icon has; the full-bleed logo() would render
    noticeably larger than its neighbours while the app runs."""
    result = QIcon()
    for size in (16, 32, 64, 128, 256, 512):
        tile = _render(_LOGO, round(size * 0.86))  # 0.805/0.9375: visible tile at 80.5%
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        offset = (size - tile.width()) // 2
        painter.drawPixmap(offset, offset, tile)
        painter.end()
        result.addPixmap(canvas)
    return result


def logo_svg() -> str:
    return _LOGO


@cache
def check_file(color: str) -> str:
    """Style sheets take images by path, so the checkmark is written to a temp file once."""
    path = Path(tempfile.gettempdir()) / f"opencode-model-sync-check-{color.strip('#')}.svg"
    path.write_text(svg("check", color, 3.0), encoding="utf-8")
    return path.as_posix()


@cache
def dash_file(color: str) -> str:
    """The dash a check box shows when the config never chose one way or the other."""
    path = Path(tempfile.gettempdir()) / f"opencode-model-sync-dash-{color.strip('#')}.svg"
    path.write_text(svg("dash", color, 3.0), encoding="utf-8")
    return path.as_posix()


@cache
def down_file(color: str) -> str:
    path = Path(tempfile.gettempdir()) / f"opencode-model-sync-down-{color.strip('#')}.svg"
    path.write_text(svg("down", color), encoding="utf-8")
    return path.as_posix()
