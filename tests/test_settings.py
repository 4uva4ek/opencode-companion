"""Real JSONC edits and schema-backed Qt workflows, without touching user config."""
import json
import os
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from opencode_model_sync import settings, i18n, window
from opencode_model_sync.config import ConfigError, strip_jsonc
from opencode_model_sync.settings import MISSING
from opencode_model_sync.settings_view import SettingsPanel, ValueDialog, ValueControl


@pytest.fixture
def app():
    result = QApplication.instance() or QApplication([])
    i18n.set_language("en")
    yield result
    result.processEvents()


def choose(control, kind, value):
    index = next(i for i, (k, v) in enumerate(control.choices) if k == kind and settings.equal(v, value))
    control.mode.setCurrentIndex(index)


def type_text(control, text):
    if control.suggestions is not None:
        control.suggestions.setCurrentText(text)
    else:
        control.text.setText(text)
        control.text.textEdited.emit(text)


def test_complete_schema_and_local_references():
    schema = settings.schema()
    assert len(schema["properties"]) == 29
    assert "x-legacy" not in schema
    assert {field.path[0] for field in settings.fields()} == set(schema["properties"])
    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                assert node["$ref"].startswith("#/$defs/")
                settings.resolve(node)
            for child in node.values(): walk(child)
        elif isinstance(node, list):
            for child in node: walk(child)
    walk(schema)


@pytest.mark.parametrize("text,target", [
    ('{\n// keep\n"a":1, "b":2, "c":3,\n}', {"c": 3}),
    ('{"a":1, /* keep */ "b":2}', {"a": 1}),
    ('{"a":1 // keep\n}', {"a": 1, "b": False}),
    ('{/* keep */}', {"a": {"nested": [1, 2]}}),
    ('{"a":{"x":1,"y":2},"url":"https://x//y"}', {"a": {"y": 0}, "url": "https://x//y"}),
    ('{"a":1,"b":2,"c":3}', {}),
    ('{"a":false}', {"a": 0}),
    ('{"a":[1,2]}', {"a": ["русский", {"x": True}]}),
    ('', {"x": "new"}),
])
def test_jsonc_patches(text, target):
    result = settings.patch_text(text, target)
    assert settings.equal(json.loads(strip_jsonc(result)), target)
    if "keep" in text: assert "keep" in result


def test_sparse_save_preserves_unrelated_external_changes_and_comments(tmp_path):
    path = tmp_path / "opencode.jsonc"
    original = '{\n// providers unchanged\n"custom": {"secret":"${TOKEN}"},\n"experimental":{"todo":true}\n}\n'
    path.write_text(original, encoding="utf-8")
    base = json.loads(strip_jsonc(original))
    latest = original.replace('"todo":true', '"todo":true,"subagent_depth":3')
    path.write_text(latest, encoding="utf-8")
    result = settings.save(path, base, {("experimental", "todo"): False})
    assert result == {"custom": {"secret": "${TOKEN}"}, "experimental": {"todo": False, "subagent_depth": 3}}
    assert path.read_text() == latest.replace('"todo":true', '"todo":false')
    assert next(tmp_path.glob("*.bak-model-sync-*")).read_text() == latest
    settings.save(path, result, {("experimental", "todo"): MISSING})
    assert json.loads(strip_jsonc(path.read_text()))["experimental"] == {"subagent_depth": 3}


