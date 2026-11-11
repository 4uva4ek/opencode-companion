"""Provider actions exercise the UI and real config writes without network requests."""
import json
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QApplication, QDialog, QInputDialog, QMessageBox, QPushButton, QScrollArea, QWidget)
from opencode_model_sync import window, i18n


@pytest.fixture
def view(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({"providers": {"local": {
        "name": "Local", "settings": {"baseURL": "http://localhost:1234/v1"}, "models": {}
    }}}))
    monkeypatch.setattr(window, "config_path", lambda: path)
    monkeypatch.setattr(window.MainWindow, "refresh", window.MainWindow._reload_config)
    def run(work, done, failed):
        try:
            result = work()
        except Exception as error:
            failed(str(error))
        else:
            done(result)
    monkeypatch.setattr(window.tasks, "run", run)
    widget = window.MainWindow()
    yield widget, path
    widget.close()
    widget.deleteLater()
    app.processEvents()


def action_menu(widget):
    # Rendering replaces widgets with deleteLater; use the current header layout.
    # The content layout is: the top bar, the provider header, the model list, the footer.
    header = widget.content_layout.itemAt(1).layout()
    return header.itemAt(header.count() - 1).widget().menu()


def menu_action(widget, key):
    """Menu entries are found by what they say: the order they were added in is not a contract."""
    return next(action for action in action_menu(widget).actions() if action.text() == i18n.tr(key))


def test_rename_action_persists_and_keeps_selection(view, monkeypatch):
    widget, path = view
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("Renamed", True))
    menu_action(widget, "provider.rename").trigger()
    assert json.loads(path.read_text())["providers"]["local"]["name"] == "Renamed"
    assert widget.selected == "local"
    assert widget.config.provider("local").title == "Renamed"


def test_remove_requires_confirmation_and_updates_selection(view, monkeypatch):
    widget, path = view
    original = path.read_text()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    menu_action(widget, "provider.remove").trigger()
    assert path.read_text() == original
    def confirm(*args):
        assert args[-1] == QMessageBox.StandardButton.No
        return QMessageBox.StandardButton.Yes
    monkeypatch.setattr(QMessageBox, "question", confirm)
    widget.checked["local"] = {"model"}
    menu_action(widget, "provider.remove").trigger()
    assert json.loads(path.read_text()) == {}, "a map that lost its last provider leaves with it"
    assert widget.selected is None
    assert "local" not in widget.checked


def test_cancel_and_empty_rename_do_not_write(view, monkeypatch):
    widget, path = view
    original = path.read_text()
    for value in [("Ignored", False), ("  ", True)]:
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: value)
        widget.rename_provider("local")
        assert path.read_text() == original
    assert widget.config.provider("local").title == "Local"
    assert not widget.busy


def rows_of(widget):
    return {row.row.id: row for row in widget.findChildren(window.ModelRowWidget)}


def write_models(widget, path, models: dict) -> None:
    """Puts the provider's models in place and shows them the way opening the file would."""
    data = json.loads(path.read_text())
    data["providers"]["local"]["models"] = models
    path.write_text(json.dumps(data))
    widget._reload_config()


def saved_models(path) -> dict:
    return json.loads(path.read_text())["providers"]["local"].get("models", {})


