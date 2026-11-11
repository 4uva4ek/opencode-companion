"""The standard parameter sets: what a person clicks instead of typing eight numbers.

Half of this is the data — five sets, every field answered, no number a field would refuse. The
other half is the click: a template is only worth having if filling the fields from it writes the
entry it promises and takes back the words it promises to take back.
"""
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox

from opencode_model_sync import i18n, presets, window


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


def write_models(widget, path, models: dict) -> None:
    data = json.loads(path.read_text())
    data["providers"]["local"]["models"] = models
    path.write_text(json.dumps(data))
    widget._reload_config()


def saved_models(path) -> dict:
    return json.loads(path.read_text())["providers"]["local"].get("models", {})


def open_model_window(widget, monkeypatch, model_id: str = "m", edit=None, accept: bool = True):
    """The way the user goes: the gear, the window, then the button that applies it."""
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


def choose(dialog, preset_id: str) -> None:
    """The two clicks a person makes: the name out of the list, then the button beside it."""
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(preset_id))
    dialog.preset_button.click()


# ---- the sets themselves ----

def test_there_are_five_standard_templates_and_no_two_bear_one_name():
    assert len(presets.PRESETS) == 5
    assert len({one.id for one in presets.PRESETS}) == len(presets.PRESETS)


def test_every_template_answers_every_field_the_window_offers():
    """A template is the whole answer: a field it does not name would keep a stranger's number."""
    offered = {key for key, _ in window.MODEL_PARAMS}
    for preset in presets.PRESETS:
        assert set(preset.values) == offered, preset.id


def test_no_template_offers_a_number_its_own_field_would_refuse():
    """Filling a template can never be the reason the window refuses to apply itself."""
    for preset in presets.PRESETS:
        for key, info in window.MODEL_PARAMS:
            value = preset.values[key]
            if value is None:
                continue
            if info.get("type") in ("number", "integer"):
                assert info["minimum"] <= value <= info["maximum"], (preset.id, key, value)
                if "multipleOf" in info:
                    # A number a slider cannot stand on is a number the field can only be typed to.
                    steps = value / info["multipleOf"]
                    assert abs(steps - round(steps)) < 1e-9, (preset.id, key, value)
            elif "enum" in info:
                assert value in info["enum"], (preset.id, key, value)
            else:
                raise AssertionError(f"{preset.id}.{key} answers a field the window does not draw")


def test_only_the_short_answers_set_names_an_output_limit():
    """A cap is the one number of the five that can cut real work short, so only one of them dares."""
    capped = [one.id for one in presets.PRESETS if one.values["maxOutputTokens"] is not None]
    assert capped == ["brief"]


def test_no_template_asks_a_model_to_reason():
    """A level named of a model that cannot reason is a request a server may refuse outright."""
    assert all(one.values["reasoningEffort"] is None for one in presets.PRESETS)


def test_the_five_answers_are_five_different_answers():
    seen = [json.dumps(one.values, sort_keys=True) for one in presets.PRESETS]
    assert len(set(seen)) == len(seen)


@pytest.mark.parametrize("language", ["en", "ru"])
def test_both_languages_name_and_explain_every_template(language):
    previous = i18n.language()
    i18n.set_language(language)
    try:
        names = []
        for preset in presets.PRESETS:
            assert i18n.tr(f"preset.{preset.id}.name") == preset.name
            assert i18n.tr(f"preset.{preset.id}.hint") == preset.description
            assert len(preset.description) > 60, f"{preset.id} is explained in more than a word"
            names.append(preset.name)
        assert len(set(names)) == len(names), "two templates that read alike are one template"
    finally:
        i18n.set_language(previous)


def test_the_templates_are_named_in_the_language_they_are_read_in():
    """A Russian speaker reads a Russian name, not the English one left standing there."""
    previous = i18n.language()
    try:
        i18n.set_language("en")
        english = [one.name for one in presets.PRESETS]
        i18n.set_language("ru")
        russian = [one.name for one in presets.PRESETS]
    finally:
        i18n.set_language(previous)
    assert english != russian and len(english) == len(russian)


def test_preset_finds_a_set_by_its_name_and_says_nothing_for_nothing():
    assert presets.preset("code") is presets.PRESETS[1]
    assert presets.preset(None) is None
    assert presets.preset("nonesuch") is None


# ---- the click ----

