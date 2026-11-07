"""The agents page: the config's agents, an editor for one agent and a builder for a planner-and-workers team."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import agents, theme
from .agents import ACCESS, CUSTOM, MODES, PERMISSIONS, ROLES, Agent, Worker
from .catalog import ModelChoice, find
from .i18n import tr
from .widgets import ElidedLabel, button, label, pill, repolish, scrolled, tokens


@dataclass
class ModelList:
    """The models opencode has connected, and a line that says where the list came from."""

    items: list[ModelChoice] = field(default_factory=list)
    note: str = ""
    loading: bool = True
    # False when opencode could not be asked and the list holds only the config's models,
    # so a model missing from it may still be connected.
    complete: bool = False


Models = Callable[[], ModelList]


def describe(item: ModelChoice, *, include_provider: bool = True) -> str:
    parts = [item.provider] if include_provider else []
    if item.local:
        parts.append(tr("model.local"))
    elif item.free:
        parts.append(tr("model.free"))
    if item.tools is not None:
        parts.append(tr("row.tools") if item.tools else tr("row.noTools"))
    if item.context:
        parts.append(tokens(item.context))
    return "  ·  ".join(parts)


def section(text: str) -> QWidget:
    return label(text, "sectionLabel")


def dialog_buttons(dialog: QDialog, accept_text: str, accept: Callable[[], None]) -> QHBoxLayout:
    cancel = button(tr("dialog.cancel"), "ghost")
    cancel.clicked.connect(dialog.reject)
    save = button(accept_text, "primary", "check")
    save.clicked.connect(accept)
    save.setDefault(True)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(cancel)
    row.addWidget(save)
    return row


class ModelPicker(QDialog):
    """Connected models in collapsible provider groups, with search and filters."""

    def __init__(self, parent: QWidget, models: ModelList, current: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("picker.title"))
        self.resize(660, 600)
        self.models = models
        self.chosen = current
        self.expanded_providers = {current.split("/", 1)[0]} if current else set()
        self._filling = False
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("picker.search"))
        self.search.setClearButtonEnabled(True)
        self.free_only = QCheckBox(tr("picker.freeOnly"))
        self.tools_only = QCheckBox(tr("picker.toolsOnly"))
        self.listing = QTreeWidget()
        self.listing.setObjectName("pickerList")
        self.listing.setHeaderHidden(True)
        self.listing.setColumnCount(1)
        self.listing.setIndentation(18)
        self.listing.setExpandsOnDoubleClick(False)
        self.listing.setVerticalScrollMode(QTreeWidget.ScrollMode.ScrollPerPixel)
        self.listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.listing.setWordWrap(True)
        self.listing.itemClicked.connect(self._clicked)
        self.listing.itemDoubleClicked.connect(lambda item, _column: self._accept() if item.parent() else None)
        self.listing.itemExpanded.connect(self._expansion_changed)
        self.listing.itemCollapsed.connect(self._expansion_changed)
        self.listing.currentItemChanged.connect(self._selection_changed)
        self.empty = label(tr("picker.empty"), "hint")
        note = label(models.note, "hint", wrap=True)

        for widget in (self.search,):
            widget.textChanged.connect(self._fill)
        for box in (self.free_only, self.tools_only):
            box.toggled.connect(self._fill)
        filters = QHBoxLayout()
        filters.addWidget(self.free_only)
        filters.addWidget(self.tools_only)
        filters.addStretch(1)
        expand = button(tr("picker.expandAll"), "ghost")
        expand.clicked.connect(self.listing.expandAll)
        collapse = button(tr("picker.collapseAll"), "ghost")
        collapse.clicked.connect(self.listing.collapseAll)
        groups = QHBoxLayout()
        groups.addWidget(expand)
        groups.addWidget(collapse)
        groups.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        layout.addWidget(self.search)
        layout.addLayout(filters)
        layout.addLayout(groups)
        layout.addWidget(self.listing, 1)
        layout.addWidget(self.empty)
        layout.addWidget(note)
        layout.addLayout(dialog_buttons(self, tr("picker.choose"), self._accept))
        self._fill()
        self.search.setFocus()

    def _fill(self) -> None:
        words = self.search.text().lower().split()
        self._filling = True
        self.listing.clear()
        selected = None
        groups: dict[str, tuple[str, list[ModelChoice]]] = {}
        for item in self.models.items:
            haystack = f"{item.name} {item.ref} {item.provider}".lower()
            if any(word not in haystack for word in words):
                continue
            if self.free_only.isChecked() and not item.free:
                continue
            if self.tools_only.isChecked() and item.tools is False:
                continue
            provider_id = item.ref.split("/", 1)[0]
            groups.setdefault(provider_id, (item.provider, []))[1].append(item)
        names = [name for name, _items in groups.values()]
        for provider_id, (name, items) in sorted(groups.items(), key=lambda pair: (pair[1][0].casefold(), pair[0])):
            title = f"{name} · {provider_id}" if names.count(name) > 1 else name
            group = QTreeWidgetItem([f"{title}  ({len(items)})"])
            group.setData(0, Qt.ItemDataRole.UserRole, provider_id)
            group.setToolTip(0, provider_id)
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            self.listing.addTopLevelItem(group)
            for item in sorted(items, key=lambda item: (item.name.casefold(), item.ref)):
                details = describe(item, include_provider=False)
                title = f"{item.name}   ·   {details}" if details else item.name
                entry = QTreeWidgetItem([f"{title}\n{item.ref}"])
                entry.setData(0, Qt.ItemDataRole.UserRole, item.ref)
                entry.setToolTip(0, item.ref)
                group.addChild(entry)
                if item.ref == self.chosen:
                    selected = entry
            group.setExpanded(bool(words) or provider_id in self.expanded_providers)
        if selected and selected.parent().isExpanded():
            self.listing.setCurrentItem(selected)
        self.empty.setVisible(self.listing.topLevelItemCount() == 0)
        self._filling = False

    def _clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.parent() is None:
            item.setExpanded(not item.isExpanded())

    def _selection_changed(self, item: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if not self._filling and item and item.parent():
            self.chosen = item.data(0, Qt.ItemDataRole.UserRole)

    def _expansion_changed(self, group: QTreeWidgetItem) -> None:
        if self._filling:
            return
        if not self.search.text().strip():
            provider_id = group.data(0, Qt.ItemDataRole.UserRole)
            if group.isExpanded():
                self.expanded_providers.add(provider_id)
            else:
                self.expanded_providers.discard(provider_id)
        current = self.listing.currentItem()
        if not group.isExpanded() and current and current.parent() == group:
            self.listing.setCurrentItem(None)

    def _accept(self) -> None:
        item = self.listing.currentItem()
        if item and item.parent() and item.parent().isExpanded():
            self.chosen = item.data(0, Qt.ItemDataRole.UserRole)
            self.accept()


class ModelField(QWidget):
    """A model reference typed in or picked from the connected models, with what is known about it."""

    def __init__(self, models: Models, value: str | None) -> None:
        super().__init__()
        self.models = models
        self.edit = QLineEdit(value or "")
        self.edit.setPlaceholderText(tr("model.placeholder"))
        completer = QCompleter([item.ref for item in models().items], self.edit)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.edit.setCompleter(completer)
        pick = button(tr("model.pick"))
        pick.clicked.connect(self._pick)
        self.info = label("", "hint")
        self.edit.textChanged.connect(self._describe)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.edit, 1)
        row.addWidget(pick)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(row)
        layout.addWidget(self.info)
        self._describe()

    def value(self) -> str | None:
        return self.edit.text().strip() or None

    def _pick(self) -> None:
        picker = ModelPicker(self.window(), self.models(), self.edit.text().strip())
        if picker.exec() == QDialog.DialogCode.Accepted:
            self.edit.setText(picker.chosen)

    def _describe(self) -> None:
        ref = self.edit.text().strip()
        models = self.models()
        item = find(models.items, ref)
        if not ref:
            text, name = tr("agents.defaultModel"), "hint"
        elif item:
            text, name = describe(item), "hint"
        elif not models.complete:
            text, name = "", "hint"
        else:
            text, name = tr("model.unknown"), "error"
        self.info.setText(text)
        self.info.setObjectName(name)
        repolish(self.info)


def access_combo(value: str | None) -> QComboBox:
    combo = QComboBox()
    combo.addItem(tr("access.default"), None)
    for action in ACCESS:
        combo.addItem(tr(f"access.{action}"), action)
    if value == CUSTOM:
        combo.addItem(tr("access.custom"), CUSTOM)
    combo.setCurrentIndex(max(0, combo.findData(value)))
    return combo


class AgentDialog(QDialog):
    """Every setting of one agent this app manages."""

    def __init__(self, parent: QWidget, item: Agent | None, taken: set[str], subagents: list[str], models: Models) -> None:
        super().__init__(parent)
        self.original = item
        self.item = item or Agent(name="", mode="subagent")
        self.taken = taken
        self.setWindowTitle(tr("agent.editTitle", name=item.name) if item else tr("agent.newTitle"))
        self.resize(600, 720)

        self.name = QLineEdit(self.item.name)
        self.name.setPlaceholderText("coder")
        self.description = QLineEdit(self.item.description)
        self.description.setPlaceholderText(tr("agent.descriptionPlaceholder"))
        self.mode = QComboBox()
        for mode in MODES:
            self.mode.addItem(tr(f"mode.{mode}"), mode)
            self.mode.setItemData(self.mode.count() - 1, tr(f"mode.{mode}Hint"), Qt.ItemDataRole.ToolTipRole)
        self.mode.setCurrentIndex(MODES.index(self.item.mode))
        self.model = ModelField(models, self.item.model)
        self.steps = QLineEdit("" if self.item.steps is None else str(self.item.steps))
        self.steps.setPlaceholderText(tr("agent.stepsPlaceholder"))
        self.prompt = QPlainTextEdit(self.item.prompt)
        self.prompt.setPlaceholderText(tr("agent.promptPlaceholder"))
        self.prompt.setMinimumHeight(120)
        self.access = {key: access_combo(self.item.access.get(key)) for key in PERMISSIONS}
        self.disabled = QCheckBox(tr("agent.disabled"))
        self.disabled.setChecked(self.item.disabled)
        self.status = label("", "error", wrap=True)

        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(6)

        def field(caption: str, widget: QWidget, hint: str | None = None) -> None:
            form.addWidget(label(caption, "fieldLabel"))
            form.addWidget(widget)
            if hint:
                form.addWidget(label(hint, "hint", wrap=True))
            form.addSpacing(6)

        field(tr("agent.name"), self.name, tr("agent.nameHint"))
        field(tr("agent.description"), self.description)
        top = QGridLayout()
        top.setHorizontalSpacing(12)
        top.addWidget(label(tr("agent.mode"), "fieldLabel"), 0, 0)
        top.addWidget(label(tr("agent.steps"), "fieldLabel"), 0, 1)
        top.addWidget(self.mode, 1, 0)
        top.addWidget(self.steps, 1, 1)
        top.setColumnStretch(0, 2)
        top.setColumnStretch(1, 1)
        form.addLayout(top)
        form.addWidget(label(tr("agent.stepsHint"), "hint", wrap=True))
        form.addSpacing(6)
        field(tr("agent.model"), self.model)
        field(tr("agent.prompt"), self.prompt)

        form.addWidget(section(tr("agent.access").upper()))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        for row, key in enumerate(PERMISSIONS):
            grid.addWidget(label(tr(f"access.{key}")), row, 0)
            grid.addWidget(self.access[key], row, 1)
        grid.setColumnStretch(1, 1)
        form.addLayout(grid)
        if self.item.has_custom_access:
            form.addWidget(label(tr("agent.accessKept"), "hint", wrap=True))
        form.addSpacing(6)

        # Who this agent may hand work to; only an agent that can be primary hands out work.
        self.delegation = QWidget()
        box = QVBoxLayout(self.delegation)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addWidget(section(tr("agent.delegation").upper()))
        self.limit = QCheckBox(tr("agent.limitDelegates"))
        self.limit.setChecked(self.item.delegates is not None)
        box.addWidget(self.limit)
        chosen = set(self.item.delegates or [])
        names = [name for name in subagents if name != self.item.name] + sorted(chosen - set(subagents))
        self.delegates = {name: QCheckBox(name) for name in names}
        picks = QGridLayout()
        picks.setContentsMargins(24, 0, 0, 0)
        for index, (name, check) in enumerate(self.delegates.items()):
            check.setChecked(name in chosen)
            picks.addWidget(check, index // 3, index % 3)
        box.addLayout(picks)
        if self.item.custom_task:
            box.addWidget(label(tr("agent.taskKept"), "hint", wrap=True))
            self.limit.setEnabled(False)
        self.limit.toggled.connect(self._sync)
        self.mode.currentIndexChanged.connect(self._sync)
        form.addWidget(self.delegation)
        form.addSpacing(6)
        form.addWidget(self.disabled)
        form.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        title = label(self.windowTitle(), "title")
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)
        layout.addWidget(scrolled(body), 1)
        layout.addWidget(self.status)
        layout.addLayout(dialog_buttons(self, tr("agent.save"), self._accept))
        self._sync()

    def _sync(self) -> None:
        self.delegation.setVisible(self.mode.currentData() != "subagent")
        editable = not self.item.custom_task and self.limit.isChecked()
        for check in self.delegates.values():
            check.setEnabled(editable)

    def result_agent(self) -> Agent:
        item = self.item
        return Agent(
            name=self.name.text().strip(),
            mode=self.mode.currentData(),
            model=self.model.value(),
            description=self.description.text().strip(),
            prompt=self.prompt.toPlainText().strip(),
            disabled=self.disabled.isChecked(),
            access={key: combo.currentData() for key, combo in self.access.items()},
            delegates=[name for name, check in self.delegates.items() if check.isChecked()] if self.limit.isChecked() else None,
            custom_task=item.custom_task,
            steps=int(self.steps.text().strip()) if self.steps.text().strip() else None,
            kept_rules=list(item.kept_rules),
        )

    def _accept(self) -> None:
        name = self.name.text().strip()
        if not name:
            self.status.setText(tr("agent.needName"))
        elif not agents.valid_name(name):
            self.status.setText(tr("error.badAgentName"))
        elif name in self.taken and name != (self.original.name if self.original else None):
            self.status.setText(tr("error.agentExists", name=name))
        elif not self.description.text().strip():
            self.status.setText(tr("agent.needDescription"))
        elif self.steps.text().strip() and not (self.steps.text().strip().isdigit() and int(self.steps.text()) >= 1):
            self.status.setText(tr("agent.badSteps"))
        else:
            self.accept()


class WorkerRow(QFrame):
    removed = Signal(object)

    def __init__(self, role: str, models: Models) -> None:
        super().__init__()
        self.setObjectName("workerRow")
        self.role = QComboBox()
        for item in ROLES:
            self.role.addItem(tr(f"role.{item}"), item)
            self.role.setItemData(self.role.count() - 1, tr(f"role.{item}.description"), Qt.ItemDataRole.ToolTipRole)
        self.role.setCurrentIndex(ROLES.index(role))
        self.name = QLineEdit(role if role != "custom" else "worker")
        self.named = False
        self.name.textEdited.connect(lambda _text: setattr(self, "named", True))
        self.role.currentIndexChanged.connect(self._role_changed)
        self.model = ModelField(models, None)
        self.hint = label(tr(f"role.{role}.description"), "hint", wrap=True)
        remove = button("", "ghost", "trash")
        remove.setToolTip(tr("team.removeWorker"))
        remove.clicked.connect(lambda: self.removed.emit(self))

        grid = QGridLayout(self)
        grid.setContentsMargins(14, 12, 10, 12)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.addWidget(self.role, 0, 0)
        grid.addWidget(self.name, 0, 1)
        grid.addWidget(remove, 0, 2)
        grid.addWidget(self.hint, 1, 0, 1, 3)
        grid.addWidget(self.model, 2, 0, 1, 3)
        grid.setColumnStretch(1, 1)

    def _role_changed(self) -> None:
        role = self.role.currentData()
        self.hint.setText(tr(f"role.{role}.description"))
        if not self.named:
            self.name.setText(role if role != "custom" else "worker")

    def worker(self) -> Worker:
        return Worker(role=self.role.currentData(), name=self.name.text().strip(), model=self.model.value())


class TeamDialog(QDialog):
    """One primary planner and the workers it may hand work to, each on its own model."""

    def __init__(self, parent: QWidget, taken: set[str], models: Models) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("team.title"))
        self.resize(640, 760)
        self.taken = taken
        self.models = models
        self.planner = QLineEdit("planner")
        self.planner_model = ModelField(models, None)
        self.delegate_only = QCheckBox(tr("team.delegateOnly"))
        self.delegate_only.setChecked(True)
        self.make_default = QCheckBox(tr("team.makeDefault"))
        self.make_default.setChecked(True)
        self.status = label("", "error", wrap=True)

        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(6)
        form.addWidget(section(tr("team.planner")))
        lead = QFrame()
        lead.setObjectName("workerRow")
        lead_layout = QVBoxLayout(lead)
        lead_layout.setContentsMargins(14, 12, 14, 12)
        lead_layout.setSpacing(6)
        lead_layout.addWidget(label(tr("agent.name"), "fieldLabel"))
        lead_layout.addWidget(self.planner)
        lead_layout.addWidget(label(tr("agent.model"), "fieldLabel"))
        lead_layout.addWidget(self.planner_model)
        lead_layout.addWidget(self.delegate_only)
        lead_layout.addWidget(self.make_default)
        form.addWidget(lead)
        form.addSpacing(10)
        form.addWidget(section(tr("team.workers")))
        self.rows: list[WorkerRow] = []
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        form.addLayout(self.rows_box)
        add = button(tr("team.addWorker"), "ghost", "plus")
        add.clicked.connect(lambda: self._add("custom"))
        form.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        form.addStretch(1)
        for role in ("coder", "tester", "researcher"):
            self._add(role)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        title = label(tr("team.title"), "title")
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)
        layout.addWidget(label(tr("team.hint"), "hint", wrap=True))
        layout.addWidget(scrolled(body), 1)
        layout.addWidget(self.status)
        layout.addLayout(dialog_buttons(self, tr("team.create"), self._accept))

    def _add(self, role: str) -> None:
        row = WorkerRow(role, self.models)
        row.removed.connect(self._remove)
        self.rows.append(row)
        self.rows_box.addWidget(row)

    def _remove(self, row: WorkerRow) -> None:
        self.rows.remove(row)
        row.deleteLater()

    def members(self) -> list[Agent]:
        return agents.team(
            self.planner.text().strip(),
            self.planner_model.value(),
            [row.worker() for row in self.rows],
            self.delegate_only.isChecked(),
        )

    def _accept(self) -> None:
        names = [self.planner.text().strip()] + [row.name.text().strip() for row in self.rows]
        if not self.rows:
            self.status.setText(tr("team.needWorker"))
            return
        if not all(names):
            self.status.setText(tr("agent.needName"))
            return
        if not all(agents.valid_name(name) for name in names):
            self.status.setText(tr("error.badAgentName"))
            return
        if len(set(names)) != len(names):
            self.status.setText(tr("error.teamDuplicate"))
            return
        existing = [name for name in names if name in self.taken]
        if existing:
            answer = QMessageBox.question(self, tr("team.overwriteTitle"), tr("team.overwriteText", names=", ".join(existing)))
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.accept()


class AgentRow(QFrame):
    edit = Signal(str)
    remove = Signal(str)

    def __init__(self, item: Agent, is_default: bool, models: ModelList, last: bool, busy: bool) -> None:
        super().__init__()
        self.setObjectName("modelRow")
        self.setProperty("last", last)
        title = QHBoxLayout()
        title.setSpacing(8)
        name = label(item.name, "modelName")
        title.addWidget(name)
        mode = pill(tr(f"mode.{item.mode}"), "accent" if item.mode != "subagent" else "muted")
        mode.setToolTip(tr(f"mode.{item.mode}Hint"))
        title.addWidget(mode)
        if is_default:
            default = pill(tr("agents.default"), "success")
            default.setToolTip(tr("agents.defaultHint"))
            title.addWidget(default)
        if item.disabled:
            title.addWidget(pill(tr("agents.disabled"), "warning"))
        title.addStretch(1)

        text = QVBoxLayout()
        text.setSpacing(3)
        text.addLayout(title)
        choice = find(models.items, item.model)
        model = ElidedLabel(item.model or tr("agents.defaultModel"), "mono", Qt.TextElideMode.ElideMiddle)
        text.addWidget(model)
        if item.description:
            text.addWidget(ElidedLabel(item.description, "subtitle"))
        if item.can_delegate and item.delegates is not None:
            text.addWidget(ElidedLabel(tr("agents.delegates", names=", ".join(item.delegates) or "—"), "configPath"))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(text, 1)
        if choice:
            tags = pill(tr("model.local") if choice.local else tr("model.free") if choice.free else choice.provider, "muted")
            tags.setToolTip(describe(choice))
            layout.addWidget(tags)
            if choice.tools is False:
                warn = pill(tr("row.noTools"), "warning")
                warn.setToolTip(tr("row.noToolsHint"))
                layout.addWidget(warn)
        elif item.model and models.complete:
            missing = pill(tr("model.unknown"), "warning")
            missing.setToolTip(item.model)
            layout.addWidget(missing)
        edit = button(tr("agents.edit"), "ghost")
        edit.setEnabled(not busy)
        edit.clicked.connect(lambda: self.edit.emit(item.name))
        remove = button("", "ghost", "trash", theme.current().danger)
        remove.setToolTip(tr("agents.remove"))
        remove.setEnabled(not busy)
        remove.clicked.connect(lambda: self.remove.emit(item.name))
        layout.addWidget(edit)
        layout.addWidget(remove)


class AgentsPanel(QWidget):
    edit = Signal(str)
    remove = Signal(str)
    new_agent = Signal()
    new_team = Signal()

    def __init__(self, items: list[Agent], default: str | None, models: ModelList, busy: bool) -> None:
        super().__init__()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(label(tr("agents.title"), "title"))
        heading.addWidget(label(tr("agents.subtitle"), "subtitle", wrap=True))
        new_agent = button(tr("agents.newAgent"), icon_name="plus")
        new_agent.setEnabled(not busy)
        new_agent.clicked.connect(self.new_agent.emit)
        new_team = button(tr("agents.newTeam"), "primary", "users")
        new_team.setToolTip(tr("agents.newTeamHint"))
        new_team.setEnabled(not busy)
        new_team.clicked.connect(self.new_team.emit)
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addLayout(heading, 1)
        header.addWidget(new_agent, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(new_team, 0, Qt.AlignmentFlag.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addLayout(header)
        if not items:
            empty = label(tr("agents.empty"), "empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty, 1)
        else:
            container = QFrame()
            container.setObjectName("modelList")
            column = QVBoxLayout(container)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(0)
            for index, item in enumerate(items):
                row = AgentRow(item, item.name == default, models, index == len(items) - 1, busy)
                row.edit.connect(self.edit.emit)
                row.remove.connect(self.remove.emit)
                column.addWidget(row)
            column.addStretch(1)
            layout.addWidget(scrolled(container), 1)
        layout.addWidget(label(models.note, "configPath", wrap=True))