def open_model_window(widget, monkeypatch, model_id: str = "m", edit=None, accept: bool = True):
    """Goes the way the user goes: the gear, then the window, then the button that applies it.

    ``edit`` is what happens while the window stands open, so a test sees the same fields the
    user sees and the write that follows is the one the window really produced. ``accept=False``
    closes it the way Cancel does: the window is still there to be looked at, nothing is written.
    """
    shown = {}

    def exec(dialog):
        if edit:
            edit(dialog)
        if accept:
            dialog.finish()
        shown["dialog"] = dialog
        return QDialog.DialogCode.Accepted if accept else QDialog.DialogCode.Rejected

    monkeypatch.setattr(window.QDialog, "exec", exec)
    widget.configure_model("local", model_id)
    return shown["dialog"]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_row_is_its_name_its_status_and_one_way_in(view, language):
    """What the entry can say all moved behind the gear; the row keeps only what a model is."""
    widget, path = view
    previous = i18n.language()
    i18n.set_language(language)
    try:
        write_models(widget, path, {"m": {"disabled": True, "capabilities": {"tools": False}}})
        row = rows_of(widget)["m"]
        assert [control.text() for control in row.findChildren(QPushButton)] == [""]
        assert not row.settings_button.icon().isNull(), "the gear says what the button is for"
        assert row.settings_button.accessibleName() == i18n.tr("row.settings")
        assert row.settings_button.toolTip() == i18n.tr("row.settingsHint")
        line = row.layout()
        assert line.itemAt(line.count() - 1).widget() is row.settings_button, "the way in ends the row"
        assert bool(row.property("off")), "a hidden model is still marked hidden where it stands"
        widget.busy = True
        widget.render()
        assert not rows_of(widget)["m"].isEnabled()
    finally:
        i18n.set_language(previous)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_gear_opens_the_model_window_on_its_display_tab(view, monkeypatch, language):
    widget, path = view
    previous = i18n.language()
    i18n.set_language(language)
    try:
        write_models(widget, path, {"m": {}})
        seen = {}

        def exec(dialog):
            seen["tabs"] = [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())]
            seen["current"] = dialog.tabs.currentIndex()
            return QDialog.DialogCode.Rejected

        monkeypatch.setattr(window.QDialog, "exec", exec)
        rows_of(widget)["m"].settings_button.click()
        assert seen["tabs"] == [i18n.tr("dialog.tabDisplays"), i18n.tr("dialog.tabConfig"),
                               i18n.tr("dialog.tabAdvanced")]
        assert seen["current"] == 0, "the display of a model comes before its parameters"
    finally:
        i18n.set_language(previous)


def test_the_display_tab_writes_only_what_the_user_moved(view, monkeypatch):
    """The window may be looked at as often as liked: silence in the config stays silence."""
    widget, path = view
    write_models(widget, path, {"on": {"capabilities": {"tools": True}}, "off": {"disabled": True}})

    open_model_window(widget, monkeypatch, "on")
    open_model_window(widget, monkeypatch, "off")
    assert saved_models(path) == {"on": {"capabilities": {"tools": True}}, "off": {"disabled": True}}

    open_model_window(widget, monkeypatch, "on", lambda dialog: dialog.tools.setCheckState(Qt.CheckState.Unchecked))
    assert saved_models(path)["on"] == {"capabilities": {"tools": False}}

    open_model_window(widget, monkeypatch, "on", lambda dialog: dialog.visible.setChecked(False))
    assert saved_models(path)["on"] == {"capabilities": {"tools": False}, "disabled": True}

    # Showing a model again takes the word out instead of leaving `disabled: false` behind.
    open_model_window(widget, monkeypatch, "off", lambda dialog: dialog.visible.setChecked(True))
    assert saved_models(path)["off"] == {}

    open_model_window(widget, monkeypatch, "off", lambda dialog: dialog.images.setCheckState(Qt.CheckState.Checked))
    assert saved_models(path)["off"] == {"capabilities": {"input": ["text", "image"], "output": ["text"]}}

    # A box moved back to the dash gives its word up: opencode is allowed to decide again.
    open_model_window(widget, monkeypatch, "off",
                      lambda dialog: dialog.images.setCheckState(Qt.CheckState.PartiallyChecked))
    assert "input" not in saved_models(path)["off"].get("capabilities", {})


def test_the_display_tab_leaves_untouched_words_where_they_were(view, monkeypatch):
    """A field the user did not move cannot rewrite a part of the entry the window never showed."""
    widget, path = view
    write_models(widget, path, {"m": {"name": "Qwen", "settings": {"mirostat": 2},
                              "limit": {"context": 200000, "output": 8192}}})
    open_model_window(widget, monkeypatch, "m", lambda dialog: dialog.visible.setChecked(False))
    assert saved_models(path)["m"] == {
        "name": "Qwen", "settings": {"mirostat": 2},
        "limit": {"context": 200000, "output": 8192}, "disabled": True}