def test_the_window_offers_the_templates_above_the_numbers_it_fills(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    assert [dialog.preset_box.itemData(index) for index in range(dialog.preset_box.count())] == [
        None, *[one.id for one in presets.PRESETS]]
    assert dialog.preset_box.itemText(0) == i18n.tr("model.presetsNone")
    held = Qt.ItemDataRole.ToolTipRole
    assert [dialog.preset_box.itemData(index, held) for index in range(1, dialog.preset_box.count())] \
        == [window.preset_tip(one) for one in presets.PRESETS], "every name carries its own answer"
    assert not dialog.preset_note.text()
    dialog.deleteLater()


def test_the_templates_stand_between_the_words_about_the_numbers_and_the_numbers(view):
    """A choice made to fill eight rows belongs beside those rows, not at the top of the tab."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"temperature": 0.7}})
    dialog.show()
    dialog.tabs.setCurrentIndex(1)
    page = dialog.config_page.widget()
    app = QApplication.instance()
    for _ in range(10):
        app.processEvents()
    try:
        heading = next(one for one in page.findChildren(QLabel) if one.text() == i18n.tr("model.params"))

        def top(box):
            return box.mapTo(dialog, box.rect().topLeft()).y()

        assert top(heading) < top(dialog.preset_box), "the words about the numbers come first"
        assert top(dialog.preset_box) < top(dialog.preset_note), "what the name says reads under it"
        assert top(dialog.preset_note) < top(dialog.params["temperature"]), "then the numbers it fills"
        assert top(dialog.params["temperature"]) - top(dialog.preset_box) < 200, \
            "close enough that no scrolling stands between the choice and its rows"
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("preset_id", [one.id for one in presets.PRESETS])
def test_a_hover_over_a_name_lists_every_number_it_holds(view, preset_id):
    """Comparing two names should be a hover, not a round of choosing, reading and remembering."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    tip = dialog.preset_box.itemData(dialog.preset_box.findData(preset_id), Qt.ItemDataRole.ToolTipRole)
    answer = presets.preset(preset_id).values
    for key, info in window.MODEL_PARAMS:
        row = f"<tr><td>{window.field_name(('settings', key), info)}</td>" \
              f"<td>{window.tip_value(answer[key])}</td></tr>"
        assert row in tip, (preset_id, key)
    assert tip.count("<tr>") == len(window.MODEL_PARAMS), "one line per row, no more and no less"
    assert presets.preset(preset_id).name in tip
    assert presets.preset(preset_id).description in tip
    assert i18n.tr("model.presetsTipEmpty") in tip, "a dash has to be explained where it is used"
    dialog.deleteLater()


def test_a_hover_reads_in_the_language_the_window_is_in(view):
    """The words in the list are the words in the rows, or the two do not read as one answer."""
    previous = i18n.language()
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    try:
        i18n.set_language("ru")
        russian = window.preset_tip(presets.preset("exact"))
        russian_word = window.field_name(("settings", "topP"), {})
        i18n.set_language("en")
        english = window.preset_tip(presets.preset("exact"))
        english_word = window.field_name(("settings", "topP"), {})
    finally:
        i18n.set_language(previous)
        dialog.deleteLater()
    assert russian_word in russian and english_word in english
    assert russian_word != english_word, "the same row has two names, and the tip uses the standing one"
    assert russian_word not in english and english_word not in russian
    assert i18n.tr("model.presetsTipEmpty") in window.preset_tip(presets.preset("exact"))
    assert english.count("<tr>") == russian.count("<tr>"), "the same answer, said twice"


def test_the_closed_list_says_what_the_standing_name_would_write(view):
    """The question is asked of a box standing shut, so the box has to answer it."""
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    assert dialog.preset_box.toolTip() == i18n.tr("model.presetsHint")
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData("brief"))
    assert dialog.preset_box.toolTip() == window.preset_tip(presets.preset("brief"))
    assert "2048" in dialog.preset_box.toolTip(), "the one number that can cut an answer short"
    dialog.preset_box.setCurrentIndex(0)
    assert dialog.preset_box.toolTip() == i18n.tr("model.presetsHint"), "nothing chosen, nothing listed"
    dialog.deleteLater()


