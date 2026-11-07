"""Schema-backed forms. Nested maps and lists use the same typed editors."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import settings, icons, theme
from .config import ConfigError, OpencodeConfig
from .settings import MISSING
from .settings_text import field_help, field_name, enum_label, t
from .widgets import button, label


def clone(value):
    return MISSING if value is MISSING else deepcopy(value)


def summary(value) -> str:
    if value is MISSING: return t("inherit")
    if isinstance(value, (dict, list)): return t("items", count=len(value))
    return enum_label(value)[:100]


class ValueControl(QWidget):
    changed = Signal()

    def __init__(self, info: dict, value, path: tuple, *, optional=True, suggestions=None, parent=None):
        super().__init__(parent)
        self.info = settings.resolve(info)
        self.path = path
        self.optional = optional
        self._value = clone(value)
        self._loading = True
        self.choices = []
        self.mode = QComboBox()
        self.mode.setMinimumWidth(160)
        self.mode.setMaximumWidth(250)
        if optional:
            self.choices.append(("missing", MISSING))
        for variant in settings.variants(info):
            if "enum" in variant:
                for literal in variant["enum"]:
                    if not any(kind == "literal" and settings.equal(data, literal) for kind, data in self.choices):
                        self.choices.append(("literal", literal))
            elif variant.get("type") == "boolean":
                self.choices.extend([("literal", True), ("literal", False)])
            else:
                self.choices.append(("typed", variant))
        self.multiline = str(path[-1]) in ("system", "prompt", "template", "description")
        self.text = QPlainTextEdit() if self.multiline else QLineEdit()
        if self.multiline:
            self.text.setFixedHeight(120)
        else:
            self.text.setClearButtonEnabled(True)
        if any(part.lower() in ("apikey", "clientsecret", "client_secret") for part in path if isinstance(part, str)):
            self.text.setEchoMode(QLineEdit.EchoMode.Password)
        self.suggestions = QComboBox() if suggestions is not None else None
        if self.suggestions:
            self.suggestions.setEditable(True)
            self.suggestions.addItems(suggestions)
            self.suggestions.currentTextChanged.connect(self._changed)
        self.edit = button(t("edit"))
        self.edit.clicked.connect(self._edit)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        (self.text.textChanged if self.multiline else self.text.textEdited).connect(self._changed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.mode)
        row.addWidget(self.suggestions or self.text, 1)
        if self.suggestions: self.text.hide()
        row.addWidget(self.edit, 1)
        row.addStretch(1)
        self.retranslate()
        self.set_value(value)
        self._loading = False

    def retranslate(self):
        index = self.mode.currentIndex()
        self.mode.blockSignals(True)
        self.mode.clear()
        for kind, data in self.choices:
            text = t("inherit") if kind == "missing" else enum_label(data) if kind == "literal" else t(data.get("type", "json"))
            if kind == "typed":
                discriminator = data.get("properties", {}).get("type", {}).get("enum", [])
                if len(discriminator) == 1:
                    text = enum_label(discriminator[0])
            self.mode.addItem(text)
        self.mode.setCurrentIndex(max(index, 0))
        self.mode.blockSignals(False)
        self.edit.setText(f"{t('edit')}  {summary(self._value)}")
        hint = field_help(self.path, self.info)
        self.setToolTip(hint)
        for control in (self.mode, self.text, self.edit, self.suggestions):
            if control: control.setToolTip(hint)

    def set_value(self, value):
        self._loading = True
        self._value = clone(value)
        index = -1
        for i, (kind, data) in enumerate(self.choices):
            if ((kind == "missing" and value is MISSING) or
                (kind == "literal" and settings.equal(value, data)) or
                (kind == "typed" and value is not MISSING and not settings.validation_errors(value, data))):
                index = i
                break
        # Preserve existing future/extension values without silently coercing them.
        if index < 0 and value is not MISSING:
            self.choices.append(("typed", {}))
            self.retranslate()
            index = len(self.choices) - 1
        self.mode.setCurrentIndex(max(0, index))
        if value is MISSING and not self.optional:
            kind, data = self.choices[self.mode.currentIndex()]
            self._value = deepcopy(data) if kind == "literal" else {
                "string": "", "integer": data.get("minimum", 0), "number": data.get("minimum", 0),
                "array": [], "object": {}, "null": None,
            }.get(data.get("type"), {})
        self._display()
        self._loading = False

    def _display(self):
        kind, info = self.choices[max(self.mode.currentIndex(), 0)]
        scalar = kind == "typed" and info.get("type") in ("string", "integer", "number")
        self.layout().setStretch(3, 1 if kind != "typed" else 0)
        (self.suggestions or self.text).setVisible(scalar)
        self.edit.setVisible(kind == "typed" and not scalar)
        if scalar:
            text = "" if self._value is MISSING else str(self._value)
            if self.suggestions:
                self.suggestions.blockSignals(True)
                self.suggestions.setCurrentText(text)
                self.suggestions.blockSignals(False)
            else:
                self.text.blockSignals(True)
                self.text.setPlainText(text) if self.multiline else self.text.setText(text)
                self.text.blockSignals(False)
        self.edit.setText(f"{t('edit')}  {summary(self._value)}")

    def _mode_changed(self):
        if self._loading: return
        kind, data = self.choices[self.mode.currentIndex()]
        if kind == "missing": self._value = MISSING
        elif kind == "literal": self._value = deepcopy(data)
        else:
            self._value = {"string": "", "integer": 0, "number": 0, "array": [], "object": {}, "null": None}.get(data.get("type"), {})
            if data.get("type") in ("integer", "number"):
                self._value = data.get("minimum", data.get("exclusiveMinimum", -1) + 1)
        self._display()
        self.changed.emit()

    def _changed(self, *_):
        if not self._loading: self.changed.emit()

    def value(self):
        kind, info = self.choices[self.mode.currentIndex()]
        if kind == "missing": return MISSING
        if kind == "literal": return deepcopy(info)
        if info.get("type") in ("string", "integer", "number"):
            raw = self.suggestions.currentText() if self.suggestions else self.text.toPlainText() if self.multiline else self.text.text()
            if info["type"] == "string": return raw
            try:
                value = json.loads(raw)
            except (ValueError, TypeError):
                raise ValueError(".".join(str(p) for p in self.path)) from None
            if type(value) not in (int, float) or (info["type"] == "integer" and type(value) is not int):
                raise ValueError(".".join(str(p) for p in self.path))
            return value
        return clone(self._value)

    def _edit(self):
        kind, info = self.choices[self.mode.currentIndex()]
        if kind != "typed": return
        dialog = ValueDialog(info, self._value, self.path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._value = dialog.result_value
            self._display()
            self.changed.emit()


class FieldRow(QFrame):
    def __init__(self, info, value, path, *, optional=True, suggestions=None):
        super().__init__()
        self.setObjectName("settingRow")
        self.path, self.info = path, info
        self.title = label("", "fieldLabel", wrap=True)
        self.key_label = label(".".join(str(p) for p in path), "hint", wrap=True)
        self.control = ValueControl(info, value, path, optional=optional, suggestions=suggestions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(5)
        # The path of a nested field is one long word, and it breaks wherever it has to. Two things
        # keep it whole. The words line themselves up inside the cell the grid hands them, so a label
        # is as wide as its half of the row instead of as wide as one line of text; and a wrapping
        # label raises its own floor to the height the broken word needs, so the card grows deeper
        # rather than drawing the second line past its own edge, out of sight.
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.key_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        heading = QGridLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(8)
        heading.addWidget(self.title, 0, 0)
        heading.addWidget(self.key_label, 0, 1)
        heading.setColumnStretch(0, 5)
        heading.setColumnStretch(1, 7)
        layout.addLayout(heading)
        layout.addWidget(self.control)
        self.retranslate()

    def retranslate(self):
        self.title.setText(field_name(self.path, self.info))
        hint = field_help(self.path, self.info)
        for item in (self, self.title, self.key_label): item.setToolTip(hint)
        self.control.retranslate()


class CollectionEditor(QWidget):
    changed = Signal()

    def __init__(self, info, value, path, parent=None, *, mcp=False):
        super().__init__(parent)
        self.info, self.path, self.mcp = info, path, mcp
        self.mapping = info.get("type") == "object"
        self.data = deepcopy(value) if isinstance(value, dict if self.mapping else list) else ({} if self.mapping else [])
        self.listing = QListWidget()
        self.listing.setObjectName("settingsCollection")
        self.listing.setMinimumHeight(160)
        self.listing.itemDoubleClicked.connect(lambda _: self.edit_item())
        self.listing.itemChanged.connect(self._toggle)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.listing, 1)
        actions = QHBoxLayout()
        for key, fn in (("add", self.add_item), ("edit", self.edit_item), ("remove", self.remove_item)):
            control = button(t(key))
            control.clicked.connect(fn)
            control.setToolTip(t(key))
            actions.addWidget(control)
        if not self.mapping:
            for key, delta in (("up", -1), ("down", 1)):
                control = button(t(key), "ghost")
                control.clicked.connect(lambda _checked=False, d=delta: self.move(d))
                actions.addWidget(control)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.note = label(t("order") if not self.mapping else t("key"), "hint", wrap=True)
        layout.addWidget(self.note)
        self.fill()

    def item_schema(self):
        if not self.mapping: return self.info.get("items", {})
        extra = self.info.get("additionalProperties", {})
        return extra if isinstance(extra, dict) else {}

    def fill(self, selected=None):
        self.listing.blockSignals(True)
        self.listing.clear()
        for key, value in (self.data.items() if self.mapping else enumerate(self.data)):
            if isinstance(value, dict):
                # Never expose API keys, headers or process environment in the summary.
                details = " · ".join(str(value[k]) for k in ("name", "type", "action", "resource", "effect") if k in value)
                text = details or t("items", count=len(value))
            elif isinstance(value, str): text = value
            else: text = summary(value)
            entry = QListWidgetItem(f"{key}  ·  {text}" if self.mapping else text)
            entry.setData(Qt.ItemDataRole.UserRole, key)
            if self.mcp and isinstance(value, dict):
                entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                entry.setCheckState(Qt.CheckState.Unchecked if value.get("disabled", False) else Qt.CheckState.Checked)
                entry.setToolTip(t("mcpToggle"))
            self.listing.addItem(entry)
            if selected == key: self.listing.setCurrentItem(entry)
        self.listing.blockSignals(False)

    def _toggle(self, item):
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.mcp and isinstance(self.data.get(key), dict):
            self.data[key]["disabled"] = item.checkState() != Qt.CheckState.Checked
            self.changed.emit()

    def add_item(self):
        if self.mapping:
            key, ok = QInputDialog.getText(self, t("add"), t("key"))
            if not ok: return
            key = key.strip()
            if not key or key in self.data:
                QMessageBox.warning(self, t("add"), t("duplicate"))
                return
        else: key = len(self.data)
        dialog = ValueDialog(self.item_schema(), MISSING, (*self.path, str(key)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        if self.mapping: self.data[key] = dialog.result_value
        else: self.data.append(dialog.result_value)
        self.fill(key)
        self.changed.emit()

    def edit_item(self):
        entry = self.listing.currentItem()
        if not entry: return
        key = entry.data(Qt.ItemDataRole.UserRole)
        dialog = ValueDialog(self.item_schema(), self.data[key], (*self.path, str(key)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        self.data[key] = dialog.result_value
        self.fill(key)
        self.changed.emit()

    def remove_item(self):
        entry = self.listing.currentItem()
        if not entry: return
        key = entry.data(Qt.ItemDataRole.UserRole)
        del self.data[key]
        self.fill()
        self.changed.emit()

    def move(self, delta):
        index = self.listing.currentRow()
        other = index + delta
        if index < 0 or not 0 <= other < len(self.data): return
        self.data[index], self.data[other] = self.data[other], self.data[index]
        self.fill(other)
        self.changed.emit()

    def value(self): return deepcopy(self.data)


class ValueDialog(QDialog):
    def __init__(self, info, value, path, parent=None):
        super().__init__(parent)
        self.info = settings.resolve(info)
        self.path = path
        self.result_value = clone(value)
        self.setWindowTitle(field_name(path, info))
        self.resize(760, 620)
        self.rows = {}
        self.collection = None
        self.scalar = None
        self.raw = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        description = label(field_help(path, self.info), "hint", wrap=True)
        layout.addWidget(description)
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        content = QVBoxLayout(body)
        self.content = content
        content.setContentsMargins(0, 0, 0, 0)
        area.setWidget(body)
        layout.addWidget(area, 1)
        if self.info.get("anyOf"):
            self.scalar = ValueControl(self.info, value, path, optional=False)
            content.addWidget(self.scalar)
        elif self.info.get("type") == "object":
            data = deepcopy(value) if isinstance(value, dict) else {}
            properties = self.info.get("properties", {})
            for key, child in properties.items():
                row = FieldRow(child, data.get(key, MISSING), (*path, key), optional=key not in self.info.get("required", []))
                self.rows[key] = row.control
                content.addWidget(row)
            extras = {key: val for key, val in data.items() if key not in properties}
            additional = self.info.get("additionalProperties", True)
            if additional is not False or extras:
                if properties: content.addWidget(label(t("extras"), "fieldLabel"))
                self.collection = CollectionEditor({"type": "object", "additionalProperties": additional}, extras, path)
                content.addWidget(self.collection)
        elif self.info.get("type") == "array":
            self.collection = CollectionEditor(self.info, value, path)
            content.addWidget(self.collection)
        elif "type" in self.info or "enum" in self.info:
            self.scalar = ValueControl(self.info, value, path, optional=False)
            content.addWidget(self.scalar)
        else:
            self.raw = QPlainTextEdit(json.dumps(None if value is MISSING else value, ensure_ascii=False, indent=2))
            self.raw.setToolTip(t("customHint"))
            content.addWidget(self.raw)
        content.addStretch(1)
        notice = label(t(settings.effect(path)), "settingsNotice", wrap=True)
        layout.addWidget(notice)
        self.error = label("", "error", wrap=True)
        layout.addWidget(self.error)
        buttons = QHBoxLayout()
        self.actions = buttons
        buttons.addStretch(1)
        cancel = button(t("cancel"), "ghost")
        cancel.clicked.connect(self.reject)
        accept = button(t("apply"), "primary")
        accept.clicked.connect(self.finish)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)

    def extend(self, result):
        """A subclass with rows of its own merges them in here, before the result is validated."""

    def finish(self):
        try:
            if self.scalar: result = self.scalar.value()
            elif self.raw: result = json.loads(self.raw.toPlainText())
            elif self.info.get("type") == "array": result = self.collection.value()
            else:
                result = self.collection.value() if self.collection else {}
                for key, control in self.rows.items():
                    value = control.value()
                    if value is not MISSING: result[key] = value
                self.extend(result)
            errors = settings.validation_errors(result, self.info)
            if errors: raise ValueError("; ".join(errors[:4]))
        except (ValueError, TypeError) as error:
            self.error.setText(t("invalid", error=error))
            return
        self.result_value = result
        self.accept()


class SettingsPanel(QWidget):
    saved = Signal()

    def __init__(self, path: Path, models=None, *, mcp=False):
        super().__init__()
        self.path, self.models, self.mcp = path, models, mcp
        self.base = deepcopy(OpencodeConfig.load(path).data)
        self.specs = [field for field in settings.fields() if (field.category == "mcp") == mcp]
        if mcp: self.specs.sort(key=lambda field: field.path != ("mcp", "servers"))
        self.rows = {}
        self.changes = {}
        self.errors = {}
        self.notice_keys = []
        self.status_key = "clean"
        self.status_values = {}
        self._loading = True
        self.title = label("", "title")
        self.subtitle = label("", "hint")
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        self.categories = QListWidget()
        self.categories.setObjectName("settingsCategories")
        self.categories.setFixedWidth(225)
        self.categories.currentRowChanged.connect(self.filter)
        self.scope = label("", "hint", wrap=True)
        self.status = label("", "hint", wrap=True)
        self.notice = label("", "settingsNotice", wrap=True)
        self.file_label = label(str(path), "configPath", wrap=True)
        self.file_label.setToolTip(str(path))
        self.save_button = button("", "primary", "check")
        self.save_button.clicked.connect(self.save)
        self.discard_button = button("", "ghost")
        self.discard_button.clicked.connect(self.discard)
        self.refresh_button = button("", icon_name="refresh")
        self.refresh_button.clicked.connect(self.refresh_clicked)
        # The way out lives on the settings page alone; the MCP page edits the same file.
        self.reset_button = None if mcp else button("", "ghost", "trash")
        if self.reset_button:
            self.reset_button.clicked.connect(self.reset)
        self.empty = label("", "hint")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        body = QWidget()
        self.form = QVBoxLayout(body)
        self.form.setContentsMargins(0, 0, 10, 0)
        self.form.setSpacing(10)
        self.scroll.setWidget(body)
        self.mcp_servers = None
        self.timeouts_button = None
        for spec in self.specs:
            value = settings.get(self.base, spec.path)
            if mcp and spec.path == ("mcp", "servers"):
                self.mcp_servers = CollectionEditor(spec.info, value, spec.path, mcp=True)
                self.mcp_servers.listing.setMinimumHeight(220)
                self.mcp_servers.changed.connect(self._changed)
                self.form.addWidget(self.mcp_servers)
                self.timeouts_button = button("", "ghost")
                self.timeouts_button.setCheckable(True)
                self.timeouts_button.clicked.connect(self.filter)
                self.form.addWidget(self.timeouts_button)
                continue
            suggestions = None
            if spec.path == ("model",) and models:
                suggestions = [item.ref for item in models().items]
            if spec.path == ("default_agent",):
                suggestions = list(dict.fromkeys(["build", "plan", *self.base.get("agents", {}), *self.base.get("agent", {})]))
            row = FieldRow(spec.info, value, spec.path, suggestions=suggestions)
            row.control.changed.connect(self._changed)
            self.rows[spec.path] = row
            self.form.addWidget(row)
        self.form.addWidget(self.empty)
        self.form.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch(1)
        self.catalog_button = None
        if mcp:
            from .mcp_catalog_view import t as catalog_text
            self.catalog_button = button(catalog_text("browse"), "primary", "plus")
            self.catalog_button.clicked.connect(self.browse_catalog)
            header.addWidget(self.catalog_button)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.file_label)
        layout.addWidget(self.search)
        split = QHBoxLayout()
        if not mcp: split.addWidget(self.categories)
        else: self.categories.hide()
        split.addWidget(self.scroll, 1)
        layout.addLayout(split, 1)
        layout.addWidget(self.scope)
        layout.addWidget(self.notice)
        footer = QHBoxLayout()
        if self.reset_button: footer.insertWidget(0, self.reset_button)
        footer.addWidget(self.status, 1)
        footer.addWidget(self.discard_button)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.retranslate()
        self._loading = False
        self._changed()

    @property
    def dirty(self): return bool(self.changes or self.errors)

    def browse_catalog(self):
        from .mcp_catalog_view import CatalogDialog
        dialog = CatalogDialog(self.mcp_servers.data, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.mcp_servers.data[dialog.result_name] = dialog.result_config
        self.mcp_servers.fill(dialog.result_name)
        self._changed()

    def refresh_suggestions(self):
        available = {
            ("model",): [item.ref for item in self.models().items] if self.models else [],
            ("default_agent",): list(dict.fromkeys(["build", "plan", *self.base.get("agents", {}), *self.base.get("agent", {})])),
        }
        for path, items in available.items():
            row = self.rows.get(path)
            combo = row.control.suggestions if row else None
            if combo is None: continue
            text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            combo.setCurrentText(text)
            combo.blockSignals(False)

    def retranslate(self):
        if self.catalog_button:
            from .mcp_catalog_view import t as catalog_text
            self.catalog_button.setText(catalog_text("browse"))
        self.title.setText(t("mcp" if self.mcp else "title"))
        self.subtitle.setText(t("subtitle", version=settings.schema()["x-version"], count=len(self.specs)))
        self.search.setPlaceholderText(t("search"))
        self.scope.setText(t("scope"))
        self.save_button.setText(t("save"))
        self.discard_button.setText(t("discard"))
        self.refresh_button.setText(t("refresh"))
        if self.reset_button:
            self.reset_button.setText(t("reset"))
            self.reset_button.setToolTip(t("resetConfirm", file=self.path.name))
        self.empty.setText(t("empty"))
        selected = self.categories.currentItem().data(Qt.ItemDataRole.UserRole) if self.categories.currentItem() else "general"
        self.categories.blockSignals(True)
        self.categories.clear()
        categories = ["all", *dict.fromkeys(spec.category for spec in self.specs)]
        for category in categories:
            item = QListWidgetItem(t(category))
            item.setData(Qt.ItemDataRole.UserRole, category)
            self.categories.addItem(item)
            if category == selected: self.categories.setCurrentItem(item)
        self.categories.blockSignals(False)
        for row in self.rows.values(): row.retranslate()
        if self.mcp_servers:
            # Texts on collection buttons are updated without replacing draft data.
            for control, key in zip(self.mcp_servers.findChildren(QPushButton), ("add", "edit", "remove")):
                control.setText(t(key))
                control.setToolTip(t(key))
            self.mcp_servers.note.setText(t("mcpToggle"))
            self.mcp_servers.fill(self.mcp_servers.listing.currentItem().data(Qt.ItemDataRole.UserRole)
                                  if self.mcp_servers.listing.currentItem() else None)
            self.timeouts_button.setText(t("timeouts"))
            self.timeouts_button.setIcon(icons.icon("down", theme.current().muted))
            self.timeouts_button.setToolTip(t("timeoutsHint"))
        self._show_status()
        self.filter()

    def filter(self, *_):
        words = self.search.text().casefold().split()
        item = self.categories.currentItem()
        category = item.data(Qt.ItemDataRole.UserRole) if item else "all"
        self.scope.setText(t("scope"))
        count = 0
        for spec in self.specs:
            row = self.rows.get(spec.path)
            if row is None: continue
            haystack = f"{spec.key} {row.title.text()} {row.toolTip()} {t(spec.category)}".casefold()
            visible = (bool(words) or category == "all" or category == spec.category or self.mcp) and all(word in haystack for word in words)
            if self.mcp and not words: visible = self.timeouts_button.isChecked()
            row.setVisible(visible)
            count += visible
        if self.mcp_servers:
            for i in range(self.mcp_servers.listing.count()):
                entry = self.mcp_servers.listing.item(i)
                entry.setHidden(any(word not in entry.text().casefold() for word in words))
            count += self.mcp_servers.listing.count()
        self.empty.setVisible(count == 0)

    def _changed(self):
        if self._loading: return
        self.changes, self.errors = {}, {}
        for spec in self.specs:
            try:
                value = self.mcp_servers.value() if spec.path == ("mcp", "servers") and self.mcp_servers else self.rows[spec.path].control.value()
                original = settings.get(self.base, spec.path)
                # Opening an empty MCP page must not add an explicit empty object.
                if self.mcp and spec.path == ("mcp", "servers") and original is MISSING and value == {}:
                    value = MISSING
                if settings.equal(value, original): continue
                self.changes[spec.path] = value
                if value is not MISSING:
                    errors = settings.validation_errors(value, spec.info)
                    if errors: self.errors[spec.path] = "; ".join(errors[:2])
            except (ValueError, TypeError) as error:
                self.errors[spec.path] = str(error)
        self.status_key = "invalid" if self.errors else "pending" if self.changes else "clean"
        self.status_values = {"error": ", ".join(".".join(path) for path in self.errors)} if self.errors else {"count": len(self.changes)} if self.changes else {}
        self.notice_keys = list(dict.fromkeys(settings.effect(path) for path in [*self.changes, *self.errors]))
        self._show_status()

    def _show_status(self):
        self.status.setText(t(self.status_key, **self.status_values))
        self.notice.setText("\n".join(t(key) for key in self.notice_keys))
        self.notice.setVisible(bool(self.notice_keys))
        self.save_button.setEnabled(bool(self.changes) and not self.errors)
        self.discard_button.setEnabled(self.dirty)

    def reload(self, *, force=False):
        try: latest = OpencodeConfig.load(self.path).data
        except (OSError, ConfigError) as error:
            self.status_key, self.status_values = "failed", {"error": str(error)}
            self._show_status()
            return
        if self.dirty and not force:
            if not settings.equal(latest, self.base):
                self.status_key, self.status_values = "external", {}
                self._show_status()
            return
        if not force and settings.equal(latest, self.base): return
        self.base = deepcopy(latest)
        self._loading = True
        for path, row in self.rows.items(): row.control.set_value(settings.get(self.base, path))
        if self.mcp_servers:
            value = settings.get(self.base, ("mcp", "servers"))
            self.mcp_servers.data = {} if value is MISSING else deepcopy(value)
            self.mcp_servers.fill()
        self._loading = False
        self._changed()

    def discard(self):
        self.reload(force=True)

    def refresh_clicked(self):
        if self.dirty and QMessageBox.question(self, t("refresh"), t("resetQuestion")) != QMessageBox.StandardButton.Yes:
            return
        self.reload(force=True)

    def save(self):
        self._changed()
        if self.errors or not self.changes: return
        effects = list(self.notice_keys)
        try:
            settings.save(self.path, self.base, self.changes)
        except settings.Conflict as error:
            self.status_key, self.status_values = "conflict", {"error": str(error)}
        except (OSError, ConfigError, ValueError) as error:
            self.status_key, self.status_values = "failed", {"error": str(error)}
        else:
            self.reload(force=True)
            self.status_key, self.status_values = "saved", {}
            self.notice_keys = effects
            self.saved.emit()
        self._show_status()

    def reset(self):
        """Empty the file and start over: the draft, the conflicts and the stale keys included."""
        answer = QMessageBox.warning(
            self, t("resetTitle"), t("resetConfirm", file=self.path.name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            settings.reset(self.path)
        except OSError as error:
            self.status_key, self.status_values = "failed", {"error": str(error)}
        else:
            self.reload(force=True)
            self.status_key, self.status_values = "saved", {}
            self.notice_keys = []
            self.saved.emit()
        self._show_status()