def test_the_display_tab_sizes_the_context_in_the_usual_steps(view, monkeypatch):
    """A preset and a typed number are the same decision; a K is 1024 tokens, so 384K is 393 216."""
    widget, path = view
    write_models(widget, path, {"m": {}})
    dialog = open_model_window(widget, monkeypatch, "m")
    assert dialog.context.value() == 0
    assert dialog.context.placeholderText() == i18n.tr("dialog.contextNone")
    assert saved_models(path)["m"] == {}

    assert [dialog.presets.itemData(index) for index in range(1, dialog.presets.count())] == [
        8192, 16384, 32768, 65536, 131072, 204800, 262144, 393216, 524288, 786432, 1048576]
    assert [dialog.presets.itemText(index) for index in range(1, dialog.presets.count())] == [
        "8K · 8 192", "16K · 16 384", "32K · 32 768", "64K · 65 536", "128K · 131 072",
        "200K · 204 800", "256K · 262 144", "384K · 393 216", "512K · 524 288",
        "768K · 786 432", "1024K · 1 048 576"]

    open_model_window(widget, monkeypatch, "m",
                      lambda dialog: dialog.presets.setCurrentIndex(dialog.presets.findData(393216)))
    assert saved_models(path)["m"] == {"limit": {"context": 393216, "output": 32768}}

    # A number that is nobody's preset is writable too, and it moves the list along with it.
    typed = window.ModelSettingsDialog(widget, "local", "m", saved_models(path)["m"])
    typed.context.setValue(100000)
    assert typed.presets.currentIndex() == 0 and typed.presets.currentData() is None
    typed.context.setValue(393216)
    assert typed.presets.currentData() == 393216
    typed.deleteLater()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_provider_menu_is_translated_and_disabled_during_save(view, language):
    widget, _ = view
    previous = i18n.language()
    try:
        i18n.set_language(language)
        widget.busy = True
        widget.render()
        menu = action_menu(widget)
        assert [a.text() for a in menu.actions()] == [
            i18n.tr("provider.edit"), i18n.tr("provider.rename"), i18n.tr("provider.remove")]
        assert not menu.parentWidget().isEnabled()
    finally:
        i18n.set_language(previous)


def test_the_display_tab_shows_an_unwritten_capability_as_an_open_question(view, monkeypatch):
    """Nothing in the config said anything about images: the window must not pretend otherwise."""
    widget, path = view
    write_models(widget, path, {'m': {'capabilities': {'tools': False}, 'limit': {'context': 123, 'output': 45}}})
    dialog = open_model_window(widget, monkeypatch, 'm')
    assert dialog.tools.checkState() == Qt.CheckState.Unchecked
    assert dialog.images.checkState() == Qt.CheckState.PartiallyChecked
    assert i18n.tr('dialog.undecided') in dialog.state.text(), "the window says what it will not write"
    assert saved_models(path)['m'] == {'capabilities': {'tools': False},
                                       'limit': {'context': 123, 'output': 45}}

    def both(dialog):
        dialog.images.setCheckState(Qt.CheckState.Checked)
        dialog.context.setValue(0)  # the limit the config holds, given back to opencode
    open_model_window(widget, monkeypatch, 'm', both)
    assert saved_models(path)['m'] == {'capabilities': {'tools': False, 'input': ['text', 'image'],
                                                        'output': ['text']}}
    open_model_window(widget, monkeypatch, 'm',
                      lambda dialog: dialog.images.setCheckState(Qt.CheckState.Unchecked))
    assert saved_models(path)['m']['capabilities']['input'] == ['text']


def test_the_image_test_is_confirmed_before_it_costs_anything(view, monkeypatch):
    widget, path = view
    write_models(widget, path, {'m': {}})
    calls = []
    monkeypatch.setattr(widget, 'show_banner', lambda text, tone: calls.append((text, tone)))
    monkeypatch.setattr(window.QMessageBox, 'question', lambda *a, **kw: QMessageBox.StandardButton.No)
    monkeypatch.setattr(window.tasks, 'run', lambda *a: pytest.fail('no request without confirmation'))
    open_model_window(widget, monkeypatch, 'm', lambda dialog: dialog.probe_button.click(), accept=False)
    assert not calls and saved_models(path)['m'] == {}


