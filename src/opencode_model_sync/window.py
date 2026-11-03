"""Main navigation: providers, workspaces, agents, MCP and configuration."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QFileSystemWatcher, QDir, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QEnterEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMenu,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from . import agents, catalog, discovery, i18n, icons, tasks, theme, workspaces, vision
from .agents_view import AgentDialog, AgentsPanel, ModelList, TeamDialog
from .config import ConfigError, OpencodeConfig, Provider, config_path
from .discovery import Discovery, ModelRow, RemoteModel, Suggestion
from .i18n import tr
from .widgets import ElidedLabel, button, label, pill, repolish, scrolled, tokens
from .workspaces_view import WorkspacesPanel
from .settings_view import SettingsPanel
from .settings_text import t as settings_text
from .version import VERSION

# opencode wants to be told twice before it drops a worktree that holds changes.
FORCE_NEEDED = "force"


def host(url: str | None) -> str:
    parsed = urlparse(url or "")
    return parsed.netloc or (url or "")


class ProviderCard(QFrame):
    """One provider in the sidebar, with a status dot and a model count."""

    clicked = Signal(str)

    def __init__(self, provider: Provider, result: Discovery | None) -> None:
        super().__init__()
        self.provider_id = provider.id
        self.setObjectName("providerCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        palette = theme.current()
        color = palette.faint if result is None else palette.success if result.ok else palette.danger
        dot = label("●")
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        dot.setToolTip(
            tr("card.checking") if result is None else tr("card.online") if result.ok else tr("card.offline", error=result.error)
        )
        name = ElidedLabel(provider.title, "providerName")
        url = ElidedLabel(host(provider.base_url), "providerUrl")
        count = label(str(len(provider.models)), "countBadge")
        count.setToolTip(tr("card.count"))
        count.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        new = len([m for m in (result.models if result and result.ok else []) if m.id not in provider.models])

        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(name)
        text.addWidget(url)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        if provider.untranslatable:
            stuck = pill("V1", "warning")
            stuck.setToolTip(tr("card.stuckInLegacy", keys=", ".join(provider.untranslatable)))
            layout.addWidget(stuck)
        if new:
            badge = pill(f"+{new}", "accent")
            badge.setToolTip(tr("card.new"))
            layout.addWidget(badge)
        layout.addWidget(count)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)

    def enterEvent(self, event: QEnterEvent) -> None:
        self.setProperty("hover", True)
        repolish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hover", False)
        repolish(self)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self.provider_id)
        super().mousePressEvent(event)


class NavCard(QFrame):
    """A sidebar entry that opens a page rather than a provider."""

    clicked = Signal()

    def __init__(self, title: str, hint: str, icon_name: str, count: int) -> None:
        super().__init__()
        self.setObjectName("providerCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(hint)
        glyph = QLabel()
        glyph.setPixmap(icons.icon(icon_name, theme.current().muted).pixmap(16, 16))
        badge = label(str(count), "countBadge")
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        layout.addWidget(glyph)
        layout.addWidget(ElidedLabel(title, "providerName"), 1)
        layout.addWidget(badge)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)

    def enterEvent(self, event: QEnterEvent) -> None:
        self.setProperty("hover", True)
        repolish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hover", False)
        repolish(self)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class SuggestionCard(QFrame):
    added = Signal(object)

    def __init__(self, suggestion: Suggestion) -> None:
        super().__init__()
        self.setObjectName("suggestion")
        text = label(f"<b>{suggestion.name}</b><br>{host(suggestion.base_url)} · {tr('suggestion.models', count=suggestion.count)}")
        text.setObjectName("suggestionText")
        add = button(tr("suggestion.add"), "link")
        add.clicked.connect(lambda: self.added.emit(suggestion))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.addWidget(text, 1)
        layout.addWidget(add)


class ModelRowWidget(QFrame):
    toggled = Signal()
    tools_toggled = Signal(str, bool)
    visibility_toggled = Signal(str, bool)
    vision_toggled = Signal(str, bool)
    vision_probe = Signal(str)

    def __init__(self, row: ModelRow, checked: bool, last: bool) -> None:
        super().__init__()
        self.row = row
        self.setObjectName("modelRow")
        self.setProperty("last", last)
        self.setProperty("off", not row.visible)
        self.model_switch: QPushButton | None = None  # only a model in the config can be switched
        self.tools_switch: QPushButton | None = None
        self.vision_switch: QPushButton | None = None
        self.check = QCheckBox()
        self.check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check.setChecked(checked)
        self.check.toggled.connect(lambda _checked: self.toggled.emit())

        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(ElidedLabel(row.name, "modelName"))
        if row.name != row.id:
            names.addWidget(ElidedLabel(row.id, "mono", Qt.TextElideMode.ElideMiddle))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 11)
        layout.setSpacing(12)
        layout.addWidget(self.check)
        layout.addLayout(names, 1)
        remote = row.remote
        if remote and remote.context:
            chip = pill(tokens(remote.context), "muted")
            chip.setToolTip(tr("row.context", count=f"{remote.context:,}".replace(",", " ")))
            layout.addWidget(chip)
        if row.in_config:
            self.model_switch = self._switch("row.display", row.visible,
                tr("row.visibleHint" if row.visible else "row.hiddenHint"))
            self.model_switch.clicked.connect(lambda value: self.visibility_toggled.emit(row.id, value))
            layout.addWidget(self.model_switch)

            # An unspecified capability retains the existing default of tools enabled.
            self.tools_switch = self._switch("row.tools", row.tools is not False,
                tr("row.toolsHint") if row.tools is not False else tr("row.noToolsHint"))
            self.tools_switch.clicked.connect(lambda value: self.tools_toggled.emit(row.id, value))
            layout.addWidget(self.tools_switch)
        elif row.tools is not None:
            tools = pill(tr("row.tools") if row.tools else tr("row.noTools"), "muted" if row.tools else "warning")
            tools.setToolTip(tr("row.toolsHint") if row.tools else tr("row.noToolsHint"))
            layout.addWidget(tools)
        hint = tr("vision.configured") if row.configured_vision is not None else tr(
            "vision.detected" if row.vision is not None else "vision.unknownHint")
        if row.in_config:
            self.vision_switch = self._switch("vision.images" if row.vision is not None else "vision.unknown",
                                             row.vision is True, hint)
            self.vision_switch.clicked.connect(lambda value: self.vision_toggled.emit(row.id, value))
            layout.addWidget(self.vision_switch)
        else:
            image_status = pill(tr("vision.images" if row.vision else "vision.noImages") if row.vision is not None
                                else tr("vision.unknown"), "muted")
            image_status.setToolTip(hint)
            layout.addWidget(image_status)
        self.probe_button = button(tr("vision.test"), "ghost")
        self.probe_button.setToolTip(tr("vision.testHint"))
        self.probe_button.setAccessibleName(tr("vision.testHint"))
        self.probe_button.clicked.connect(lambda: self.vision_probe.emit(row.id))
        layout.addWidget(self.probe_button)
        status = {
            "new": (tr("status.new"), "accent"),
            "configured": (tr("status.configured"), "success"),
            "missing": (tr("status.missing"), "warning"),
        }[row.status]
        layout.addWidget(pill(*status))

    @staticmethod
    def _switch(key: str, checked: bool, hint: str) -> QPushButton:
        control = QPushButton(tr(key))
        control.setObjectName("modelToggle")
        control.setCheckable(True)
        control.setChecked(checked)
        control.setCursor(Qt.CursorShape.PointingHandCursor)
        control.setToolTip(hint)
        control.setAccessibleName(tr(key))
        return control


class AddProviderDialog(QDialog):
    """Name, URL and optional key for a new OpenAI-compatible provider, with a connection check."""

    def __init__(self, parent: QWidget, existing: set[str], preset: Suggestion | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.title"))
        self.setMinimumWidth(460)
        self.existing = existing
        self.result_models: list[RemoteModel] = []
        self.name = QLineEdit(preset.name if preset else "")
        self.name.setPlaceholderText(tr("dialog.namePlaceholder"))
        self.ident = QLineEdit(preset.id if preset else "")
        self.ident.setPlaceholderText("ollama-mac")
        self.url = QLineEdit(preset.base_url if preset else "")
        self.url.setPlaceholderText("http://192.168.1.10:11434/v1")
        self.key = QLineEdit()
        self.key.setPlaceholderText(tr("dialog.keyPlaceholder"))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.add_models = QCheckBox(tr("dialog.addModels"))
        self.add_models.setChecked(True)
        self.status = label("", "hint", wrap=True)
        self.name.textEdited.connect(self._suggest_id)

        title = label(tr("dialog.title"), "title")
        title.setStyleSheet("font-size: 18px;")
        hint = label(tr("dialog.hint"), "hint", wrap=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(10)
        for caption, field in ((tr("dialog.name"), self.name), (tr("dialog.id"), self.ident), (tr("dialog.url"), self.url), (tr("dialog.key"), self.key)):
            layout.addWidget(label(caption, "fieldLabel"))
            layout.addWidget(field)
            layout.addSpacing(4)
        layout.addWidget(self.add_models)
        layout.addWidget(self.status)
        layout.addSpacing(8)

        check = button(tr("dialog.check"), icon_name="refresh")
        check.clicked.connect(self._check)
        cancel = button(tr("dialog.cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        self.save = button(tr("dialog.add"), "primary", "plus")
        self.save.clicked.connect(self._accept)
        actions = QHBoxLayout()
        actions.addWidget(check)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(self.save)
        layout.addLayout(actions)
        if preset:
            self._check()

    def values(self) -> tuple[str, str, str, str | None]:
        return (
            self.ident.text().strip(),
            self.name.text().strip(),
            self.url.text().strip().rstrip("/"),
            self.key.text().strip() or None,
        )

    def _suggest_id(self, text: str) -> None:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        self.ident.setText(slug)

    def _set_status(self, text: str, name: str) -> None:
        self.status.setText(text)
        self.status.setObjectName(name)
        repolish(self.status)

    def _check(self) -> None:
        _, _, url, key = self.values()
        if not url:
            self._set_status(tr("dialog.needUrl"), "error")
            return
        self._set_status(tr("dialog.connecting"), "hint")
        tasks.run(lambda: discovery.discover(url, key), self._checked, lambda message: self._set_status(message, "error"))

    def _checked(self, result: Discovery) -> None:
        if not result.ok:
            self._set_status(tr("dialog.failed", error=result.error), "error")
            return
        self.result_models = result.models
        self._set_status(tr("dialog.works", server=tr(f"server.{result.server}"), count=len(result.models)), "hint")

    def _accept(self) -> None:
        ident, _, url, _ = self.values()
        if not ident or not url:
            self._set_status(tr("dialog.needIdUrl"), "error")
            return
        if ident in self.existing:
            self._set_status(tr("dialog.exists", id=ident), "error")
            return
        self.accept()


class MainWindow(QMainWindow):
    synced = Signal(str)
    language_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenCode Companion")
        self.setWindowIcon(icons.logo())
        self.resize(1080, 700)
        self.setMinimumSize(860, 540)
        self.config_file = config_path()
        self.config = OpencodeConfig.load(self.config_file)
        self.results: dict[str, Discovery | None] = {}
        self.suggestions: list[Suggestion] = []
        self.selected: str | None = None
        self.checked: dict[str, set[str]] = {}
        self.busy = False
        self.tab = "providers"
        # Workspaces of opencode; None while the list is loading.
        self.ws_items: list[workspaces.Workspace] | None = None
        self.ws_note = ""
        self.ws_busy = False
        self.ws_loaded = False
        self.excluded: set[str] = set()
        self.show_excluded = False
        self.show_archived = False
        self.banner = QFrame()
        self.banner.hide()
        # Connected models as opencode lists them; None while the list is loading.
        self.connected: list[str] | None = None
        self.connected_complete = False
        self.models_note = ""
        self.catalog: dict | None = None

        self.sidebar = self._build_sidebar()
        self.content = QWidget()
        self.content.setObjectName("content")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(28, 24, 28, 22)
        self.content_layout.setSpacing(14)

        providers = QWidget()
        providers_layout = QHBoxLayout(providers)
        providers_layout.setContentsMargins(0, 0, 0, 0)
        providers_layout.setSpacing(0)
        providers_layout.addWidget(self.sidebar)
        providers_layout.addWidget(self.content, 1)

        self.workspaces_page = QWidget()
        self.workspaces_layout = QVBoxLayout(self.workspaces_page)
        self.workspaces_layout.setContentsMargins(28, 24, 28, 22)
        self.workspaces_layout.setSpacing(14)

        self.agents_page = QWidget()
        self.agents_layout = QVBoxLayout(self.agents_page)
        self.agents_layout.setContentsMargins(28, 24, 28, 22)
        self.mcp_page = SettingsPanel(self.config_file, self.model_list, mcp=True)
        self.settings_page = SettingsPanel(self.config_file, self.model_list)
        self.mcp_page.saved.connect(self._reload_config)
        self.settings_page.saved.connect(self._reload_config)

        self.tabs = QTabBar()
        self.tabs.setObjectName("tabs")
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.setMovable(False)
        for _ in range(5):
            self.tabs.addTab("")
        self.tabs.currentChanged.connect(self._show_tab)

        self.stack = QStackedWidget()
        self.stack.addWidget(providers)
        self.stack.addWidget(self.workspaces_page)
        self.stack.addWidget(self.agents_page)
        self.stack.addWidget(self.mcp_page)
        self.stack.addWidget(self.settings_page)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tab_strip())
        layout.addWidget(self._banner_slot(), 0)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        # opencode or the user may edit the config while the window is open.
        self.watcher = QFileSystemWatcher(self)
        self.watcher.addPath(str(self.config_file.parent))
        self.watcher.directoryChanged.connect(lambda _: self._reload_debounced.start())
        self._reload_debounced = QTimer(self, singleShot=True, interval=400)
        self._reload_debounced.timeout.connect(self._reload_config)
        self.banner_timer = QTimer(self, singleShot=True, interval=6000)
        self.banner_timer.timeout.connect(self._hide_banner)

        self.refresh()

    # ---- data

    def managed(self) -> list[Provider]:
        """Providers this app can sync: the ones with their own API address."""
        return [provider for provider in self.config.providers() if provider.base_url]

    def refresh(self) -> None:
        self._reload_config()
        for provider in self.managed():
            self.results[provider.id] = None
            self._discover(provider)
        tasks.run(lambda: discovery.scan_local(self.config), self._suggested, lambda _: None)
        self._load_models()
        self.render()

    def _load_models(self) -> None:
        """Ask opencode which models it has connected, and fetch the catalog that describes them."""
        self.connected = None
        self.models_note = tr("model.loading")
        config_file = self.config_file

        def listed() -> tuple[list[str], str, bool]:
            cli = catalog.find_cli()
            if not cli:
                return catalog.from_config(OpencodeConfig.load(config_file)), tr("model.noCli"), False
            try:
                refs = catalog.connected(cli)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                return catalog.from_config(OpencodeConfig.load(config_file)), tr("model.failed", error=error), False
            return refs, tr("model.count", count=len(refs)), True

        def done(result: tuple[list[str], str, bool]) -> None:
            self.connected, self.models_note, self.connected_complete = result
            self.render()

        def failed(error: str) -> None:
            self.connected, self.models_note, self.connected_complete = [], tr("model.failed", error=error), False
            self.render()

        tasks.run(listed, done, failed)
        tasks.run(lambda: catalog.load(catalog.cache_path()), self._catalog_loaded, lambda _: None)

    def _catalog_loaded(self, data: dict) -> None:
        self.catalog = data
        self.render_agents()

    def model_list(self) -> ModelList:
        if self.connected is None:
            return ModelList(note=self.models_note, loading=True)
        items = catalog.choices(self.config, self.connected, self.catalog)
        return ModelList(items=items, note=self.models_note, loading=False, complete=self.connected_complete)

    def _discover(self, provider: Provider) -> None:
        def done(result: Discovery) -> None:
            if not self.config.provider(provider.id):
                return
            self.results[provider.id] = result
            self.checked.setdefault(provider.id, set()).update(
                model.id for model in result.models if model.id not in provider.models
            )
            self.render()

        tasks.run(lambda: discovery.discover(provider.base_url or "", provider.api_key), done, lambda _: None)

    def _suggested(self, suggestions: list[Suggestion]) -> None:
        self.suggestions = suggestions
        self.render_sidebar()

    def _reload_config(self) -> None:
        try:
            self.config = OpencodeConfig.load(self.config_file)
        except ConfigError as error:
            self.show_banner(str(error), "danger")
            return
        if self.selected not in {provider.id for provider in self.managed()}:
            self.selected = next((provider.id for provider in self.managed()), None)
        active = {provider.id for provider in self.config.providers()}
        self.results = {key: value for key, value in self.results.items() if key in active}
        self.checked = {key: value for key, value in self.checked.items() if key in active}
        self.settings_page.reload()
        self.mcp_page.reload()
        self.render()

    # ---- actions

    def sync(self, provider_id: str, only_checked: bool = False) -> None:
        provider = self.config.provider(provider_id)
        result = self.results.get(provider_id)
        if not provider or not result or not result.ok:
            return
        chosen = self.checked.get(provider_id, set())
        add = [model for model in discovery.sync_candidates(provider, result) if not only_checked or model.id in chosen]
        if not add:
            self.show_banner(tr("banner.noNew", provider=provider.title), "accent")
            return
        self._write(provider_id, add, [], tr("banner.added", provider=provider.title, count=len(add)))

    def sync_all(self) -> None:
        plan = []
        for provider in self.managed():
            result = self.results.get(provider.id)
            if result and result.ok:
                add = discovery.sync_candidates(provider, result)
                if add:
                    plan.append((provider.id, add))
        if not plan:
            self.show_banner(tr("banner.allSynced"), "accent")
            self.synced.emit(tr("banner.allSynced"))
            return
        total = sum(len(add) for _, add in plan)

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            for provider_id, add in plan:
                discovery.apply(config, provider_id, add, [])

        message = tr("banner.addedAll", count=total, providers=len(plan))
        self._run_write(work, message)

    def remove_selected(self, provider_id: str) -> None:
        provider = self.config.provider(provider_id)
        if not provider:
            return
        chosen = self.checked.get(provider_id, set())
        rows = discovery.diff(provider, self.results.get(provider_id) or Discovery(ok=False))
        remove = [row.id for row in rows if row.in_config and row.id in chosen]
        if not remove:
            return
        answer = QMessageBox.question(
            self,
            tr("remove.title"),
            tr("remove.text", count=len(remove)) + "\n\n" + "\n".join(remove),
        )
        if answer == QMessageBox.StandardButton.Yes:
            chosen.difference_update(remove)
            self._write(provider_id, [], remove, tr("banner.removed", provider=provider.title, count=len(remove)))

    def set_tools(self, provider_id: str, model_id: str, enabled: bool) -> None:
        if self.busy:
            return
        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.set_model_tools(provider_id, model_id, enabled)
            config.save()

        self._run_write(work, tr("banner.toolsOn" if enabled else "banner.toolsOff", model=model_id))

    def set_vision(self, provider_id: str, model_id: str, enabled: bool) -> None:
        if self.busy:
            return
        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.set_model_vision(provider_id, model_id, enabled)
            config.save()
        self._run_write(work, tr("vision.enabled" if enabled else "vision.disabled", model=model_id))

    def probe_vision(self, provider_id: str, model_id: str) -> None:
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        if not provider:
            return
        answer = QMessageBox.question(self, tr("vision.testHint"), tr("vision.confirm", model=model_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = self.results.get(provider_id)
        remote = next((model for model in result.models if model.id == model_id), None) if result else None
        self.busy = True
        self.render()
        self.show_banner(tr("vision.testing", model=model_id), "accent")
        self.banner_timer.stop()

        def done(result: vision.ProbeResult) -> None:
            self.busy = False
            self._reload_config()
            if result.supported is True:
                self.show_banner(tr("vision.enabled", model=model_id), "success")
            else:
                self.show_banner(tr("vision.undetermined", reason=result.reason), "warning")

        def failed(error: str) -> None:
            self.busy = False
            self.render()
            self.show_banner(tr("vision.failed", error=error), "danger")

        tasks.run(lambda: vision.probe_and_enable(self.config_file, provider_id, model_id, remote), done, failed)

    def set_visible(self, provider_id: str, model_id: str, enabled: bool) -> None:
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        title = provider.title if provider else provider_id

        def work() -> str | None:
            config = OpencodeConfig.load(self.config_file)
            moved = config.set_model_visible(provider_id, model_id, enabled)
            config.save()
            # A provider that changed section is worth saying out loud: the config looks different now.
            return tr("banner.modelOffMoved", model=model_id, provider=title) if moved and not enabled else None

        self._run_write(work, tr("banner.modelOn" if enabled else "banner.modelOff", model=model_id))

    def add_provider(self, preset: Suggestion | None = None) -> None:
        dialog = AddProviderDialog(self, {provider.id for provider in self.config.providers()}, preset)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        ident, name, url, key = dialog.values()
        models = dialog.result_models if dialog.add_models.isChecked() else []

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.add_provider(ident, name, url, key)
            discovery.apply(config, ident, models, [])

        self.selected = ident
        self._run_write(work, tr("banner.providerAdded", name=name or ident, count=len(models)), refresh=True)

    def rename_provider(self, provider_id: str) -> None:
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        if not provider:
            return
        name, accepted = QInputDialog.getText(
            self, tr("provider.rename"), tr("dialog.name"), text=provider.title
        )
        if not accepted or name.strip() == provider.title:
            return

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.rename_provider(provider_id, name)
            config.save()

        self._run_write(work, tr("banner.providerRenamed", name=name.strip()))

    def remove_provider(self, provider_id: str) -> None:
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        if not provider:
            return
        answer = QMessageBox.question(
            self, tr("provider.remove"), tr("provider.removeConfirm", name=provider.title),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.remove_provider(provider_id)
            config.save()

        self._run_write(work, tr("banner.providerRemoved", name=provider.title))

    def edit_agent(self, name: str | None = None) -> None:
        item = agents.agent(self.config, name) if name else None
        if name and not item:
            return
        taken = {agent.name for agent in agents.agents(self.config)}
        dialog = AgentDialog(self, item, taken, agents.subagent_names(self.config), self.model_list)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result_agent()

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            agents.save_agent(config, result, name)
            config.save()

        self._run_write(work, tr("banner.agentSaved", name=result.name))

    def remove_agent(self, name: str) -> None:
        answer = QMessageBox.question(self, tr("remove.agentTitle"), tr("remove.agentText", name=name))
        if answer != QMessageBox.StandardButton.Yes:
            return

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            agents.remove_agent(config, name)
            config.save()

        self._run_write(work, tr("banner.agentRemoved", name=name))

    def build_team(self) -> None:
        dialog = TeamDialog(self, {agent.name for agent in agents.agents(self.config)}, self.model_list)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        members = dialog.members()
        make_default = dialog.make_default.isChecked()

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            agents.save_team(config, members, make_default)
            config.save()

        self._run_write(work, tr("banner.teamSaved", names=", ".join(member.name for member in members)))

    # ---- workspaces ----

    def refresh_workspaces(self) -> None:
        if self.ws_busy:
            return
        self.ws_busy = True
        self.ws_loaded = True
        self.render_workspaces()

        def work():
            return workspaces.list_workspaces(catalog.find_cli())

        def done(result) -> None:
            self.ws_items, self.ws_note = result
            self.ws_busy = False
            self.render_workspaces()

        def failed(error: str) -> None:
            self.ws_busy = False
            self.ws_items, self.ws_note = [], tr("banner.wsFailed", error=error)
            self.show_banner(self.ws_note, "danger")
            self.render_workspaces()

        tasks.run(work, done, failed)

    def add_workspace(self) -> None:
        if self.ws_busy:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("ws.addTitle"), QDir.homePath())
        if not folder:
            return

        def work():
            workspace = workspaces.add(catalog.find_cli(), folder)
            workspaces.include(workspace)  # A folder the user just picked is not meant to stay hidden.
            return None

        self._run_workspaces(work, tr("banner.wsAdded", folder=Path(folder).name or folder))

    def exclude_workspace(self, item: workspaces.Workspace) -> None:
        workspaces.exclude(item)
        self.show_banner(tr("banner.wsExcluded", folder=item.name), "accent")
        self.render_workspaces()

    def restore_workspace(self, item: workspaces.Workspace) -> None:
        workspaces.include(item)
        self.show_banner(tr("banner.wsRestored", folder=item.name), "accent")
        self.render_workspaces()

    def open_workspace(self, item: workspaces.Workspace) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(item.directory))

    def remove_workspace(self, item: workspaces.Workspace) -> None:
        if self.ws_busy:
            return
        text = "ws.removeWorktreeText" if item.kind == workspaces.WORKTREE else "ws.removeProjectText"
        answer = QMessageBox.question(
            self,
            tr("ws.removeTitle"),
            tr(text, folder=item.directory) + ("\n\n" + tr("ws.removeNoteMissing") if not item.exists else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._remove_workspace(item, force=False)

    def _remove_workspace(self, item: workspaces.Workspace, force: bool) -> None:
        self.ws_busy = True
        self.render_workspaces()
        cli = catalog.find_cli()

        def work() -> str:
            try:
                return workspaces.remove(item, cli, force=force)
            except workspaces.ForceRequired:
                return FORCE_NEEDED

        def done(key: object) -> None:
            self.ws_busy = False
            if key == FORCE_NEEDED:
                answer = QMessageBox.question(
                    self,
                    tr("ws.removeTitle"),
                    tr("ws.forceText", folder=item.directory),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                self.render_workspaces()
                if answer == QMessageBox.StandardButton.Yes:
                    self._remove_workspace(item, True)
                return
            message = tr(str(key), folder=item.name)
            self.show_banner(message, "success")
            self.synced.emit(message)
            self.refresh_workspaces()

        def failed(error: str) -> None:
            self.ws_busy = False
            self.show_banner(tr("banner.wsFailed", error=error), "danger")
            self.render_workspaces()

        tasks.run(work, done, failed)

    def unarchive_workspace(self, item: workspaces.Workspace) -> None:
        """Take a workspace out of the archive of opencode; it comes back to this list by itself."""
        if self.ws_busy:
            return

        def work():
            workspaces.unarchive(item)
            return None

        self._run_workspaces(work, tr("banner.wsUnarchived", folder=item.name))

    def _run_workspaces(self, work, message: str) -> None:
        self.ws_busy = True
        self.render_workspaces()

        def done(_: object) -> None:
            self.ws_busy = False
            self.show_banner(message, "success")
            self.synced.emit(message)
            self.refresh_workspaces()

        def failed(error: str) -> None:
            self.ws_busy = False
            self.show_banner(tr("banner.wsFailed", error=error), "danger")
            self.render_workspaces()

        tasks.run(work, done, failed)

    def _write(self, provider_id: str, add: list[RemoteModel], remove: list[str], message: str) -> None:
        def work() -> None:
            # Re-read the file so edits made since the window loaded it are not overwritten.
            discovery.apply(OpencodeConfig.load(self.config_file), provider_id, add, remove)

        self._run_write(work, message)

    def _run_write(self, work, message: str, refresh: bool = False) -> None:
        self.busy = True
        self.render()

        def done(result: object) -> None:
            # A write may come back with what it actually did, which the caller could not know.
            said = result if isinstance(result, str) and result else message
            self.busy = False
            self.show_banner(said, "success")
            self.synced.emit(said)
            if refresh:
                self.refresh()
            else:
                self._reload_config()

        def failed(error: str) -> None:
            self.busy = False
            self.show_banner(tr("banner.saveFailed", error=error), "danger")
            self.render()

        tasks.run(work, done, failed)

    # ---- rendering

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(icons.logo().pixmap(34, 34))
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label("Companion", "brand"))
        self.brand_sub = label(tr("app.brandSub"), "brandSub")
        brand.addWidget(self.brand_sub)
        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 0, 10)
        header.setSpacing(10)
        header.addWidget(logo)
        header.addLayout(brand, 1)
        layout.addLayout(header)

        self.providers_label = label(tr("sidebar.providers"), "sectionLabel")
        layout.addWidget(self.providers_label)
        self.provider_list = QListWidget()
        self.provider_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.provider_list.setSpacing(2)
        layout.addWidget(self.provider_list, 1)

        self.suggestion_box = QVBoxLayout()
        self.suggestion_box.setSpacing(6)
        layout.addLayout(self.suggestion_box)

        self.add_button = button(tr("sidebar.addProvider"), "ghost", "plus")
        self.add_button.clicked.connect(lambda: self.add_provider())
        self.language_button = button("", "ghost")
        self.language_button.clicked.connect(self.switch_language)
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_button)
        bottom.addStretch(1)
        layout.addLayout(bottom)
        return sidebar

    def _tab_strip(self) -> QWidget:
        strip = QWidget()
        strip.setObjectName("tabStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(20, 12, 20, 0)
        row.setSpacing(8)
        row.addWidget(self.tabs)
        row.addStretch(1)
        self.version_button = button(f"v{VERSION}", "ghost")
        self.version_button.clicked.connect(self.show_updates)
        row.addWidget(self.version_button)
        row.addWidget(self.language_button)
        return strip

    def _banner_slot(self) -> QWidget:
        """The one banner of the window, above both tabs."""
        holder = QWidget()
        self.banner_slot = QHBoxLayout(holder)
        self.banner_slot.setContentsMargins(28, 12, 28, 0)
        self.banner_slot.addWidget(self.banner)
        holder.hide()
        return holder

    def _hide_banner(self) -> None:
        self.banner.hide()
        self.banner_slot.parentWidget().hide()

    def _show_tab(self, index: int) -> None:
        self.tab = ("providers", "workspaces", "agents", "mcp", "settings")[index]
        self.stack.setCurrentIndex(index)
        if self.tab == "workspaces" and not self.ws_loaded:
            self.refresh_workspaces()
        if self.tab == "settings":
            self.settings_page.refresh_suggestions()

    def switch_language(self) -> None:
        i18n.set_language("en" if i18n.language() == "ru" else "ru")
        self.language_changed.emit()
        self.render()

    def render(self) -> None:
        self.version_button.setToolTip(tr("update.check"))
        self.version_button.setAccessibleName(tr("update.check"))
        self.tabs.setTabText(0, tr("tab.providers"))
        self.tabs.setTabText(1, tr("tab.workspaces"))
        self.tabs.setTabText(2, tr("nav.agents"))
        self.tabs.setTabText(3, "MCP")
        self.tabs.setTabText(4, settings_text("title"))
        self.render_sidebar()
        self.render_content()
        self.render_workspaces()
        self.render_agents()
        for panel in (self.settings_page, self.mcp_page):
            panel.setEnabled(not self.busy)
            panel.retranslate()

    def confirm_quit(self) -> bool:
        if not (self.settings_page.dirty or self.mcp_page.dirty):
            return True
        return QMessageBox.question(self, settings_text("title"), settings_text("quit"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def render_sidebar(self) -> None:
        self.brand_sub.setText(tr("app.brandSub"))
        self.providers_label.setText(tr("sidebar.providers"))
        self.add_button.setText(tr("sidebar.addProvider"))
        self.add_button.setEnabled(not self.busy)
        # The button names the language it switches to.
        self.language_button.setText("EN" if i18n.language() == "ru" else "RU")
        self.language_button.setToolTip(tr("sidebar.language"))
        self.provider_list.clear()
        for provider in self.managed():
            card = ProviderCard(provider, self.results.get(provider.id))
            card.set_selected(provider.id == self.selected)
            card.clicked.connect(self._select)
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.provider_list.addItem(item)
            self.provider_list.setItemWidget(item, card)

        while self.suggestion_box.count():
            widget = self.suggestion_box.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        if self.suggestions:
            self.suggestion_box.addWidget(label(tr("sidebar.found"), "sectionLabel"))
            for suggestion in self.suggestions:
                card = SuggestionCard(suggestion)
                card.added.connect(self.add_provider)
                self.suggestion_box.addWidget(card)

    def _select(self, provider_id: str) -> None:
        self.selected = provider_id
        self.render()

    def _open_agents(self) -> None:
        self.tabs.setCurrentIndex(2)

    def render_content(self) -> None:
        layout = self.content_layout
        _clear(layout)

        layout.addLayout(self._top_bar())
        provider = self.config.provider(self.selected) if self.selected else None
        if not provider:
            empty = label(
                tr("empty.noProviders"),
                "empty",
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty, 1)
            return
        result = self.results.get(provider.id)
        layout.addLayout(self._provider_header(provider, result))
        layout.addWidget(self._model_list(provider, result), 1)
        layout.addLayout(self._footer(provider, result))

    def render_agents(self) -> None:
        _clear(self.agents_layout)
        panel = AgentsPanel(agents.agents(self.config), agents.default_agent(self.config), self.model_list(), self.busy)
        panel.edit.connect(self.edit_agent)
        panel.remove.connect(self.remove_agent)
        panel.new_agent.connect(lambda: self.edit_agent())
        panel.new_team.connect(self.build_team)
        self.agents_layout.addWidget(panel, 1)

    def render_workspaces(self) -> None:
        self.excluded = workspaces.read_excluded()
        _clear(self.workspaces_layout)
        panel = WorkspacesPanel(
            self.ws_items, self.ws_note, self.excluded, self.show_excluded, self.show_archived, self.ws_busy
        )
        panel.refresh.connect(self.refresh_workspaces)
        panel.add.connect(self.add_workspace)
        panel.exclude.connect(self.exclude_workspace)
        panel.restore.connect(self.restore_workspace)
        panel.remove.connect(self.remove_workspace)
        panel.unarchive.connect(self.unarchive_workspace)
        panel.open.connect(self.open_workspace)
        panel.show_excluded_toggled.connect(lambda shown: self._show_excluded(shown))
        panel.show_archived_toggled.connect(lambda shown: self._show_archived(shown))
        self.workspaces_layout.addWidget(panel, 1)

    def _show_excluded(self, shown: bool) -> None:
        self.show_excluded = shown
        self.render_workspaces()

    def _show_archived(self, shown: bool) -> None:
        self.show_archived = shown
        self.render_workspaces()

    def show_updates(self) -> None:
        from .updates_view import UpdateDialog
        dialog = UpdateDialog(self)
        dialog.exec()

    def _top_bar(self) -> QHBoxLayout:
        folder = button("", "ghost", "folder")
        folder.setToolTip(tr("top.openFolder"))
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.config_file.parent))))
        path = ElidedLabel(str(self.config_file), "configPath", Qt.TextElideMode.ElideMiddle)
        refresh = button(tr("top.refresh"), icon_name="refresh")
        refresh.setToolTip(tr("top.refreshHint"))
        refresh.clicked.connect(self.refresh)
        sync_all = button(tr("top.syncAll"), "primary", "sync")
        sync_all.setEnabled(not self.busy)
        sync_all.setToolTip(tr("top.syncAllHint"))
        sync_all.clicked.connect(self.sync_all)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(folder)
        bar.addWidget(path, 1)
        bar.addWidget(refresh)
        bar.addWidget(sync_all)
        return bar

    def _provider_header(self, provider: Provider, result: Discovery | None) -> QHBoxLayout:
        title = ElidedLabel(provider.title, "title")
        details = [provider.base_url or ""]
        if result and result.ok:
            details.append(tr(f"server.{result.server}"))
        subtitle = ElidedLabel("  ·  ".join(details), "subtitle")
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(title)
        text.addWidget(subtitle)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(text, 1)
        if result is None:
            header.addWidget(pill(tr("header.checking"), "muted"))
        elif not result.ok:
            header.addWidget(pill(tr("header.offline"), "danger"))
        sync = button(tr("header.sync"), "primary", "sync")
        sync.setEnabled(bool(result and result.ok) and not self.busy)
        sync.setToolTip(tr("header.syncHint"))
        sync.clicked.connect(lambda: self.sync(provider.id))
        header.addWidget(sync, 0, Qt.AlignmentFlag.AlignVCenter)
        manage = button("⋯", "ghost")
        manage.setObjectName("providerActions")
        manage.setAccessibleName(tr("provider.actions"))
        manage.setToolTip(tr("provider.actions"))
        manage.setEnabled(not self.busy)
        menu = QMenu(manage)
        menu.addAction(tr("provider.rename")).triggered.connect(lambda: self.rename_provider(provider.id))
        menu.addAction(tr("provider.remove")).triggered.connect(lambda: self.remove_provider(provider.id))
        manage.setMenu(menu)
        header.addWidget(manage, 0, Qt.AlignmentFlag.AlignVCenter)
        return header

    def _model_list(self, provider: Provider, result: Discovery | None) -> QWidget:
        rows = discovery.diff(provider, result or Discovery(ok=False))
        if not rows:
            text = (
                tr("empty.offline", error=result.error)
                if result is not None and not result.ok
                else tr("empty.noModels")
            )
            empty = label(text, "empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return empty
        container = QFrame()
        container.setObjectName("modelList")
        column = QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        chosen = self.checked.setdefault(provider.id, set())
        for index, row in enumerate(rows):
            widget = ModelRowWidget(row, row.id in chosen, index == len(rows) - 1)
            widget.setEnabled(not self.busy)
            widget.toggled.connect(lambda w=widget, pid=provider.id: self._toggle(pid, w))
            widget.vision_toggled.connect(lambda model, value, pid=provider.id: self.set_vision(pid, model, value))
            widget.vision_probe.connect(lambda model, pid=provider.id: self.probe_vision(pid, model))
            widget.tools_toggled.connect(lambda model, value, pid=provider.id: self.set_tools(pid, model, value))
            widget.visibility_toggled.connect(lambda model, value, pid=provider.id: self.set_visible(pid, model, value))
            column.addWidget(widget)
        column.addStretch(1)
        return scrolled(container)

    def _toggle(self, provider_id: str, widget: ModelRowWidget) -> None:
        chosen = self.checked.setdefault(provider_id, set())
        if widget.check.isChecked():
            chosen.add(widget.row.id)
        else:
            chosen.discard(widget.row.id)
        QTimer.singleShot(0, self.render_content)

    def _footer(self, provider: Provider, result: Discovery | None) -> QHBoxLayout:
        rows = discovery.diff(provider, result or Discovery(ok=False))
        chosen = self.checked.get(provider.id, set())
        new = [row for row in rows if row.status == "new"]
        missing = [row for row in rows if row.status == "missing"]
        candidates = discovery.sync_candidates(provider, result) if result and result.ok else []
        picked_new = [model for model in candidates if model.id in chosen]
        picked_config = [row for row in rows if row.in_config and row.id in chosen]
        configured = len([row for row in rows if row.in_config])

        summary = label(
            tr("footer.summary", configured=configured, new=len(new), missing=len(missing)), "subtitle"
        )
        footer = QHBoxLayout()
        footer.addWidget(summary, 1)
        if configured:
            remove = button(tr("footer.remove", count=len(picked_config)), "danger", "trash", theme.current().danger)
            remove.setEnabled(bool(picked_config) and not self.busy)
            remove.clicked.connect(lambda: self.remove_selected(provider.id))
            footer.addWidget(remove)
        if candidates:
            add = button(tr("footer.add", count=len(picked_new)), icon_name="plus")
            add.setEnabled(bool(picked_new) and not self.busy)
            add.clicked.connect(lambda: self.sync(provider.id, only_checked=True))
            footer.addWidget(add)
        return footer

    def show_banner(self, text: str, tone: str) -> None:
        self.banner_slot.removeWidget(self.banner)
        self.banner.deleteLater()
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setProperty("tone", tone)
        row = QHBoxLayout(self.banner)
        row.setContentsMargins(14, 10, 14, 10)
        row.addWidget(label(text, wrap=True), 1)
        self.banner_slot.addWidget(self.banner)
        self.banner_slot.parentWidget().show()
        self.banner_timer.start()


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())