def test_a_word_the_app_does_not_know_is_still_named_in_the_list(view):
    """A hand-written word is a word the template carries: hiding it would be lying by omission."""
    widget, _ = view
    window.presets_file().write_text(json.dumps({"presets": [
        {"id": "u-hand", "name": "Hand", "description": "",
         "values": {"temperature": 0.2, "mirostat": 2, "nested": {"no": "way"}}}]}), encoding="utf-8")
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    tip = dialog.preset_box.itemData(dialog.preset_box.findData("u-hand"), Qt.ItemDataRole.ToolTipRole)
    assert "<tr><td>mirostat</td><td>2</td></tr>" in tip
    assert "nested" not in tip, "a map is not a number, and it is not in the file either"
    assert tip.count("<tr>") == len(window.MODEL_PARAMS) + 1
    dialog.deleteLater()


def test_a_template_fills_every_field_it_answers_and_ticks_back_the_rest(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    choose(dialog, "brief")
    answer = presets.preset("brief").values
    for key, control in dialog.params.items():
        if answer[key] is None:
            assert control.value() is window.MISSING, f"{key} was left empty and still has a number"
        else:
            assert control.value() == answer[key], (key, control.value(), answer[key])
    assert dialog.preset_note.text() == i18n.tr("model.presetsApplied",
                                               name=presets.preset("brief").name)
    dialog.deleteLater()


def test_filling_a_template_writes_the_entry_it_promised(view, monkeypatch):
    """The whole point, reached the way the user reaches it: the gear, the click, the apply."""
    widget, path = view
    write_models(widget, path, {"m": {"name": "Qwen", "settings": {"mirostat": 2}}})
    open_model_window(widget, monkeypatch, "m", lambda dialog: choose(dialog, "code"))
    assert saved_models(path)["m"] == {
        "name": "Qwen",
        # The provider's own word survives: a template answers the fields it knows, not the file.
        "settings": {"mirostat": 2, "temperature": 0.3, "topP": 0.9, "topK": 40, "minP": 0,
                     "presencePenalty": 0, "frequencyPenalty": 0}}


def test_a_number_one_template_wrote_and_the_next_leaves_empty_goes_back(view, monkeypatch):
    """Templates are whole answers: one that says nothing about a field takes that word out again."""
    widget, path = view
    write_models(widget, path, {"m": {"settings": {"seed": 17, "maxOutputTokens": 4096}}})
    open_model_window(widget, monkeypatch, "m", lambda dialog: choose(dialog, "everyday"))
    assert saved_models(path)["m"] == {
        "settings": {"temperature": 0.6, "topP": 0.95, "topK": 40, "minP": 0,
                     "presencePenalty": 0, "frequencyPenalty": 0}}, "the seed is nobody's now"


def test_reading_a_template_without_filling_it_writes_nothing(view, monkeypatch):
    """Highlighting a name is reading it, and reading cannot be allowed to rewrite a model."""
    widget, path = view
    write_models(widget, path, {"m": {"settings": {"temperature": 0.7}}})
    dialog = open_model_window(
        widget, monkeypatch, "m",
        lambda dialog: dialog.preset_box.setCurrentIndex(dialog.preset_box.findData("creative")),
        accept=False)
    try:
        assert dialog.params["temperature"].value() == 0.7, "the fields stand where they stood"
        # The note reads as the template rather than as a filled-in one: what is offered is not yet
        # what was taken.
        assert dialog.preset_note.text().startswith(presets.preset("creative").description)
        assert "Filled from" not in dialog.preset_note.text()
        dialog.finish()
        assert not dialog.error.text()
        assert dialog.result_value == {"settings": {"temperature": 0.7}}
    finally:
        dialog.deleteLater()


def test_a_template_and_a_hand_written_number_are_two_touches_that_survive_each_other(view, monkeypatch):
    """The template fills the fields, and then the person decides one of them differently."""
    widget, path = view
    write_models(widget, path, {"m": {}})

    def edit(dialog):
        choose(dialog, "creative")
        dialog.params["temperature"].text.setText("0.9")

    open_model_window(widget, monkeypatch, "m", edit)
    settings = saved_models(path)["m"]["settings"]
    assert settings["temperature"] == 0.9, "the hand-written number wins"
    assert settings["frequencyPenalty"] == 0.3, "and the rest of the template stands"


def test_the_defaults_button_admits_that_no_template_is_filled_in(view):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"seed": 4}})
    choose(dialog, "exact")
    dialog.defaults.click()
    assert dialog.preset_box.currentIndex() == 0, "nothing stands filled in any more"
    assert not dialog.preset_note.text()
    assert all(control.value() is window.MISSING for control in dialog.params.values())
    dialog.deleteLater()