def test_the_image_test_reports_into_the_window_it_was_asked_from(view, monkeypatch):
    """The test is run for the window that is standing open, so its answer belongs there too."""
    widget, path = view
    write_models(widget, path, {'m': {}})
    monkeypatch.setattr(window.QMessageBox, 'question', lambda *a, **kw: QMessageBox.StandardButton.Yes)
    queued = []
    monkeypatch.setattr(window.tasks, 'run', lambda work, done, failed: queued.append((work, done, failed)))
    monkeypatch.setattr(window.vision, 'probe', lambda *a, **kw: window.vision.ProbeResult(True))
    before = path.read_text()
    dialog = open_model_window(widget, monkeypatch, 'm', lambda item: item.probe_button.click(), accept=False)
    assert widget.busy and len(queued) == 1
    assert path.read_text() == before, "a click only queues the request"
    assert dialog.images.checkState() == Qt.CheckState.PartiallyChecked, "the answer is not in yet"
    work, done, failed = queued[0]
    done(work())
    assert not widget.busy
    assert saved_models(path)['m']['capabilities']['input'] == ['text', 'image']
    assert dialog.images.checkState() == Qt.CheckState.Checked
    assert dialog.note.text() == i18n.tr('vision.enabled', model='m')


def test_sync_button_enriches_existing_model(view):
    widget, path = view
    data = json.loads(path.read_text())
    data['providers']['local']['models']['m'] = {'name': 'Custom name', 'capabilities': {'tools': False}}
    path.write_text(json.dumps(data))
    widget._reload_config()
    widget.results['local'] = window.Discovery(True, models=[window.RemoteModel('m', vision=True)])
    widget.sync('local')
    saved = json.loads(path.read_text())['providers']['local']['models']['m']
    assert saved == {'name': 'Custom name',
                     'capabilities': {'tools': False, 'input': ['text', 'image'], 'output': ['text']}}


def test_the_edit_dialog_locks_the_id_and_hints_at_a_saved_key(view):
    widget, path = view
    dialog = window.AddProviderDialog(widget, set(), editing=("local", "Local", "http://localhost:1234/v1", "secret"))
    assert dialog.ident.text() == "local" and dialog.ident.isReadOnly()
    assert dialog.name.text() == "Local"
    assert dialog.url.text() == "http://localhost:1234/v1"
    assert dialog.key.text() == "", "the saved key is hinted at, never shown"
    assert i18n.tr("dialog.keyKeep") in dialog.key.placeholderText()
    assert dialog.values()[2] == "http://localhost:1234/v1"
    dialog.deleteLater()


def test_edit_provider_updates_connection_through_the_dialog(view, monkeypatch):
    widget, path = view
    seen = {}

    class StubDialog:
        def __init__(self, parent, existing, preset=None, editing=None):
            self.editing = editing
            seen['editing'] = editing
            self.add_models = SimpleNamespace(isChecked=lambda: False)
            self.result_models = []

        def exec(self):
            return QDialog.DialogCode.Accepted

        def values(self):
            return (self.editing[0], "Strata PC", "http://192.168.1.5:1234/v1", None)

    monkeypatch.setattr(window, "AddProviderDialog", StubDialog)
    widget.edit_provider("local")
    assert seen['editing'] == ("local", "Local", "http://localhost:1234/v1", None)
    saved = json.loads(path.read_text())['providers']['local']
    assert saved['name'] == "Strata PC"
    assert saved['settings'] == {"baseURL": "http://192.168.1.5:1234/v1"}
    assert 'package' not in saved, "an edit invents nothing the provider never had"


