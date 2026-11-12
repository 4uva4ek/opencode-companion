"""Application entry point: theme, main window and the tray icon."""

from __future__ import annotations

import sys

from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import i18n, icons, theme
from .i18n import tr
from .instance import SingleInstance
from .window import MainWindow

# Keep the settings namespace so upgrades retain language and user preferences.
APP_ID = "opencode-model-sync"


class TrayWindow(MainWindow):
    """Closing the window hides it to the tray while a tray icon is available."""

    def __init__(self, tray: QSystemTrayIcon | None) -> None:
        super().__init__()
        self.tray = tray
        self.hinted = False

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.tray or not self.tray.isVisible():
            event.accept() if self.confirm_quit() else event.ignore()
            return
        event.ignore()
        self.hide()
        if not self.hinted:
            self.hinted = True
            self.tray.showMessage("Companion", tr("app.trayHint"), icons.logo(), 3000)


def apply_theme(app: QApplication) -> None:
    palette = theme.current()
    app.setStyleSheet(theme.style_sheet(palette, icons.check_file(palette.accent_text)))


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    # QStandardPaths includes the application name. Acquire the existing lock
    # under the old name so Companion and Model Sync cannot edit in parallel.
    app.setApplicationName("OpenCode Model Sync")
    app.setOrganizationName(APP_ID)
    try:
        instance = SingleInstance()
        if not instance.acquire():
            return 0
    except (OSError, RuntimeError) as error:
        QMessageBox.critical(None, "OpenCode Companion", str(error))
        return 1
    app.setApplicationName("OpenCode Companion")
    app.setDesktopFileName("opencode-companion")
    app.setWindowIcon(icons.logo_app())
    app.setStyle("Fusion")
    apply_theme(app)
    settings = QSettings(APP_ID, APP_ID)
    i18n.set_language(str(settings.value("language", "")) or i18n.detect(QLocale.system().uiLanguages()))

    tray = QSystemTrayIcon(icons.logo()) if QSystemTrayIcon.isSystemTrayAvailable() else None
    window = TrayWindow(tray)

    def show_window() -> None:
        if window.isMinimized():
            window.showNormal()
        else:
            window.show()
        window.raise_()
        window.activateWindow()

    instance.activated.connect(show_window)
    app.aboutToQuit.connect(instance.close)

    def restyle(_scheme: object) -> None:
        apply_theme(app)
        icons.icon.cache_clear()
        window.render()

    app.styleHints().colorSchemeChanged.connect(restyle)
    window.language_changed.connect(lambda: settings.setValue("language", i18n.language()))

    if tray:
        menu = QMenu()
        open_action = QAction(tr("tray.open"), menu)
        open_action.triggered.connect(show_window)
        sync_action = QAction(tr("tray.syncAll"), menu)
        sync_action.triggered.connect(window.sync_all)
        quit_action = QAction(tr("tray.quit"), menu)
        quit_action.triggered.connect(lambda: app.quit() if window.confirm_quit() else None)
        menu.addAction(open_action)
        menu.addAction(sync_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        def retranslate() -> None:
            open_action.setText(tr("tray.open"))
            sync_action.setText(tr("tray.syncAll"))
            quit_action.setText(tr("tray.quit"))

        window.language_changed.connect(retranslate)
        tray.setContextMenu(menu)
        tray.setToolTip("OpenCode Companion")
        tray.activated.connect(
            lambda reason: show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        window.synced.connect(lambda message: tray.showMessage("Companion", message, icons.logo(), 4000))
        tray.show()
        app.setQuitOnLastWindowClosed(False)

    window.show()
    try:
        return app.exec()
    finally:
        instance.close()