@pytest.mark.parametrize("preset_id", [one.id for one in presets.PRESETS])
@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_template_applies_in_whichever_language_the_window_is_open(view, monkeypatch,
                                                                        preset_id, language):
    """Nothing a template does may depend on a translated word: the numbers are the whole answer."""
    widget, path = view
    previous = i18n.language()
    i18n.set_language(language)
    try:
        write_models(widget, path, {"m": {}})
        open_model_window(widget, monkeypatch, "m", lambda dialog: choose(dialog, preset_id))
        settings = saved_models(path)["m"]["settings"]
        answer = presets.preset(preset_id).values
        assert settings["temperature"] == answer["temperature"]
        assert ("maxOutputTokens" in settings) == (answer["maxOutputTokens"] is not None)
        assert "reasoningEffort" not in settings and "seed" not in settings
    finally:
        i18n.set_language(previous)


# ---- a person's own templates ----

OWN = {"temperature": 0.45, "topP": 0.93, "topK": 33, "minP": 0.02, "presencePenalty": 0.1,
       "frequencyPenalty": 0, "maxOutputTokens": 3000, "seed": None, "stopSequences": None,
       "reasoningEffort": None}


def stored(file) -> list:
    """What the file of templates holds, read as JSON rather than through the app's own reader."""
    return json.loads(file.read_text(encoding="utf-8"))["presets"]


def answer_saving(monkeypatch, name: str, description: str = ""):
    """The saving window is a dialog, so a test answers it the way a person types into it."""

    def answer(box):
        if isinstance(box, window.SavePresetDialog):
            box.name.setText(name)
            box.description.setPlainText(description)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(window.QDialog, "exec", answer)


# ---- the file of templates ----


def test_a_saved_template_comes_back_exactly_as_it_was_saved(tmp_path):
    """What you saved is what comes back, the fields it says nothing about included."""
    file = tmp_path / presets.STATE_NAME
    saved, replaced = presets.save("Мягко и коротко", "My own softness.", OWN, file)
    assert replaced is False and saved.custom
    assert saved.name == "Мягко и коротко", "your own words are not translated on the way back"
    assert saved.description == "My own softness."
    assert presets.load(file) == [saved]


def test_saving_under_a_name_you_already_used_rewrites_it_instead_of_adding_a_second(tmp_path):
    file = tmp_path / presets.STATE_NAME
    presets.save("Mine", "the first", OWN, file)
    saved, replaced = presets.save("Mine", "the second", dict(OWN, temperature=0.9), file)
    assert replaced is True
    assert [one.name for one in presets.load(file)] == ["Mine"]
    assert saved.values["temperature"] == 0.9
    assert presets.load(file)[0].description == "the second"


def test_a_name_you_used_is_not_the_case_or_the_spaces_you_happened_to_type(tmp_path):
    file = tmp_path / presets.STATE_NAME
    presets.save("My Soft", "", OWN, file)
    _, replaced = presets.save("  my soft  ", "", OWN, file)
    assert replaced is True, "one name is one template, and one template is one thing to delete"


def test_a_rewritten_template_keeps_the_place_it_had_in_the_list(tmp_path):
    """A name that jumps to the bottom of the row on every save is a name the eyes lose."""
    file = tmp_path / presets.STATE_NAME
    first, _ = presets.save("First", "", OWN, file)
    presets.save("Second", "", OWN, file)
    presets.save("First", "again", dict(OWN, temperature=0.8), file)
    assert [one.name for one in presets.load(file)] == ["First", "Second"]
    assert presets.load(file)[0].id == first.id and presets.load(file)[0].description == "again"


def test_saving_under_the_name_of_a_built_in_template_leaves_that_one_where_it_is(tmp_path):
    """A name is yours to reuse; the five that came with the app are not yours to lose."""
    file = tmp_path / presets.STATE_NAME
    code = presets.preset("code")
    saved, _ = presets.save(code.name, "mine", OWN, file)
    assert saved.custom and saved.name == code.name and saved.id != code.id
    assert presets.preset("code") is code, "the shipped answer still answers the same numbers"
    own = presets.load(file)
    assert presets.one(code.id, own).custom is False
    assert presets.one(saved.id, own).custom is True