def test_the_server_answers_into_the_field_and_only_the_user_applies_it(view, monkeypatch):
    """«Take from the server» fills the field; the config waits for the button that applies."""
    widget, path = view
    write_models(widget, path, {"m": {"limit": {"context": 200000, "output": 8192}}})
    seen = {}

    def ask(dialog):
        dialog.context_button.click()
        seen.update(field=dialog.context.value(), preset=dialog.presets.currentData(),
                    note=dialog.note.text(), file=path.read_text())

    def fake_discover(url, key):
        assert url == "http://localhost:1234/v1"
        return window.Discovery(True, models=[window.RemoteModel("m", context=393216)])

    monkeypatch.setattr(window.discovery, "discover", fake_discover)
    open_model_window(widget, monkeypatch, "m", ask)
    assert seen["field"] == 393216 and seen["preset"] == 393216
    assert seen["note"] == i18n.tr("row.contextRemote", count="393 216")
    assert json.loads(seen["file"])["providers"]["local"]["models"]["m"]["limit"] == {
        "context": 200000, "output": 8192}, "an answer nobody applied has not been written"
    assert saved_models(path)["m"]["limit"] == {"context": 393216, "output": 8192}, "the number is applied"

    # A server that says nothing about one model says so in the window, and the field keeps the number.
    monkeypatch.setattr(window.discovery, "discover",
                        lambda url, key: window.Discovery(False, error="offline"))
    quiet = {}

    def ask_without_an_answer(dialog):
        quiet["field"] = dialog.context.value()
        dialog.context_button.click()
        quiet["note"] = dialog.note.text()
        quiet["kept"] = dialog.context.value()

    open_model_window(widget, monkeypatch, "m", ask_without_an_answer)
    assert quiet["note"] == i18n.tr("banner.contextNoApi", model="m")
    assert quiet["field"] == quiet["kept"] == 393216


ENTRY = {"name": "Qwen", "limit": {"context": 32768, "output": 4096},
         "settings": {"temperature": 0.7, "mirostat": 2}}


def test_the_model_window_lists_every_field_opencode_allows(view):
    """The point of the window: the list comes from the schema, so it cannot fall behind opencode."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    assert list(dialog.rows) == [
        "modelID", "family", "name", "releaseDate", "compatibility", "package", "settings",
        "headers", "body", "capabilities", "variants", "cost", "disabled", "limit"]
    assert list(dialog.params) == [key for key, _ in window.MODEL_PARAMS]
    assert dialog.windowTitle() == i18n.tr("model.dialogTitle", model="m")
    assert dialog.params["temperature"].value() == 0.7, "the config is what the field starts from"
    assert dialog.params["topP"].value() is window.MISSING, "a written word about one field is not a word about all"
    assert "providers.local.models.m.settings.topP" in dialog.params["topP"].toolTip()
    dialog.deleteLater()


def test_the_generation_parameters_hold_the_middle_tab(view):
    """What the schema has no fields for gets a tab of its own, between the two it came between."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    assert [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())] == [
        i18n.tr("dialog.tabDisplays"), i18n.tr("dialog.tabConfig"), i18n.tr("dialog.tabAdvanced")]
    assert dialog.tabs.widget(1) is dialog.config_page

    def within(page, control) -> bool:
        parent = control.parent()
        while parent is not None:
            if parent is page:
                return True
            parent = parent.parent()
        return False

    body = dialog.config_page.widget()
    assert all(within(body, control) for control in dialog.params.values())
    assert not any(within(body, control) for control in dialog.rows.values())
    dialog.deleteLater()


