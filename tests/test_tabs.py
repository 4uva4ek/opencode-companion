"""The tab strip: the chosen tab is hooked onto the page it opens, not floating above it."""
import json
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from opencode_model_sync import app as application, theme, window


@pytest.fixture
def view(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    application.apply_theme(app)
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({"providers": {"local": {
        "name": "Local", "settings": {"baseURL": "http://localhost:1234/v1"}, "models": {}
    }}}))
    monkeypatch.setattr(window, "config_path", lambda: path)
    monkeypatch.setattr(window.MainWindow, "refresh", window.MainWindow._reload_config)
    monkeypatch.setattr(window.MainWindow, "refresh_workspaces", lambda self: None)

    def run(work, done, failed):
        try:
            result = work()
        except Exception as error:  # noqa: BLE001
            failed(str(error))
        else:
            done(result)

    monkeypatch.setattr(window.tasks, "run", run)
    widget = window.MainWindow()
    widget.resize(1000, 600)
    widget.show()
    spin(app)
    yield widget, app
    widget.close()
    widget.deleteLater()
    app.processEvents()


def spin(app, seconds=0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.005)


def strip_of(widget):
    return widget.tabs.parentWidget()


def pixel(widget, point):
    return widget.grab().toImage().pixelColor(point).name()


def test_the_chosen_tab_stands_on_the_line_of_the_strip(view):
    widget, app = view
    strip, bar = strip_of(widget), widget.tabs
    # The bar reaches the strip's own bottom edge, covering its line, rather than stopping above it.
    bottom = bar.mapTo(widget, QPoint(0, 0)).y() + bar.height()
    assert bottom == strip.mapTo(widget, QPoint(0, 0)).y() + strip.height()

    line = strip.height() - 1
    chosen = bar.tabRect(bar.currentIndex())
    under = strip.mapTo(widget, QPoint(chosen.center().x(), line))
    beside = strip.mapTo(widget, QPoint(bar.geometry().right() + 60, line))
    palette = theme.current()
    assert pixel(widget, under) == palette.window, "the line gives way where the tab stands"
    assert pixel(widget, beside) == palette.border, "and runs on everywhere else"


def test_the_chosen_tab_is_cut_in_the_colour_of_its_page(view):
    widget, app = view
    strip, bar = strip_of(widget), widget.tabs
    palette = theme.current()
    chosen = bar.tabRect(bar.currentIndex())
    inside = strip.mapTo(widget, QPoint(chosen.center().x(), chosen.center().y()))
    other = bar.tabRect(1 - bar.currentIndex())
    away = strip.mapTo(widget, QPoint(other.center().x(), other.center().y()))
    assert pixel(widget, inside) == palette.window, "the chosen tab is the page colour"
    assert pixel(widget, away) == palette.sidebar, "the rest of the strip is the chrome colour"