@pytest.mark.parametrize("preset_id", [one.id for one in presets.PRESETS])
def test_a_template_that_came_with_the_app_cannot_be_deleted_however_it_is_asked(tmp_path, preset_id):
    """The refusal lives in the store, not in whether a button happens to be enabled."""
    file = tmp_path / presets.STATE_NAME
    # Copied into the own file by hand: the id of a shipped answer stays a shipped answer, and the
    # real one is what the list resolves to.
    presets.write([presets.Preset(one.id, one.values, one.name, one.description, True)
                   for one in presets.PRESETS], file)
    with pytest.raises(presets.PresetError):
        presets.remove(preset_id, file)
    assert len(presets.load(file)) == len(presets.PRESETS), "nothing was taken out of the file"
    assert presets.one(preset_id, presets.load(file)).custom is False


def test_an_absent_file_is_not_a_reason_to_claim_a_built_in_template_was_deleted(tmp_path):
    with pytest.raises(presets.PresetError):
        presets.remove("code", tmp_path / presets.STATE_NAME)
    assert not (tmp_path / presets.STATE_NAME).exists(), "refusing does not even write a file"


def test_deleting_yours_leaves_the_others_in_the_order_they_were_saved(tmp_path):
    file = tmp_path / presets.STATE_NAME
    first, _ = presets.save("One", "", OWN, file)
    second, _ = presets.save("Two", "", dict(OWN, temperature=1.0), file)
    assert [one.id for one in presets.load(file)] == [first.id, second.id]
    assert presets.remove(first.id, file).name == "One"
    assert [one.name for one in presets.load(file)] == ["Two"]
    with pytest.raises(presets.PresetError):
        presets.remove(first.id, file)


def test_deleting_a_name_that_is_not_there_says_so_rather_than_pretending(tmp_path):
    file = tmp_path / presets.STATE_NAME
    mine, _ = presets.save("Once", "", OWN, file)
    presets.remove(mine.id, file)
    with pytest.raises(presets.PresetError):
        presets.remove(mine.id, file)
    assert presets.load(file) == []


def test_a_file_that_cannot_be_read_is_no_templates_rather_than_an_empty_list_of_lies(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json at all", encoding="utf-8")
    assert presets.load(broken) == []
    assert presets.load(tmp_path / "absent.json") == []
    assert presets.load(tmp_path) == [], "a folder is not a file either"


def test_a_file_poked_at_by_hand_offers_what_it_can_and_drops_what_it_cannot(tmp_path):
    """A map is not a number, a flag is not a number, and a field has no way to say either back."""
    file = tmp_path / presets.STATE_NAME
    file.write_text(json.dumps({"presets": [
        {"name": "Hand", "description": "typed in a text editor",
         "values": {"temperature": 0.2, "stopSequences": ["\n\n"], "nested": {"a": 1}, "flag": True}},
        {"values": {"temperature": 0.5}},
        "not even a template",
    ]}), encoding="utf-8")
    only, = presets.load(file)
    assert only.values == {"temperature": 0.2, "stopSequences": ["\n\n"]}
    assert only.custom and only.name == "Hand" and only.id.startswith("u-")
    assert only.description == "typed in a text editor"


def test_a_template_needs_nothing_more_than_a_name_to_be_worth_saving(tmp_path):
    file = tmp_path / presets.STATE_NAME
    saved, _ = presets.save("Bare", "", {}, file)
    assert presets.load(file) == [saved] and saved.values == {}
    assert saved.description == "", "no description is an answer, not a word to go looking up"


def test_the_name_of_a_template_stands_though_its_spaces_and_case_do_not(tmp_path):
    assert presets._ident("  Мягко ") == presets._ident("мягко")
    assert presets._ident("Мягко") != presets._ident("Резко")
    assert presets._ident("Мягко").startswith("u-"), "a Russian name hashes; slugging it gives nothing"


def test_the_templates_live_in_one_file_beside_the_config_and_the_environment_can_move_it(tmp_path):
    home = tmp_path / "xdg"
    assert presets.state_path({"XDG_CONFIG_HOME": str(home)}) == home / "opencode" / presets.STATE_NAME
    moved = tmp_path / "mine.json"
    assert presets.state_path({"OPENCODE_MODEL_SYNC_PRESETS": str(moved)}) == moved


def test_the_window_reads_and_writes_the_file_beside_the_config_it_is_editing(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    monkeypatch.setattr(window, "config_path", lambda: path)
    assert window.presets_file() == tmp_path / presets.STATE_NAME


def test_the_environment_names_the_file_and_the_window_does_not_quarrel_with_it(tmp_path, monkeypatch):
    """One question, one answer: a moved file is moved for the window too, not only for the store."""
    moved = tmp_path / "elsewhere" / "my-templates.json"
    mine, _ = presets.save("Mine", "", OWN, presets.state_path({"OPENCODE_MODEL_SYNC_PRESETS": str(moved)}))
    monkeypatch.setattr(window, "config_path", lambda: tmp_path / "opencode.json")
    monkeypatch.setenv("OPENCODE_MODEL_SYNC_PRESETS", str(moved))
    assert window.presets_file() == moved
    dialog = window.ModelSettingsDialog(None, "local", "m", {})
    try:
        assert dialog.preset_box.findData(mine.id) > 0, "the window reads the file the environment named"
    finally:
        dialog.deleteLater()


# ---- the two buttons in the window ----


def test_your_own_templates_are_offered_after_the_five_and_told_apart_from_them(view):
    widget, _ = view
    mine, _ = presets.save("Моё", "My own numbers.", OWN, window.presets_file())
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    held = Qt.ItemDataRole.ToolTipRole
    offered = [dialog.preset_box.itemData(index) for index in range(dialog.preset_box.count())]
    assert offered == [None, *[one.id for one in presets.PRESETS], mine.id]
    last = dialog.preset_box.count() - 1
    assert dialog.preset_box.itemText(last) == "Моё"
    assert "My own numbers." in dialog.preset_box.itemData(last, held)
    assert f"<tr><td>{window.field_name(('settings', 'seed'), {})}</td><td>{window.TIP_EMPTY}</td></tr>" \
        in dialog.preset_box.itemData(last, held), "your own list says what it keeps back"
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(mine.id))
    assert dialog.preset_remove.isEnabled(), "yours is yours to throw away"
    assert i18n.tr("model.presetsOwn") in dialog.preset_note.text()
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData("code"))
    assert not dialog.preset_remove.isEnabled(), "the five that came with Companion stay put"
    assert i18n.tr("model.presetsBuiltIn") in dialog.preset_note.text()
    dialog.preset_box.setCurrentIndex(0)
    assert not dialog.preset_remove.isEnabled() and not dialog.preset_note.text()
    dialog.deleteLater()