def test_the_window_is_three_parts_words_tabs_buttons(view):
    """The words and the buttons keep their room; the body of the tabs is what spans the window."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    box = dialog.layout()
    outer = box.contentsMargins()
    assert (outer.left(), outer.right()) == (0, 0), "the page of the tabs reaches both edges"
    assert dialog.tabs.parentWidget() is dialog, "the body belongs to the window, not to a shelf"

    rows = [box.itemAt(index).widget() for index in range(box.count())]
    sheltered = [row.layout().contentsMargins().left() for row in rows
                 if row is not dialog.tabs and row.layout() is not None]
    assert sheltered and all(room == 18 for room in sheltered), sheltered
    dialog.deleteLater()


def test_a_long_path_takes_the_lines_it_needs(view):
    """The path of a nested field is one long word; a narrow window gives it lines, never a cut."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "strata-pc-office", "gpt-oss-120b-instruct-abliterated", ENTRY)
    dialog.resize(window.MODEL_WINDOW_MIN, 620)  # the narrowest the window lets itself be
    dialog.show()
    dialog.tabs.setCurrentIndex(dialog.tabs.count() - 1)
    app = QApplication.instance()
    for _ in range(8):
        app.processEvents()
    try:
        deep = []
        for row in dialog.findChildren(window.FieldRow):
            one_line = row.key_label.fontMetrics().lineSpacing()
            if row.key_label.heightForWidth(row.key_label.width()) >= 2 * one_line:
                deep.append(row)
        assert deep, "a path this long in a window this narrow has to wrap somewhere"
        for row in deep:
            assert row.key_label.height() >= row.key_label.heightForWidth(row.key_label.width()), \
                f"{row.key_label.text()} is cut off"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_nothing_is_left_without_a_place_in_the_window(view):
    """A widget the layout forgot is drawn in the corner of the window over everything else."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)

    def placed_in(box):
        found = set()
        for index in range(box.count()):
            item = box.itemAt(index)
            if item.layout():
                found |= placed_in(item.layout())
            holder = item.widget()
            if holder:
                found.add(holder)
                if holder.layout():  # the rows of the header and the footer sit inside a wrapper
                    found |= placed_in(holder.layout())
        return found

    placed = placed_in(dialog.layout())
    direct = [child for child in dialog.children() if isinstance(child, QWidget)]
    forgotten = [child for child in direct if child not in placed]
    assert not forgotten, [f"{type(one).__name__}:{one.objectName()}" for one in forgotten]
    named = {child.objectName() for child in placed if isinstance(child, window.QLabel)}
    assert {"settingsNotice", "error"} <= named, "both notes still have a row of their own"
    dialog.deleteLater()


def test_every_tab_keeps_its_content_away_from_the_frame(view):
    """The pane draws a line around a tab; nothing should start on top of it."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    assert dialog.tabs.count() == 3
    for index in range(dialog.tabs.count()):
        page = dialog.tabs.widget(index)
        page = page.widget() if isinstance(page, QScrollArea) else page
        box = page.layout().contentsMargins()
        assert (box.left(), box.top(), box.right(), box.bottom()) == window.TAB_PADDING, index
    dialog.deleteLater()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_model_window_names_its_fields_in_both_languages(view, language):
    widget, _ = view
    previous = i18n.language()
    i18n.set_language(language)
    try:
        dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
        named = {".".join(str(part) for part in row.path[-2:]): row.title.text()
                 for row in dialog.findChildren(window.FieldRow)}
        named |= {f"settings.{field.path[-1]}": field.name_label.text()
                  for field in dialog.findChildren(window.ParamField)}
        for key, _info in window.MODEL_PARAMS:
            assert named[f"settings.{key}"] not in ("", key), f"{key} is spelled for a human"
        assert i18n.tr("model.params") in [row.text() for row in dialog.findChildren(window.QLabel)]
        assert dialog.defaults.text() == i18n.tr("model.defaults")
        dialog.deleteLater()
    finally:
        i18n.set_language(previous)


def set_number(field, text: str) -> None:
    """The same for a bounded parameter: the tick comes off before a number means anything."""
    field.use_default.setChecked(False)
    field.text.setText(text)


