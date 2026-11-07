"""Main navigation: providers, workspaces, agents, MCP and configuration."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QFileSystemWatcher, QDir, QLocale, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDoubleValidator, QEnterEvent, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
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
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import agents, catalog, discovery, i18n, icons, tasks, theme, workspaces, vision
from .agents_view import AgentDialog, AgentsPanel, ModelList, TeamDialog
from .config import ConfigError, OpencodeConfig, Provider, config_path
from .discovery import Discovery, ModelRow, RemoteModel, Suggestion
from .i18n import tr
from .settings import MISSING, model_schema
from .widgets import ElidedLabel, button, label, pill, repolish, scrolled, tokens
from .workspaces_view import WorkspacesPanel
from .settings_view import FieldRow, SettingsPanel, ValueDialog
from .settings_text import field_help, field_name, t as settings_text
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
    """One model in the list.

    The row says only what the config makes of the model — whether it is there at all — and ends
    with the gear that opens everything else. What the entry can say is too long for a line: the
    display, the tools, the images and the context window all live behind that icon now.
    """

    toggled = Signal()
    configure = Signal(str)  # model id, for the window that holds every setting

    def __init__(self, row: ModelRow, checked: bool, last: bool) -> None:
        super().__init__()
        self.row = row
        self.setObjectName("modelRow")
        self.setProperty("last", last)
        self.setProperty("off", not row.visible)
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
        status = {
            "new": (tr("status.new"), "accent"),
            "configured": (tr("status.configured"), "success"),
            "missing": (tr("status.missing"), "warning"),
        }[row.status]
        layout.addWidget(pill(*status))

        # The one way in. An icon carries no language, so the word only has to be said once, in the
        # tooltip, and the row keeps its width for the model's name.
        self.settings_button = button("", "ghost", "gear")
        self.settings_button.setToolTip(tr("row.settingsHint"))
        self.settings_button.setAccessibleName(tr("row.settings"))
        self.settings_button.clicked.connect(lambda: self.configure.emit(row.id))
        layout.addWidget(self.settings_button)


class AddProviderDialog(QDialog):
    """Name, URL and optional key for a new OpenAI-compatible provider, with a connection check.

    Given ``editing`` — the provider's (id, name, url, key) as the config stores them — the same
    dialog repairs an existing provider instead: the ID stands still, and an empty key keeps the
    saved one.
    """

    def __init__(self, parent: QWidget, existing: set[str], preset: Suggestion | None = None,
                 editing: tuple[str, str, str, str | None] | None = None) -> None:
        super().__init__(parent)
        self.editing = editing
        self.setWindowTitle(tr("dialog.editTitle") if editing else tr("dialog.title"))
        self.setMinimumWidth(460)
        self.existing = existing
        self.result_models: list[RemoteModel] = []
        self.name = QLineEdit(editing[1] if editing else (preset.name if preset else ""))
        self.name.setPlaceholderText(tr("dialog.namePlaceholder"))
        self.ident = QLineEdit(editing[0] if editing else (preset.id if preset else ""))
        self.ident.setPlaceholderText("ollama-mac")
        if editing:
            self.ident.setReadOnly(True)  # opencode and every saved model selection name models by it
        self.url = QLineEdit(editing[2] if editing else (preset.base_url if preset else ""))
        self.url.setPlaceholderText("http://192.168.1.10:11434/v1")
        self.key = QLineEdit()
        self.key.setPlaceholderText(
            tr("dialog.keyKeep") if editing and editing[3] else tr("dialog.keyPlaceholder"))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.add_models = QCheckBox(tr("dialog.addModels"))
        self.add_models.setChecked(True)
        self.status = label("", "hint", wrap=True)
        self.name.textEdited.connect(self._suggest_id)

        title = label(tr("dialog.editTitle") if editing else tr("dialog.title"), "title")
        title.setStyleSheet("font-size: 18px;")
        hint = label(tr("dialog.editHint") if editing else tr("dialog.hint"), "hint", wrap=True)
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
        self.save = button(tr("dialog.save") if editing else tr("dialog.add"), "primary",
                           "check" if editing else "plus")
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


# Sizes in K, and a K is 1024 tokens: 384K is 393 216, the number that goes into the config.
CONTEXT_PRESETS = tuple(k * 1024 for k in (8, 16, 32, 64, 128, 200, 256, 384, 512, 768, 1024))


def preset_label(size: int) -> str:
    """The short name and the exact number behind it, so a chosen preset cannot surprise anyone."""
    return f"{tokens(size)} · {size:,}".replace(",", " ")


MAX_CONTEXT = 100_000_000

# What a page keeps inside itself: the window edge is not where a field wants to start, and the
# same room the model list keeps is what a reader's eye expects here.
TAB_PADDING = (18, 14, 18, 10)


class CountField(QLineEdit):
    """A number the config may leave unsaid: an empty field is the word "opencode decides".

    A spin box was the obvious control until it was drawn: Qt paints a styled spin box's digits
    from its own palette, which stays the system's light one, so the number came out black on a
    dark field — invisible. A line edit takes its ink from the style sheet like every other field
    in this app, and the presets next to it do the stepping a stepper was for.
    """

    def __init__(self, undecided: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setValidator(QIntValidator(0, MAX_CONTEXT, self))
        self.setPlaceholderText(undecided)

    def value(self) -> int:
        return int(self.text()) if self.text() else 0

    def setValue(self, count: int) -> None:
        self.setText("" if not count else str(count))


# Where a typed number stops looking like one the user meant. These are not claims about any model:
# they are the ends of the validator, so that a slip of a key cannot be saved. What a model really
# holds is the server's answer, and the context field is where that number is asked for.
MAX_TOKENS = MAX_CONTEXT
MAX_SEED = 2_147_483_647


def shown(number) -> str:
    """A number written the way a config writes it: 0.7, not 0.7000000000000001."""
    if isinstance(number, bool) or not isinstance(number, (int, float)):
        return str(number)
    return str(int(number)) if float(number).is_integer() else str(round(number, 4))


class ParamField(QWidget):
    """One generation number, the bounds it may not cross, and the choice of not saying it.

    A number with no bounds is a number a typo survives, so every field here knows both ends of its
    range. Where the range is short enough for the choice to be coarse — temperature, the nucleus,
    the two penalties — the ends are printed on either side of a slider that walks the range in the
    step this app considers reasonable, and the exact number stands beside it, typed. A count with
    no useful step (which K, how many tokens, which seed) cannot be slid over: its floor is printed
    in the slider's place and the number is typed, the validator refusing what lies outside.

    The tick box is the answer an entry gives by saying nothing. Every field the config did not name
    starts ticked, and a ticked field writes nothing at all: the provider's own default stands. While
    it is ticked the row states its bounds in words and keeps the groove hidden, because a handle
    parked on a number that will never be written is read as a value — and the wrong one.
    """

    NAME_ROOM = 176  # what a person reads, and under it the word that goes into the file
    END_ROOM = 36    # one bound printed beside the slider
    SLIDE_ROOM = 120  # a handle is worth nothing on a groove nobody can aim at
    NUMBER_ROOM = 100  # the number itself, right aligned so the digits of the rows line up

    def __init__(self, key: str, info: dict, value, path: tuple, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.whole = info.get("type") == "integer"
        self.low, self.high = info.get("minimum"), info.get("maximum")
        self.step = info.get("multipleOf")
        # A slider counts whole steps, so its range is the real one multiplied up to them.
        self.scale = round(1 / self.step) if self.step else 0
        # The number a provider says it uses when the file says nothing. It is not written here: it
        # is only where the handle is left standing, so that taking the tick off starts a person at
        # the usual value rather than at the bottom of the range.
        self.start = info.get("default")
        self._held = value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        # A number the config already holds is never refused, however unlike the others the server
        # that wrote it was: the range opens to take it in, and the field says it lies outside.
        self._outside = False
        if self._held is not None:
            if self.low is None or self._held < self.low:
                self.low, self._outside = self._held, True
            if self.high is None or self._held > self.high:
                self.high, self._outside = self._held, True
        self._loading = True

        # The two words of one parameter: what a person reads, and under it the word the file keeps.
        # A grid rather than a column, because a grid asks a wrapping label how tall it wants to be
        # at the width it actually gave it; a column takes the size hint and clips the second line.
        words = QWidget()
        column = QGridLayout(words)
        column.setContentsMargins(0, 0, 0, 0)
        column.setVerticalSpacing(1)
        self.name_label = label(field_name(path, info), "fieldLabel", wrap=True)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        column.addWidget(self.name_label, 0, 0)
        column.addWidget(label(key, "mono"), 1, 0)
        column.setRowStretch(2, 1)
        column.setColumnStretch(0, 1)
        # The same width in every row, on purpose: seven numbers that do not begin at the same x are
        # seven separate boxes rather than one table. What keeps the groove wide is the floor under
        # the window's own width, not these columns quietly giving way to one another.
        words.setFixedWidth(self.NAME_ROOM)

        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        box.addWidget(words)

        self.use_default = QCheckBox(tr("model.default"))
        self.use_default.setCursor(Qt.CursorShape.PointingHandCursor)
        self.use_default.toggled.connect(self._switched)
        box.addWidget(self.use_default)

        self.slider = None
        # The groove and the two words printed at its ends: they are the same answer as the words
        # below, only held out to be aimed at. A row that writes nothing shows the words and hides
        # the aim, because a handle sitting on a number that will never be written is a lie about
        # the value — the first thing everyone reads off a slider.
        self.groove = []
        self.range_label = label(self._floor(), "hint")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if self.scale:
            self.groove.append(self._bound(self.low, Qt.AlignmentFlag.AlignRight))
            self.slider = QSlider(Qt.Orientation.Horizontal)
            self.slider.setMinimumWidth(self.SLIDE_ROOM)
            self.slider.setRange(round(self.low * self.scale), round(self.high * self.scale))
            self.slider.setPageStep(10 * self.scale)  # a click on the groove or a page key moves a tenth
            self.slider.valueChanged.connect(self._slid)
            if self.start is not None:
                self.slider.setValue(round(self.start * self.scale))
            self.groove.append(self.slider)
            self.groove.append(self._bound(self.high, Qt.AlignmentFlag.AlignLeft))
        for one in self.groove:
            box.addWidget(one, 1 if one is self.slider else 0)
        box.addWidget(self.range_label, 1)

        self.text = QLineEdit()
        self.text.setFixedWidth(self.NUMBER_ROOM)
        self.text.setAlignment(Qt.AlignmentFlag.AlignRight)
        if self.whole:
            bounds = QIntValidator(int(self.low), int(self.high), self)
        else:
            bounds = QDoubleValidator(float(self.low), float(self.high), 3, self)
        # The machine's own habit may write decimals with a comma; the config file never does. The
        # field guards the file's spelling, so a Russian macOS still types 0.7 and not 0,7.
        bounds.setLocale(QLocale.c())
        self.text.setValidator(bounds)
        self.text.textChanged.connect(self._typed)
        box.addWidget(self.text)

        self.setToolTip(f"{self._floor()}\n{tr('model.defaultHint')}\n\n{field_help(path, info)}")
        self.use_default.setToolTip(self.toolTip())
        self.set_value(value)
        self._loading = False

    def _bound(self, number, side) -> QLabel:
        edge = label(shown(number), "hint")
        edge.setFixedWidth(self.END_ROOM)
        edge.setAlignment(side | Qt.AlignmentFlag.AlignVCenter)
        return edge

    def _floor(self) -> str:
        """What the field accepts, said once and printed wherever it fits.

        The words matter: "-2 – 2" reads as a subtraction at a glance, so a closed range is spelled
        out as a range in the reader's own language, the same way an open one says "from 1".
        """
        if self.low == -MAX_SEED and self.high == MAX_SEED:
            said = tr("model.anyWhole")
        elif self.scale:
            said = tr("model.range", low=shown(self.low), high=shown(self.high))
        else:
            said = tr("model.atLeast", value=shown(self.low))
        return f"{said} · {tr('model.outside')}" if self._outside else said

    # ---- what the config will hold

    def value(self):
        """The number for the config, or MISSING while the field is left to say nothing."""
        path = ".".join(str(part) for part in self.path)
        if self.use_default.isChecked():
            return MISSING
        raw = self.text.text().strip().replace(",", ".")
        try:
            number = int(raw) if self.whole else float(raw)
        except ValueError:
            raise ValueError(path) from None
        if (self.low is not None and number < self.low) or (self.high is not None and number > self.high):
            raise ValueError(f"{path} — {self._floor()}")
        return number

    def set_value(self, value) -> None:
        """MISSING puts the tick back on; a number takes it off and writes the number in."""
        self._loading = True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self._held = value
        self.use_default.setChecked(value is MISSING)
        self.text.setText("" if value is MISSING else shown(value))
        self._sync()
        self._show_controls(value is not MISSING)
        self._loading = False

    # ---- the two ways a value is chosen

    def _switched(self, default: bool) -> None:
        if self._loading:
            return
        self._show_controls(not default)
        if default:
            # An empty field is the honest look of a word that will not be written. The number is
            # kept beside the field as it was, so taking the tick off again gives it back.
            self.text.setText("")
            return
        if self.text.text():
            return
        # Taking the tick off has to start somewhere: the number the config held, or the one the
        # provider says it uses. A count with no such word stays empty, and the number is the one
        # the user has to type.
        opening = self._held if self._held is not None else self.start
        if opening is not None:
            self._held = opening
            self.text.setText(shown(opening))
            self._sync()

    def _show_controls(self, written: bool) -> None:
        """Words or a groove, never both: a handle pointing at a number the file will not hold is
        the first thing a reader believes, and the wrong thing to believe."""
        self.text.setEnabled(written)
        self.range_label.setVisible(not written)
        for one in self.groove:
            one.setVisible(written)

    def _typed(self, raw: str) -> None:
        if self._loading:
            return
        try:
            self._held = float(raw.strip().replace(",", "."))
        except ValueError:
            return  # "-", "0." and "" are a number on its way, not a wrong one
        self._sync()

    def _slid(self, step: int) -> None:
        if self._loading:
            return
        self._held = step / self.scale
        self.text.blockSignals(True)
        self.text.setText(shown(self._held))
        self.text.blockSignals(False)

    def _sync(self) -> None:
        """The slider follows the number. It clamps to its own ends, which are the field's ends."""
        if self.slider is not None and self._held is not None:
            self.slider.setValue(round(float(self._held) * self.scale))