def test_a_template_with_no_description_says_that_instead_of_nothing(view):
    widget, _ = view
    mine, _ = presets.save("Silent", "", OWN, window.presets_file())
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(mine.id))
    assert dialog.preset_note.text() == (i18n.tr("model.presetsNoDescription") + "\n\n"
                                         + i18n.tr("model.presetsOwn"))
    dialog.deleteLater()


def opening_saving_box(widget, own: list[str]) -> window.SavePresetDialog:
    return window.SavePresetDialog(widget, 10, window.presets_file(), own=own,
                                   shipped=[one.name for one in presets.PRESETS])


def test_a_saving_window_says_what_a_name_will_do_before_the_button_is_pressed(view):
    widget, _ = view
    box = opening_saving_box(widget, own=["Mine"])
    box._typed("Mine")
    assert box.warned.text() == i18n.tr("model.presetsNameTaken")
    box._typed(presets.preset("code").name)
    assert box.warned.text() == i18n.tr("model.presetsNameShadows")
    box._typed("Something nobody used")
    assert not box.warned.text(), "an unused name needs no warning to read past"
    box.deleteLater()


def test_a_template_without_a_name_is_not_saved(view):
    widget, _ = view
    box = opening_saving_box(widget, own=[])
    box._accept()
    assert box.error.text() == i18n.tr("model.presetsNameNeeded")
    assert box.result() != QDialog.DialogCode.Accepted, "the window is still open, still unsaved"
    box.name.setText("At last")
    box._accept()
    assert not box.error.text() and box.result() == QDialog.DialogCode.Accepted
    box.deleteLater()


def test_saving_from_the_window_keeps_the_numbers_as_the_person_left_them(view, monkeypatch):
    """Filled from a template, then corrected by hand — the correction is the reason to save it."""
    widget, path = view
    file = window.presets_file()
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    choose(dialog, "creative")
    dialog.params["temperature"].text.setText("0.9")
    dialog.params["seed"].use_default.setChecked(False)
    dialog.params["seed"].text.setText("7")
    answer_saving(monkeypatch, "My softness", "Warm, and repeatable.")
    dialog.save_preset()
    assert dialog.preset_note.text() == i18n.tr("model.presetsSaved", name="My softness")
    kept, = stored(file)
    assert kept["name"] == "My softness" and kept["description"] == "Warm, and repeatable."
    assert kept["values"]["temperature"] == 0.9 and kept["values"]["seed"] == 7
    assert kept["values"]["frequencyPenalty"] == 0.3, "the rest of the template stands as filled"
    assert kept["values"]["stopSequences"] is None, "a ticked row saves as nothing to write"
    assert json.loads(path.read_text())["providers"]["local"]["models"] == {}
    dialog.deleteLater()