def test_conflict_does_not_write(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text('{"username":"other"}')
    with pytest.raises(settings.Conflict):
        settings.save(path, {"username": "before"}, {("username",): "mine"})
    assert path.read_text() == '{"username":"other"}'
    assert not list(tmp_path.glob("*.bak*"))


def test_validation_and_reset():
    with pytest.raises(ConfigError):
        settings.merge({}, {}, {("experimental", "subagent_depth"): -1})
    with pytest.raises(ConfigError):
        settings.merge({}, {}, {("update",): "unexpected"})
    assert settings.merge({"experimental": {"todo": True}}, {"experimental": {"todo": True}},
                          {("experimental", "todo"): MISSING}) == {}
    assert not settings.equal(False, 0)
    assert settings.validation_errors(float("nan"), {"type": "number"})


def test_crlf_is_preserved_and_corrupted_external_file_is_rejected(tmp_path):
    path = tmp_path / "opencode.jsonc"
    original = b'{\r\n// comment\r\n"username":"before"\r\n}\r\n'
    path.write_bytes(original)
    settings.save(path, {"username": "before"}, {("username",): "after"})
    assert path.read_bytes() == original.replace(b'"before"', b'"after"')
    path.write_text('[]')
    with pytest.raises(ConfigError):
        settings.save(path, {}, {("username",): "new"})
    assert path.read_text() == '[]'


def test_multiline_prompt_round_trip(app):
    value = "First line\nВторая строка\n"
    control = ValueControl({"type": "string"}, value, ("agents", "test", "system"))
    assert control.value() == value
    control.text.setPlainText(value + "Third line")
    i18n.set_language("ru")
    control.retranslate()
    assert control.value() == value + "Third line"
    control.deleteLater()


def test_required_fields_and_nested_enum_controls(app):
    info = settings.schema()["$defs"]["Mcp.LocalConfigEncoded"]
    dialog = ValueDialog(info, MISSING, ("mcp", "servers", "test"))
    assert dialog.rows["type"].value() == "local"
    assert dialog.rows["command"].value() == []
    dialog.rows["command"].set_value(["node", "server.js"])
    dialog.finish()
    assert dialog.result_value == {"type": "local", "command": ["node", "server.js"]}
    union = settings.resolve(settings.schema()["properties"]["mcp"])["properties"]["servers"]["additionalProperties"]
    control = ValueControl(union, MISSING, ("mcp",), optional=False)
    assert [control.mode.itemText(i) for i in range(control.mode.count())] == ["local", "remote"]
    dialog.deleteLater()
    control.deleteLater()


def test_drafts_survive_language_refresh_and_external_writes(app, tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text('{}')
    panel = SettingsPanel(path)
    assert not panel.dirty
    control = panel.rows[("experimental", "todo")].control
    choose(control, "literal", False)
    depth = panel.rows[("experimental", "subagent_depth")].control
    depth.mode.setCurrentIndex(1)
    type_text(depth, "invalid number")
    assert panel.errors and not panel.save_button.isEnabled()
    i18n.set_language("ru")
    panel.retranslate()
    assert depth.text.text() == "invalid number"
    assert control.value() is False
    type_text(depth, "0")
    path.write_text('{"username":"external"}')
    panel.reload()
    assert panel.dirty and panel.status_key == "external"
    panel.save()
    assert json.loads(path.read_text()) == {"username": "external", "experimental": {"todo": False, "subagent_depth": 0}}
    assert not panel.dirty and panel.status_key == "saved"
    assert panel.notice_keys
    panel.deleteLater()


def test_session_notice_before_and_after_save(app, tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text('{}')
    panel = SettingsPanel(path)
    control = panel.rows[("model",)].control
    control.mode.setCurrentIndex(1)
    type_text(control, "anthropic/claude-x")
    assert "session" in panel.notice_keys
    panel.save()
    assert panel.status_key == "saved" and "session" in panel.notice_keys
    assert json.loads(path.read_text()) == {"model": "anthropic/claude-x"}
    panel.deleteLater()


def test_mcp_toggle_uses_v2_disabled_and_keeps_separate_settings_draft(app, tmp_path):
    path = tmp_path / "opencode.jsonc"
    path.write_text('{"mcp":{"servers":{"local":{"type":"local","command":["server"]}}}}')
    panel = SettingsPanel(path, mcp=True)
    general = SettingsPanel(path)
    assert not any(spec.path[0] == "mcp" for spec in general.specs)
    control = general.rows[("update",)].control
    choose(control, "literal", "notify")
    entry = panel.mcp_servers.listing.item(0)
    before = entry.text()
    entry.setCheckState(Qt.CheckState.Unchecked)
    assert entry.text() == before
    panel.save()
    result = json.loads(path.read_text())
    assert result["mcp"]["servers"]["local"] == {"type": "local", "command": ["server"], "disabled": True}
    general.reload()
    assert general.dirty
    general.save()
    assert json.loads(path.read_text()) == {**result, "update": "notify"}
    panel.deleteLater()
    general.deleteLater()


def test_save_error_keeps_draft(app, tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    path.write_text('{}')
    panel = SettingsPanel(path)
    choose(panel.rows[("update",)].control, "literal", "notify")
    def fail(*a): raise OSError("read-only")
    monkeypatch.setattr(settings, "save", fail)
    panel.save()
    assert panel.dirty and panel.status_key == "failed" and path.read_text() == '{}'
    panel.deleteLater()


def test_resetting_the_config_keeps_a_backup_and_reload(app, tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    path.write_text('{"model":"stale/one","username":"owner"}')
    panel = SettingsPanel(path)
    emitted = []
    panel.saved.connect(lambda: emitted.append(True))
    choose(panel.rows[("share",)].control, "literal", "disabled")
    assert panel.reset_button.text() == "Reset config"
    answers = []

    def ask(parent, title, text, buttons, default):
        answers.append((title, text, default))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(ask))
    panel.reset()
    assert json.loads(path.read_text()) == {}
    assert not panel.dirty and panel.status_key == "saved" and not panel.notice_keys
    assert emitted == [True]
    assert answers[0][1].startswith("Replace opencode.json")
    backups = sorted(tmp_path.glob("opencode.json.bak-model-sync-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == '{"model":"stale/one","username":"owner"}'
    # The new empty file is what the panel shows now, not the one it started from.
    assert panel.base == {}
    panel.deleteLater()


def test_declining_a_reset_and_a_failing_one_keep_the_file(app, tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    path.write_text('{"model":"keep/me"}')
    panel = SettingsPanel(path)
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: QMessageBox.StandardButton.No))
    panel.reset()
    assert path.read_text() == '{"model":"keep/me"}'
    assert not list(tmp_path.glob("*.bak-model-sync-*"))
    mcp = SettingsPanel(path, mcp=True)
    assert mcp.reset_button is None, "one page owns the way out"
    mcp.deleteLater()

    choose(panel.rows[("share",)].control, "literal", "disabled")
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a: QMessageBox.StandardButton.Yes))

    def fail(*a): raise OSError("read-only")

    monkeypatch.setattr(settings, "reset", fail)
    panel.reset()
    assert panel.status_key == "failed" and panel.dirty
    assert path.read_text() == '{"model":"keep/me"}'
    panel.deleteLater()


def test_tabs_keep_settings_drafts(app, tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    path.write_text('{}')
    monkeypatch.setattr(window, "config_path", lambda: path)
    monkeypatch.setattr(window.MainWindow, "refresh", window.MainWindow._reload_config)
    widget = window.MainWindow()
    panel = widget.settings_page
    choose(panel.rows[("share",)].control, "literal", "disabled")
    for index in (4, 3, 2, 0, 4): widget.tabs.setCurrentIndex(index)
    widget.switch_language()
    assert widget.stack.count() == 5
    assert widget.stack.widget(2) is widget.agents_page
    assert panel is widget.settings_page and panel.dirty
    assert panel.rows[("share",)].control.value() == "disabled"
    assert not hasattr(widget, "agents_box")
    widget.deleteLater()