# The narrowest the model window may be dragged. Every row of the middle tab carries a name, two
# bounds, a groove and a number: the fixed parts of that take about 530 px before the groove itself
# starts, and a groove narrower than a hand is not a control but a decoration.
MODEL_WINDOW_MIN = 680


# A model entry has no fields for generation: the schema closes the entry itself but leaves
# `settings` free, and that map is where an AI SDK provider reads these names. They are spelled the
# way the SDK sends them, so `topP` reaches the server as `top_p`; a server wanting other words, or
# its own (`mirostat`, `repeat_penalty`), is served by the entry's `body` instead.
#
# The bounds are this app's, not opencode's — the schema leaves the map free — and they are the
# ranges every provider family agrees on, so a value one family rejects cannot be saved. Only the
# pairs that name a step get a slider: a step is what makes a range worth sliding over, and counts
# such as how many tokens or which K have none. `default` is the number the provider families say
# they use when the file says nothing, and it only parks the handle: it is never written by itself.
# A value already in the config is never refused; ParamField widens its own range to take it.
MODEL_PARAMS = (
    ("temperature", {"type": "number", "minimum": 0, "maximum": 2, "multipleOf": 0.05, "default": 1}),
    ("topP", {"type": "number", "minimum": 0, "maximum": 1, "multipleOf": 0.01, "default": 1}),
    ("topK", {"type": "integer", "minimum": 1, "maximum": MAX_TOKENS}),
    ("presencePenalty", {"type": "number", "minimum": -2, "maximum": 2, "multipleOf": 0.1, "default": 0}),
    ("frequencyPenalty", {"type": "number", "minimum": -2, "maximum": 2, "multipleOf": 0.1, "default": 0}),
    ("maxOutputTokens", {"type": "integer", "minimum": 1, "maximum": MAX_TOKENS}),
    ("seed", {"type": "integer", "minimum": -MAX_SEED, "maximum": MAX_SEED}),
    ("stopSequences", {"type": "array", "items": {"type": "string"}}),
)