def test_saving_leaves_the_opencode_config_exactly_as_it_stood(view, monkeypatch):
    """A template is a way to fill fields; saving one is not a way to edit somebody's models."""
    widget, path = view
    write_models(widget, path, {"m": {"settings": {"temperature": 0.7}}})
    before = path.read_text()
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    answer_saving(monkeypatch, "Anything", "")
    dialog.save_preset()
    assert path.read_text() == before
    dialog.deleteLater()


def test_saving_selects_the_name_it_just_wrote_and_says_whether_it_replaced_one(view, monkeypatch):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    answer_saving(monkeypatch, "Mine", "the first")
    dialog.save_preset()
    assert dialog.preset_box.currentData() == presets._ident("Mine")
    assert [one.name for one in dialog.own] == ["Mine"]
    assert dialog.preset_remove.isEnabled(), "the name just saved is a name you can delete"
    dialog.params["temperature"].text.setText("1.4")
    answer_saving(monkeypatch, "Mine", "the second")
    dialog.save_preset()
    assert dialog.preset_note.text() == i18n.tr("model.presetsReplaced", name="Mine")
    assert [one.name for one in dialog.own] == ["Mine"], "one template, now another number"
    later = window.ModelSettingsDialog(widget, "local", "m", {})
    assert [one.name for one in later.own] == ["Mine"]
    assert later.preset_box.itemText(later.preset_box.findData(presets._ident("Mine"))) == "Mine"
    dialog.deleteLater()
    later.deleteLater()


def test_a_number_on_its_way_is_not_a_template_and_says_which_field(view, monkeypatch):
    widget, path = view
    write_models(widget, path, {"m": {"settings": {"temperature": 0.7}}})
    before = path.read_text()
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    choose(dialog, "everyday")
    dialog.params["temperature"].text.setText("-")
    answer_saving(monkeypatch, "Half typed", "")
    dialog.save_preset()
    assert dialog.preset_note.text() == i18n.tr("model.presetsBadValues", field="temperature")
    assert not window.presets_file().exists(), "nothing was saved under a half a number"
    assert path.read_text() == before
    dialog.deleteLater()


def test_a_number_outside_its_own_range_is_not_a_template_either(view, monkeypatch):
    widget, _ = view
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    dialog.params["topP"].use_default.setChecked(False)
    dialog.params["topP"].text.setText("1.5")
    answer_saving(monkeypatch, "Impossible", "")
    dialog.save_preset()
    assert "topP" in dialog.preset_note.text()
    assert not window.presets_file().exists()
    dialog.deleteLater()


def test_a_saved_template_fills_the_fields_and_writes_the_numbers_it_promises(view, monkeypatch):
    """The whole point of your own: the gear, the name, the apply."""
    widget, path = view
    mine, _ = presets.save("My soft", "", OWN, window.presets_file())
    write_models(widget, path, {"m": {"name": "Qwen", "settings": {"mirostat": 2}}})
    open_model_window(widget, monkeypatch, "m", lambda dialog: choose(dialog, mine.id))
    assert saved_models(path)["m"] == {
        "name": "Qwen",
        "settings": {"mirostat": 2, "temperature": 0.45, "topP": 0.93, "topK": 33, "minP": 0.02,
                     "presencePenalty": 0.1, "frequencyPenalty": 0, "maxOutputTokens": 3000}}


def test_a_template_that_predates_a_field_leaves_that_field_to_the_provider(view):
    """A template saved before some future field existed says nothing about it, which is an answer."""
    widget, _ = view
    old = presets.Preset("u-old", {"temperature": 0.2, "topP": 0.9}, "Back when", "", True)
    presets.write([old], window.presets_file())
    dialog = window.ModelSettingsDialog(widget, "local", "m", {"settings": {"minP": 0.3, "seed": 5}})
    choose(dialog, "u-old")
    assert dialog.params["temperature"].value() == 0.2 and dialog.params["topP"].value() == 0.9
    assert dialog.params["minP"].value() is window.MISSING, "the word goes out of the entry again"
    assert dialog.params["seed"].value() is window.MISSING
    dialog.deleteLater()