def test_the_model_window_puts_parameters_back_into_the_settings_map(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    set_number(dialog.params["topP"], "0.9")
    set_number(dialog.params["topK"], "40")
    dialog.finish()
    assert not dialog.error.text()
    assert dialog.result_value == {
        "name": "Qwen", "limit": {"context": 32768, "output": 4096},
        # The provider's own word survives: this app only writes the fields it showed.
        "settings": {"temperature": 0.7, "mirostat": 2, "topP": 0.9, "topK": 40}}
    dialog.deleteLater()


def test_a_parameter_left_ticked_writes_nothing_at_all(view):
    """The tick is the entry's way of not answering; only an unticked field hands over a number."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"temperature": 0.7}})
    assert not dialog.params["temperature"].use_default.isChecked(), "what the file named starts written"
    assert dialog.params["topK"].use_default.isChecked(), "what the file never named starts untold"
    assert dialog.params["topK"].value() is window.MISSING
    set_number(dialog.params["seed"], "17")
    dialog.finish()
    assert not dialog.error.text()
    assert dialog.result_value == {"settings": {"temperature": 0.7, "seed": 17}}
    dialog.deleteLater()


def test_every_parameter_prints_the_numbers_it_accepts(view):
    """No field here is a bare box: the ends of its range are on show, not hidden in a tooltip only."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    seen = 0
    for key, info in window.MODEL_PARAMS:
        if info.get("type") not in ("number", "integer"):
            continue  # a level named in words and a list of words have no range to print
        seen += 1
        field = dialog.params[key]
        assert info.get("minimum") is not None and info.get("maximum") is not None, key
        # A slider is only honest over a range that can be walked in whole steps.
        assert (field.slider is not None) == ("multipleOf" in info), key
        if "multipleOf" in info:
            expected = i18n.tr("model.range", low=window.shown(info["minimum"]),
                               high=window.shown(info["maximum"]))
        elif info["minimum"] == -window.MAX_SEED:
            expected = i18n.tr("model.anyWhole")
        else:
            expected = i18n.tr("model.atLeast", value=window.shown(info["minimum"]))
        assert expected in field.toolTip(), key
    assert seen == 8, "every number the window offers is bounded; a ninth comes with its own bounds"
    for key, info in window.MODEL_PARAMS:
        if info.get("type") in ("number", "integer"):
            continue
        # What is not a number is written by the same editor the schema forms use, and it starts
        # saying nothing, like every other field of an entry the file never named.
        assert dialog.params[key].value() is window.MISSING, key


def test_a_number_outside_the_printed_bounds_is_refused_by_the_field_itself(view):
    """The bounds are not decoration: the field does not let the wrong number be typed in."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    penalty = dialog.params["frequencyPenalty"].text.validator()
    assert penalty.validate("-3", 0)[0] != QValidator.State.Acceptable
    assert penalty.validate("1.5", 0)[0] == QValidator.State.Acceptable
    tokens = dialog.params["maxOutputTokens"].text.validator()
    assert tokens.validate("0", 0)[0] != QValidator.State.Acceptable
    assert tokens.validate("4096", 0)[0] == QValidator.State.Acceptable
    dialog.deleteLater()


def test_a_number_the_config_already_holds_is_never_refused(view):
    """A server that was told otherwise is not corrected behind anyone's back: the range opens up."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"temperature": 4}})
    field = dialog.params["temperature"]
    assert field.value() == 4
    assert i18n.tr("model.outside") in field.toolTip()
    dialog.finish()
    assert not dialog.error.text() and dialog.result_value == {"settings": {"temperature": 4}}
    dialog.deleteLater()


def test_sliding_a_parameter_writes_the_number_it_stopped_at(view):
    """The slider is the coarse way in; the number it leaves in the field is what gets saved."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"temperature": 0.7}})
    field = dialog.params["temperature"]
    assert field.slider.value() == round(0.7 * field.scale), "the handle starts at the config's number"
    field.slider.setValue(round(1.25 * field.scale))
    assert field.text.text() == "1.25"
    dialog.finish()
    assert not dialog.error.text()
    assert dialog.result_value == {"settings": {"temperature": 1.25}}
    dialog.deleteLater()


def test_taking_the_tick_off_gives_the_config_s_own_number_back(view):
    """A field the file named goes back to its own number, and the groove comes back with it."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"temperature": 0.7}})
    field = dialog.params["temperature"]
    assert not field.slider.isHidden() and field.range_label.isHidden()
    field.use_default.click()
    assert field.text.text() == "" and field.value() is window.MISSING
    assert field.slider.isHidden(), "no handle may point at a number the file will not hold"
    assert not field.range_label.isHidden(), "the bounds are still said, only without the groove"
    field.use_default.click()
    assert not field.slider.isHidden() and field.text.text() == "0.7" and field.value() == 0.7
    dialog.deleteLater()


def test_an_unnamed_field_unticks_to_the_number_the_provider_says_it_uses(view):
    """The starting point of a field nobody wrote is the usual value, not the bottom of the range."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    nucleus = dialog.params["topP"]
    assert nucleus.value() is window.MISSING and nucleus.text.text() == ""
    nucleus.use_default.click()
    assert nucleus.value() == 1 and nucleus.text.text() == "1"
    assert nucleus.slider.value() == nucleus.slider.maximum(), "the handle stands at that same number"
    seed = dialog.params["seed"]
    seed.use_default.click()
    assert seed.text.text() == "", "a count no provider names stays a number to type in"
    try:
        seed.value()
    except ValueError as said:
        assert str(said).endswith("settings.seed"), said
    else:
        raise AssertionError("a field that offered to write but holds no number is not a silence")
    dialog.deleteLater()


def test_a_field_that_offers_to_write_but_holds_no_number_is_refused_by_name(view):
    """A count the user asked to write but never typed cannot pass quietly as nothing at all."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    dialog.params["maxOutputTokens"].use_default.setChecked(False)
    dialog.finish()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert "providers.local.models.m.settings.maxOutputTokens" in dialog.error.text()
    dialog.deleteLater()


def test_the_parameter_rows_keep_their_columns(view):
    """The numbers read down one column at every width the window can be, groove included."""
    widget, _ = view
    # Every field written on purpose: a field left to the provider hides its groove, and the width
    # of a hidden groove is a number the layout stopped maintaining, not a column it disagrees on.
    written = {"settings": {"temperature": 0.7, "topP": 0.9, "presencePenalty": 0.1,
                            "frequencyPenalty": 0.2, "topK": 40, "minP": 0.05,
                            "maxOutputTokens": 4096, "seed": 3}}
    dialog = window.ModelSettingsDialog(widget, "local", "m", written)
    dialog.show()
    dialog.tabs.setCurrentIndex(1)
    app = QApplication.instance()
    try:
        for width in (window.MODEL_WINDOW_MIN, 900):
            dialog.resize(width, 660)
            for _ in range(8):
                app.processEvents()
            fields = [one for one in dialog.params.values() if isinstance(one, window.ParamField)]
            assert len(fields) == sum(1 for _, info in window.MODEL_PARAMS
                                      if info.get("type") in ("number", "integer"))
            starts = {one.mapTo(dialog, one.rect().topLeft()).x() for one in fields}
            numbers = {one.text.mapTo(dialog, one.text.rect().topLeft()).x() for one in fields}
            assert len(starts) == 1 and len(numbers) == 1, (width, starts, numbers)
            slides = {one.slider.width() for one in fields if one.slider is not None}
            assert len(slides) == 1 and min(slides) >= window.ParamField.SLIDE_ROOM, (width, slides)
            widest = fields[0].text.fontMetrics().horizontalAdvance(str(window.MAX_SEED))
            assert widest + 20 <= fields[0].text.width(), "the largest number the field takes fits in it"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def test_the_model_window_refuses_a_value_the_schema_refuses(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    dialog.params["temperature"].text.setText("not a number")
    dialog.finish()
    assert dialog.result() != QDialog.DialogCode.Accepted and dialog.error.text()
    dialog.deleteLater()


def test_the_defaults_button_leaves_the_entry_empty(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", ENTRY)
    dialog.defaults.click()
    assert all(control.value() is window.MISSING for control in dialog.rows.values())
    assert all(control.value() is window.MISSING for control in dialog.params.values())
    dialog.finish()
    assert not dialog.error.text()
    assert dialog.result_value == {}, "nothing written is how opencode is asked to decide again"
    dialog.deleteLater()


def test_configuring_a_model_writes_the_entry_the_window_returned(view, monkeypatch):
    widget, path = view
    data = json.loads(path.read_text())
    data["providers"]["local"]["models"]["m"] = ENTRY
    path.write_text(json.dumps(data))
    widget._reload_config()
    widget.render()
    seen = {}

    class StubDialog:
        def __init__(self, parent, provider_id, model_id, entry):
            seen.update(provider=provider_id, model=model_id, entry=entry)
            self.result_value = {"settings": {"temperature": 0.5}, "headers": {}, "disabled": False}

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(window, "ModelSettingsDialog", StubDialog)
    rows_of(widget)["m"].settings_button.click()
    assert seen["provider"] == "local" and seen["entry"] == ENTRY
    saved = json.loads(path.read_text())["providers"]["local"]["models"]["m"]
    assert saved == {"settings": {"temperature": 0.5}, "disabled": False}, (
        "an empty field is left out; a refusal is a word of its own")


def test_a_cancelled_model_window_writes_nothing(view, monkeypatch):
    widget, path = view
    data = json.loads(path.read_text())
    data["providers"]["local"]["models"]["m"] = ENTRY
    path.write_text(json.dumps(data))
    widget._reload_config()
    widget.render()

    class StubDialog:
        def __init__(self, parent, provider_id, model_id, entry):
            self.result_value = {"disabled": True}

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(window, "ModelSettingsDialog", StubDialog)
    before = path.read_text()
    rows_of(widget)["m"].settings_button.click()
    assert path.read_text() == before
    assert not widget.busy