class ModelSettingsDialog(ValueDialog):
    """One window with everything a model entry is allowed to say, in three tabs.

    The first is what the list row used to carry: whether the model shows in OpenCode, whether it
    calls tools, whether it takes images, and how large a context it gets. The middle holds the
    generation parameters, which opencode has no fields for because it leaves ``settings`` free and
    hands the names to the provider. The last carries the rest of opencode's own fields, read from
    its schema so the list cannot drift from what the backend reads.

    Nothing is written that the user did not touch: an entry that never mentioned tools keeps that
    silence after this window has been opened and closed again.
    """

    def __init__(self, parent: QWidget, provider_id: str, model_id: str, entry: dict) -> None:
        saved = entry.get("settings") if isinstance(entry.get("settings"), dict) else {}
        # What the config really held: clearing a row may only take away a word that was written.
        self.seeded = {key: saved[key] for key, _ in MODEL_PARAMS if key in saved}
        # The two answers a config file cannot give on its own; the main window fills both in.
        self.on_probe = None
        self.on_context = None
        self.touched: set[str] = set()
        self._building = True
        super().__init__(model_schema(), entry, ("providers", provider_id, "models", model_id), parent)
        self.setWindowTitle(tr("model.dialogTitle", model=model_id))
        self.setMinimumWidth(MODEL_WINDOW_MIN)
        self.model_id = model_id
        self.params = {}
        self.config_page = self._config_tab(saved)
        defaults = button(tr("model.defaults"), "ghost")
        self.defaults = defaults
        defaults.setToolTip(tr("model.defaultsHint"))
        defaults.clicked.connect(self.use_defaults)
        self.actions.insertWidget(0, defaults)
        self._three_parts(entry)
        self._building = False
        self._report()

    def _config_tab(self, saved: dict) -> QWidget:
        """The half of the entry the schema leaves free: the names an AI SDK provider reads itself."""
        body = QWidget()
        form = QVBoxLayout(body)
        form.setContentsMargins(*TAB_PADDING)
        form.setSpacing(10)
        form.addWidget(label(tr("model.params"), "fieldLabel"))
        form.addWidget(label(tr("model.paramsHint"), "hint", wrap=True))
        form.addWidget(label(tr("model.paramsBounds"), "hint", wrap=True))

        # One card for the numbers. Every row keeps the same widths, so the bounds and the typed
        # numbers read down the page as one table rather than as eight separate arguments.
        numbers = QFrame()
        numbers.setObjectName("settingRow")
        column = QVBoxLayout(numbers)
        column.setContentsMargins(14, 10, 14, 10)
        column.setSpacing(12)
        form.addWidget(numbers)
        for key, info in MODEL_PARAMS:
            path = (*self.path, "settings", key)
            if info.get("type") == "array":
                # A list of words has no range to draw; the ordinary editor of a list says it best.
                row = FieldRow(info, saved.get(key, MISSING), path)
                self.params[key] = row.control
                form.addWidget(row)
                continue
            field = ParamField(key, info, saved.get(key, MISSING), path)
            self.params[key] = field
            column.addWidget(field)
        form.addStretch(1)
        return scrolled(body)

    def _three_parts(self, entry: dict) -> None:
        """Words on top, the tabs and their page across the window, buttons underneath.

        The room the dialog keeps at its sides belongs to the words and the buttons, not to the
        body: the line the chosen tab stands on has to run from edge to edge, the way the strip's
        line does on the main screen. A layout does not accept negative margins, so the dialog is
        taken apart and put back rather than pushed past its own borders.
        """
        box = self.layout()
        room = box.contentsMargins().left()
        head, body, notice, error, actions = [], None, None, None, None
        while box.count():
            item = box.takeAt(0)
            widget = item.widget()
            if widget is None:
                actions = item.layout()  # the row that closes the dialog is the only layout in it
            elif isinstance(widget, QScrollArea):
                body = widget
            elif widget.objectName() == "settingsNotice":
                notice = widget
            elif widget.objectName() == "error":
                error = widget
            else:
                head.append(widget)

        self.content.setContentsMargins(*TAB_PADDING)  # the schema form was built to sit flat on a dialog
        tabs = QTabWidget()
        tabs.addTab(self._display_tab(entry), tr("dialog.tabDisplays"))
        tabs.insertTab(1, self.config_page, tr("dialog.tabConfig"))
        tabs.insertTab(2, body, tr("dialog.tabAdvanced"))
        self.tabs = tabs

        box.setContentsMargins(0, room, 0, room)
        for widget in head:
            box.addWidget(self._inset(widget, room))
        box.addWidget(tabs, 1)
        for widget in (notice, error):
            if widget:
                box.addWidget(self._inset(widget, room))
        if actions:
            buttons = QWidget()
            buttons.setLayout(actions)
            box.addWidget(self._inset(buttons, room))

    @staticmethod
    def _inset(widget: QWidget, room: int) -> QWidget:
        """One row put back into the room the dialog used to keep along its whole height."""
        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(room, 0, room, 0)
        row.addWidget(widget)
        return shell

    def _display_tab(self, entry: dict) -> QWidget:
        capabilities = entry.get("capabilities") if isinstance(entry.get("capabilities"), dict) else {}
        limit = entry.get("limit") if isinstance(entry.get("limit"), dict) else {}
        modalities = capabilities.get("input")

        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(*TAB_PADDING)
        column.setSpacing(10)

        self.visible = QCheckBox(tr("dialog.visible"))
        self.visible.setChecked(entry.get("disabled") is not True)
        self.visible.setCursor(Qt.CursorShape.PointingHandCursor)
        self.visible.toggled.connect(lambda _on: self._touch("visible"))
        column.addWidget(self.visible)

        column.addWidget(label(tr("dialog.capabilities"), "fieldLabel"))
        # A dash is the honest way to show a word the config never said: the choice is opencode's.
        self.tools = self._three_way("tools", "row.tools", capabilities.get("tools"),
            tr("row.toolsHint") if capabilities.get("tools") is not False else tr("row.noToolsHint"))
        column.addWidget(self.tools)

        self.images = self._three_way("images", "vision.images",
            None if not isinstance(modalities, list) else ("image" in modalities),
            tr("vision.configured") if isinstance(modalities, list) else tr("vision.unknownHint"))
        probe = button(tr("vision.test"), "ghost")
        probe.setToolTip(tr("vision.testHint"))
        probe.clicked.connect(lambda: self.on_probe and self.on_probe())
        self.probe_button = probe
        line = QHBoxLayout()
        line.addWidget(self.images)
        line.addWidget(probe)
        line.addStretch(1)
        column.addLayout(line)

        self.state = label("", "hint", wrap=True)
        column.addWidget(self.state)

        column.addWidget(label(tr("row.contextTitle"), "fieldLabel"))
        self.context = CountField(tr("dialog.contextNone"))
        self.context.setToolTip(tr("row.contextExact"))
        self.context.setText("" if not isinstance(limit.get("context"), int) else str(limit["context"]))
        self.context.textChanged.connect(self._count_changed)
        self.presets = QComboBox()
        self.presets.setToolTip(tr("row.contextPresets"))
        self.presets.addItem("")  # the slot a number that is not one of the usual sizes leaves empty
        for size in CONTEXT_PRESETS:
            self.presets.addItem(preset_label(size), size)
        self._sync_presets()
        self.presets.currentIndexChanged.connect(self._choose_preset)
        from_server = button(tr("row.contextApi"), "ghost")
        from_server.setToolTip(tr("row.contextApi"))
        from_server.clicked.connect(lambda: self.on_context and self.on_context())
        self.context_button = from_server
        window = QHBoxLayout()
        window.addWidget(self.context, 1)
        window.addWidget(self.presets)
        window.addWidget(from_server)
        column.addLayout(window)

        self.note = label("", "hint", wrap=True)
        column.addWidget(self.note)
        column.addWidget(label(tr("dialog.keep"), "hint", wrap=True))
        column.addStretch(1)
        return page

    def _three_way(self, name: str, key: str, value: bool | None, hint: str) -> QCheckBox:
        box = QCheckBox(tr(key))
        box.setTristate(True)
        box.setCursor(Qt.CursorShape.PointingHandCursor)
        box.setToolTip(hint)
        box.setCheckState(Qt.CheckState.PartiallyChecked if value is None
                          else Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
        box.stateChanged.connect(lambda _state: self._touch(name))
        return box

    def _touch(self, name: str) -> None:
        if not self._building:
            self.touched.add(name)
        self._report()

    def _count_changed(self, _text: str) -> None:
        """A typed number moves the preset list too: the two must never disagree."""
        self._touch("context")
        if not self._building:
            self._sync_presets()

    def _choose_preset(self, index: int) -> None:
        size = self.presets.itemData(index)
        # Setting the field is what records the change, so a preset and a typed number behave alike.
        if isinstance(size, int) and size != self.context.value():
            self.context.setValue(size)

    def _sync_presets(self) -> None:
        slot = self.presets.findData(self.context.value())
        self.presets.setCurrentIndex(slot if slot > 0 else 0)

    def _report(self) -> None:
        """Which words the entry will still not contain, and what that leaves to opencode."""
        if self._building or not hasattr(self, "state"):
            return
        quiet = []
        for box in (self.tools, self.images):
            if box.checkState() == Qt.CheckState.PartiallyChecked:
                quiet.append(f"{box.text()} — {tr('dialog.undecided')}")
        if not self.context.value():
            quiet.append(f"{tr('row.contextTitle')} — {tr('dialog.contextNone')}")
        self.state.setText(" · ".join(quiet))
        self.visible.setToolTip(tr("row.visibleHint" if self.visible.isChecked() else "row.hiddenHint"))

    def set_context(self, count: int) -> None:
        """A number the server gave, put into the field the user asked it in."""
        self.context.setValue(count)
        self._sync_presets()
        self.touched.add("context")
        self.note.setText(tr("row.contextRemote", count=f"{count:,}".replace(",", " ")))
        self._report()

    def report_probe(self, supported: bool | None, context: int | None, reason: str = "") -> None:
        """What the image test found, shown in the window it was asked for rather than behind it."""
        if supported is None:
            self.note.setText(tr("vision.undetermined", reason=reason))
        else:
            self.images.setCheckState(Qt.CheckState.Checked if supported else Qt.CheckState.Unchecked)
            self.touched.add("images")
            self.note.setText(tr("vision.enabled", model=self.model_id))
        if context and "context" not in self.touched:
            self.set_context(context)
        self._report()

    def set_notice(self, text: str) -> None:
        self.note.setText(text)

    def extend(self, result):
        """The parameters live inside ``settings``; the first tab writes the entry's own words."""
        saved = result.get("settings") if isinstance(result.get("settings"), dict) else {}
        for key, control in self.params.items():
            value = control.value()
            if value is MISSING:
                if key in self.seeded:
                    saved.pop(key, None)  # a number the config held, now cleared: opencode decides
            else:
                saved[key] = value
        if saved:
            result["settings"] = saved
        else:
            result.pop("settings", None)
        self._write_display(result)

    def _write_display(self, entry: dict) -> None:
        """Only what was touched. A box nobody moved leaves the entry exactly as it was."""
        if "visible" in self.touched:
            if self.visible.isChecked():
                entry.pop("disabled", None)  # showing a model again leaves no `disabled: false`
            else:
                entry["disabled"] = True
        if "tools" in self.touched or "images" in self.touched:
            capabilities = dict(entry["capabilities"]) if isinstance(entry.get("capabilities"), dict) else {}
            if "tools" in self.touched:
                # Both the checked and the dashed state leave the word out: opencode's own default
                # is a model that can call tools, and only its opposite needs to be written.
                if self.tools.checkState() == Qt.CheckState.Unchecked:
                    capabilities["tools"] = False
                else:
                    capabilities.pop("tools", None)
            if "images" in self.touched:
                state = self.images.checkState()
                if state == Qt.CheckState.PartiallyChecked:
                    capabilities.pop("input", None)
                else:
                    # The same shape config.set_model_vision writes, so both paths agree.
                    inputs = [item for item in capabilities.get("input", ["text"]) if isinstance(item, str)]
                    if state == Qt.CheckState.Checked:
                        if "image" not in inputs:
                            inputs.append("image")
                    else:
                        inputs = [item for item in inputs if item != "image"]
                    capabilities["input"] = inputs
                    capabilities.setdefault("output", ["text"])
            if capabilities:
                entry["capabilities"] = capabilities
            else:
                entry.pop("capabilities", None)
        if "context" in self.touched:
            count = self.context.value()
            if not count:
                entry.pop("limit", None)  # no limit at all is how the config says "you decide"
            else:
                limit = dict(entry["limit"]) if isinstance(entry.get("limit"), dict) else {}
                limit["context"] = count
                output = limit.get("output")
                if not isinstance(output, int) or isinstance(output, bool) or not 0 < output < count:
                    limit["output"] = min(32768, count // 2)
                entry["limit"] = limit

    def use_defaults(self):
        """Every field back to "not written", which is how opencode is told to decide for itself."""
        for control in [*self.rows.values(), *self.params.values()]:
            control.set_value(MISSING)
        if self.collection:
            self.collection.data = {}
            self.collection.fill()
        # The first tab decides the same way: every word taken out of the entry, deliberately.
        self.visible.setChecked(True)
        for box in (self.tools, self.images):
            box.setCheckState(Qt.CheckState.PartiallyChecked)
        self.context.setValue(0)


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

    def probe_vision(self, provider_id: str, model_id: str, dialog=None) -> None:
        """Sends two pictures to one model; the config learns the answer whether or not it said so.

        ``dialog`` is the model window that asked: it is on top of the banner, so the verdict goes
        into it as well, and the test itself has already written what it found.
        """
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        if not provider:
            return
        answer = QMessageBox.question(dialog or self, tr("vision.testHint"),
            tr("vision.confirm", model=model_id),
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
            if dialog:
                dialog.report_probe(result.supported, remote.context if remote else None, result.reason)
            if result.supported is True:
                self.show_banner(tr("vision.enabled", model=model_id), "success")
            else:
                self.show_banner(tr("vision.undetermined", reason=result.reason), "warning")

        def failed(error: str) -> None:
            self.busy = False
            self.render()
            if dialog:
                dialog.set_notice(tr("vision.failed", error=error))
            self.show_banner(tr("vision.failed", error=error), "danger")

        tasks.run(lambda: vision.probe_and_enable(self.config_file, provider_id, model_id, remote), done, failed)

    def configure_model(self, provider_id: str, model_id: str) -> None:
        """Every word one model entry is allowed to say, edited and written as a whole."""
        if self.busy:
            return
        dialog = ModelSettingsDialog(
            self, provider_id, model_id, self.config.read_model_entry(provider_id, model_id))
        # Two of the fields can only be answered by the server, and the window has to stay open
        # while the answer comes back, so both questions are handed to it rather than asked here.
        dialog.on_probe = lambda: self.probe_vision(provider_id, model_id, dialog)
        dialog.on_context = lambda: self.context_from_server(provider_id, model_id, dialog)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dialog.result_value

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.set_model_entry(provider_id, model_id, entry)
            config.save()

        self._run_write(work, tr("banner.modelUpdated", model=model_id))

    def context_from_server(self, provider_id: str, model_id: str, dialog) -> None:
        """Asks the server how large one model's context is and hands the number back to the window.

        Nothing is written here: the number only lands in the field, and the user decides whether
        to keep it. A closed window or an offline server leaves the field as it stood.
        """
        provider = self.config.provider(provider_id)
        if self.busy or not provider or not provider.base_url:
            return
        self.busy = True

        def done(result: Discovery) -> None:
            self.busy = False
            remote = next((model for model in result.models if model.id == model_id), None) if result.ok else None
            if remote and remote.context:
                dialog.set_context(remote.context)
            else:
                dialog.set_notice(tr("banner.contextNoApi", model=model_id))

        def failed(error: str) -> None:
            self.busy = False
            dialog.set_notice(tr("vision.failed", error=error))

        tasks.run(lambda: discovery.discover(provider.base_url, provider.api_key), done, failed)

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

    def edit_provider(self, provider_id: str) -> None:
        """The same dialog as for adding, told which provider it is repairing."""
        if self.busy:
            return
        provider = self.config.provider(provider_id)
        if not provider:
            return
        dialog = AddProviderDialog(
            self, set(), editing=(provider_id, provider.title, *self.config.connection(provider_id)))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        _, name, url, key = dialog.values()
        models = dialog.result_models if dialog.add_models.isChecked() else []

        def work() -> None:
            config = OpencodeConfig.load(self.config_file)
            config.edit_provider(provider_id, name, url, key)
            discovery.apply(config, provider_id, models, [])

        self.selected = provider_id
        self._run_write(work, tr("banner.providerEdited", name=name), refresh=True)

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
        menu.addAction(tr("provider.edit")).triggered.connect(lambda: self.edit_provider(provider.id))
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
            widget.configure.connect(lambda model, pid=provider.id: self.configure_model(pid, model))
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