def test_a_word_a_field_cannot_say_stops_the_window_rather_than_reaching_the_file(view, monkeypatch):
    """A hand-written "hot" where a number belongs is refused on apply, not written through."""
    widget, path = view
    window.presets_file().write_text(json.dumps({"presets": [
        {"id": "u-hand", "name": "Hand", "description": "", "values": {"temperature": "hot"}}]}),
        encoding="utf-8")
    write_models(widget, path, {"m": {"settings": {"temperature": 0.7}}})
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    choose(dialog, "u-hand")
    with pytest.raises(ValueError):
        dialog.params["temperature"].value()
    dialog.finish()
    assert "temperature" in dialog.error.text()
    assert saved_models(path)["m"]["settings"] == {"temperature": 0.7}, "the file waits"
    dialog.deleteLater()


def test_deleting_a_template_asks_and_then_takes_it_out_of_the_file_and_the_list(view, monkeypatch):
    widget, _ = view
    file = window.presets_file()
    mine, _ = presets.save("Doomed", "", OWN, file)
    other, _ = presets.save("Kept", "", OWN, file)
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(mine.id))
    asked = []

    def refuse(*_args, **_names):
        asked.append(True)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(window.QMessageBox, "question", refuse)
    dialog.delete_preset()
    assert asked, "a name that costs a template is asked for first"
    assert [one.id for one in presets.load(file)] == [mine.id, other.id], "No means the file stands"
    monkeypatch.setattr(window.QMessageBox, "question",
                        lambda *_a, **_n: QMessageBox.StandardButton.Yes)
    dialog.delete_preset()
    assert [one.id for one in presets.load(file)] == [other.id]
    assert dialog.preset_note.text() == i18n.tr("model.presetsRemoved", name="Doomed")
    assert dialog.preset_box.currentData() is None, "the list no longer stands on a deleted name"
    assert not dialog.preset_remove.isEnabled()
    dialog.deleteLater()


def test_deleting_a_template_leaves_every_model_exactly_where_it_was(view, monkeypatch):
    """A template is a way to fill fields, so losing one cannot change a written entry."""
    widget, path = view
    mine, _ = presets.save("Doomed", "", OWN, window.presets_file())
    write_models(widget, path, {"m": {"settings": {"temperature": 0.45, "mirostat": 2}}})
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(mine.id))
    monkeypatch.setattr(window.QMessageBox, "question",
                        lambda *_a, **_n: QMessageBox.StandardButton.Yes)
    dialog.delete_preset()
    assert saved_models(path)["m"]["settings"] == {"temperature": 0.45, "mirostat": 2}
    dialog.deleteLater()


def test_no_way_through_the_window_deletes_one_of_the_five(view, monkeypatch):
    """The dead button is not the only thing standing between a click and the shipped five."""
    widget, _ = view
    asked = []
    monkeypatch.setattr(window.QMessageBox, "question",
                        lambda *_a, **_n: asked.append(True) or QMessageBox.StandardButton.Yes)
    dialog = window.ModelSettingsDialog(widget, "local", "m", {})
    for preset in presets.PRESETS:
        dialog.preset_box.setCurrentIndex(dialog.preset_box.findData(preset.id))
        assert not dialog.preset_remove.isEnabled(), preset.id
        dialog.delete_preset()
    assert not asked, "a shipped template is not even asked about"
    assert dialog.preset_note.text() == i18n.tr("model.presetsBuiltIn")
    assert not window.presets_file().exists(), "a refused delete does not even write a file"
    dialog.deleteLater()


def test_two_windows_open_at_once_both_see_what_the_other_one_saved(view, monkeypatch):
    """The file is read again on every save, which is what keeps a second window from being stale."""
    widget, _ = view
    first = window.ModelSettingsDialog(widget, "local", "m", {})
    second = window.ModelSettingsDialog(widget, "local", "m", {})
    answer_saving(monkeypatch, "Late", "")
    first.save_preset()
    assert [one.name for one in second.own] == [], "the second window opened before it existed"
    second.save_preset()
    assert [one.name for one in presets.load(window.presets_file())] == ["Late"]
    assert [one.name for one in first.own] == ["Late"], "one name saved twice is one template"
    first.deleteLater()
    second.deleteLater()
