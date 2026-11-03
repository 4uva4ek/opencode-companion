import json
from pathlib import Path

import pytest

from opencode_model_sync.config import (
    ConfigError,
    OpencodeConfig,
    config_dir,
    config_path,
    configured_visible,
    strip_jsonc,
)


def write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


LEGACY_MAC = {
    "npm": "@ai-sdk/openai-compatible",
    "name": "Ollama MAC",
    "options": {"baseURL": "http://192.168.1.10:11434/v1", "apiKey": "ollama"},
    "models": {"qwen3.8:27b-mlx": {"name": "Qwen3.8-mlx"}},
}


def test_config_dir_prefers_opencode_variable(tmp_path):
    assert config_dir({"OPENCODE_CONFIG_DIR": str(tmp_path)}) == tmp_path
    assert config_dir({"XDG_CONFIG_HOME": str(tmp_path)}) == tmp_path / "opencode"


def test_config_path_lets_jsonc_win(tmp_path):
    assert config_path(tmp_path) == tmp_path / "opencode.json"
    (tmp_path / "opencode.json").write_text("{}")
    (tmp_path / "opencode.jsonc").write_text("{}")
    assert config_path(tmp_path) == tmp_path / "opencode.jsonc"


def test_models_go_to_the_current_map_whatever_map_the_provider_came_from(tmp_path):
    path = write(tmp_path / "opencode.json", {"provider": {"ollama-mac": LEGACY_MAC}})
    config = OpencodeConfig.load(path)
    entry = config.model_entry("ollama-mac", None, 65536, True)
    config.add_models("ollama-mac", {"qwen3.6:latest": entry})
    config.save()

    saved = json.loads(path.read_text())
    assert "provider" not in saved, "the map opencode does not read is left behind empty at best"
    mac = saved["providers"]["ollama-mac"]
    assert mac["package"] == "aisdk:@ai-sdk/openai-compatible", "the move carries the server along with it"
    assert mac["settings"]["baseURL"] == "http://192.168.1.10:11434/v1"
    assert mac["models"]["qwen3.6:latest"] == {"capabilities": {"tools": True}, "limit": {"context": 65536, "output": 32768}}
    assert mac["models"]["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx"}


def test_current_entry_wins_over_legacy_entry_with_same_id(tmp_path):
    path = write(
        tmp_path / "opencode.json",
        {
            "provider": {"local": LEGACY_MAC},
            "providers": {"local": {"settings": {"baseURL": "http://127.0.0.1:1234/v1"}, "models": {}}},
        },
    )
    config = OpencodeConfig.load(path)
    provider = config.provider("local")
    assert provider.section == "providers"
    assert provider.base_url == "http://127.0.0.1:1234/v1"
    assert config.model_entry("local", "M", None, False) == {"name": "M", "capabilities": {"tools": False}}


def test_existing_model_settings_are_kept(tmp_path):
    path = write(tmp_path / "opencode.json", {"provider": {"ollama-mac": LEGACY_MAC}})
    config = OpencodeConfig.load(path)
    config.add_models("ollama-mac", {"qwen3.8:27b-mlx": {"name": "overwritten?"}})
    assert config.provider("ollama-mac").models["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx"}


def test_remove_models(tmp_path):
    path = write(tmp_path / "opencode.json", {"provider": {"ollama-mac": LEGACY_MAC}})
    config = OpencodeConfig.load(path)
    config.remove_models("ollama-mac", ["qwen3.8:27b-mlx", "unknown"])
    assert config.provider("ollama-mac").models == {}


def test_save_backs_up_once_and_keeps_other_keys(tmp_path):
    path = write(tmp_path / "opencode.json", {"$schema": "x", "theme": "dark", "provider": {"m": LEGACY_MAC}})
    config = OpencodeConfig.load(path)
    config.remove_models("m", ["qwen3.8:27b-mlx"])
    config.save()
    config.save()
    backups = list(tmp_path.glob("opencode.json.bak-model-sync-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["provider"]["m"]["models"]
    assert json.loads(path.read_text())["theme"] == "dark"


def test_add_provider_starts_in_the_current_map(tmp_path):
    config = OpencodeConfig.load(tmp_path / "opencode.json")
    config.add_provider("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/", "secret")
    config.save()
    saved = json.loads((tmp_path / "opencode.json").read_text())
    assert saved["providers"]["lmstudio"] == {
        "package": "aisdk:@ai-sdk/openai-compatible",
        "name": "LM Studio",
        "settings": {"baseURL": "http://127.0.0.1:1234/v1", "apiKey": "secret"},
        "models": {},
    }, "a provider added here must not have to leave a map later"
    assert "provider" not in saved
    with pytest.raises(ConfigError):
        config.add_provider("lmstudio", "again", "http://x", None)
    with pytest.raises(ConfigError):
        config.add_provider("bad id", "x", "http://x", None)


def test_jsonc_is_read_but_not_overwritten(tmp_path):
    path = tmp_path / "opencode.jsonc"
    path.write_text('{\n  // keep me\n  "provider": {"m": {"options": {"baseURL": "http://a//b"},},},\n}\n')
    config = OpencodeConfig.load(path)
    assert config.has_comments
    assert config.provider("m").base_url == "http://a//b"
    with pytest.raises(ConfigError):
        config.save()


def test_strip_jsonc_keeps_slashes_inside_strings():
    assert json.loads(strip_jsonc('{"u": "http://x/*y*/", /* c */ "a": [1,],}')) == {"u": "http://x/*y*/", "a": [1]}


def test_env_placeholders_are_resolved(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")
    path = write(
        tmp_path / "opencode.json",
        {"provider": {"m": {"options": {"baseURL": "http://h/v1", "apiKey": "{env:MY_KEY}"}}}},
    )
    assert OpencodeConfig.load(path).provider("m").api_key == "secret"


def test_set_model_tools_writes_the_current_shape_whatever_map_the_provider_came_from(tmp_path):
    path = write(
        tmp_path / "opencode.json",
        {
            "provider": {"old": LEGACY_MAC},
            "providers": {"new": {"settings": {"baseURL": "http://h/v1"}, "models": {"m": {"name": "M"}}}},
        },
    )
    config = OpencodeConfig.load(path)
    config.set_model_tools("old", "qwen3.8:27b-mlx", False)
    config.set_model_tools("new", "m", False)
    # Both end up spelled the same way: the old provider moved, the new one stayed.
    assert config.provider("old").section == config.provider("new").section == "providers"
    assert config.provider("old").models["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx", "capabilities": {"tools": False}}
    assert config.provider("new").models["m"] == {"name": "M", "capabilities": {"tools": False}}
    with pytest.raises(ConfigError):
        config.set_model_tools("old", "unknown", True)


def test_configured_tools_reads_both_shapes():
    from opencode_model_sync.config import configured_tools

    assert configured_tools({"tool_call": False}) is False
    assert configured_tools({"capabilities": {"tools": True}}) is True
    assert configured_tools({"name": "x"}) is None


def test_switching_a_model_off_leaves_the_mark_opencode_reads(tmp_path):
    """Only ``disabled`` in the current map keeps a model out of the list opencode works from."""
    path = write(
        tmp_path / "opencode.json",
        {
            "providers": {
                "local": {
                    "package": "aisdk:@ai-sdk/openai-compatible",
                    "settings": {"baseURL": "http://h/v1"},
                    "models": {"on": {}, "off": {"disabled": True, "capabilities": {"tools": True}}},
                }
            }
        },
    )
    config = OpencodeConfig.load(path)
    models = config.provider("local").models
    assert configured_visible(models["on"], "providers")
    assert not configured_visible(models["off"], "providers")

    assert not config.set_model_visible("local", "on", False), "nothing moved: the provider is already home"
    assert not config.set_model_visible("local", "off", True)
    config.save()

    saved = json.loads(path.read_text())["providers"]["local"]["models"]
    assert saved["on"] == {"disabled": True}
    assert saved["off"] == {"capabilities": {"tools": True}}, "switching on clears the mark and leaves the rest alone"
    with pytest.raises(ConfigError):
        config.set_model_visible("local", "unknown", True)


def test_each_map_has_its_own_word_for_a_model_it_does_not_offer():
    """Measured on opencode 2.1.4, both against his own model server: the legacy map obeys
    ``status: deprecated`` and reads a ``disabled`` as nothing, the current map the other way round."""
    assert not configured_visible({"status": "deprecated"}, "provider")
    assert configured_visible({"disabled": True}, "provider"), "the mark would be read as nothing there"
    assert not configured_visible({"disabled": True}, "providers")
    assert configured_visible({"status": "deprecated"}, "providers"), "the old word means nothing here"


def test_switching_a_deprecated_model_on_clears_the_old_word_and_moves_the_provider(tmp_path):
    """``status`` is honoured where it is read, but it is not a word of the map we write, so the
    provider moves and comes back speaking ``disabled``."""
    path = write(
        tmp_path / "opencode.json",
        {"provider": {"local": {**LEGACY_MAC, "models": {"old": {"status": "deprecated", "name": "Old"}}}}},
    )
    config = OpencodeConfig.load(path)
    assert config.provider("local").models["old"], "read from the old map, it is still the same model"

    assert config.set_model_visible("local", "old", True), "this edit is what moved the provider"
    config.save()

    saved = json.loads(path.read_text())
    assert "provider" not in saved
    assert saved["providers"]["local"]["models"]["old"] == {"name": "Old"}, "away, and back, with nothing left over"


def test_moving_a_provider_carries_its_own_word_for_off_as_the_new_one(tmp_path):
    path = write(
        tmp_path / "opencode.json",
        {
            "provider": {
                "local": {**LEGACY_MAC, "models": {"old": {"status": "deprecated"}, "live": {}}}
            }
        },
    )
    config = OpencodeConfig.load(path)

    assert config.move_to_current_map("local")
    assert not config.set_model_visible("local", "live", False)
    config.save()

    models = json.loads(path.read_text())["providers"]["local"]["models"]
    assert models["old"] == {"disabled": True}, "a model opencode was told away from stays away"
    assert models["live"] == {"disabled": True}


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_add_sync_and_toggle_end_in_one_format_on_every_platform(tmp_path, monkeypatch, platform):
    import sys
    monkeypatch.setattr(sys, "platform", platform)
    path = write(tmp_path / "opencode.json", {"model": "strata-pc/model"})
    config = OpencodeConfig.load(path)
    config.add_provider("strata-pc", "Strata PC", "http://localhost:1234/v1/", "key")
    config.add_models("strata-pc", {"model": config.model_entry("strata-pc", "Model", 8192, True)})
    config.save()
    original = json.loads(path.read_text())["providers"]["strata-pc"]
    assert original["package"] == "aisdk:@ai-sdk/openai-compatible"
    assert original["settings"] == {"baseURL": "http://localhost:1234/v1", "apiKey": "key"}
    assert original["models"]["model"]["capabilities"] == {"tools": True}
    assert not config.set_model_visible("strata-pc", "model", False), "the provider is already in the one map"
    config.save()
    saved = json.loads(path.read_text())
    assert "provider" not in saved
    assert saved["model"] == "strata-pc/model"
    assert saved["providers"]["strata-pc"]["models"]["model"]["disabled"] is True
    assert not config.set_model_visible("strata-pc", "model", True)
    config.save()
    assert json.loads(path.read_text())["providers"]["strata-pc"] == original, "off and on again, the same entry"
    assert len(list(tmp_path.glob("opencode.json.bak-model-sync-*"))) == 1


def test_a_provider_the_current_map_cannot_hold_is_left_where_it_is(tmp_path):
    """Dropping a setting the user wrote is worse than a switch that waits, so the provider stays
    in the map opencode still reads it from, is reported as stuck, and refuses an edit."""
    path = write(tmp_path / "opencode.json", {
        "provider": {"local": {**LEGACY_MAC, "whitelist": ["one"]}},
    })
    config = OpencodeConfig.load(path)
    provider = config.provider("local")
    assert provider.stuck and provider.untranslatable == ("whitelist",)
    assert provider.base_url == "http://192.168.1.10:11434/v1", "it stays readable, only not rewritable"

    for edit in (lambda: config.set_model_visible("local", "qwen3.8:27b-mlx", False),
                 lambda: config.rename_provider("local", "New name"),
                 lambda: config.set_model_tools("local", "qwen3.8:27b-mlx", True)):
        with pytest.raises(ConfigError):
            edit()
    config.save()
    saved = json.loads(path.read_text())
    assert saved["provider"]["local"]["whitelist"] == ["one"]
    assert "providers" not in saved, "nothing was rewritten at the cost of a setting"


@pytest.mark.parametrize("section", ["provider", "providers"])
def test_rename_provider_writes_the_current_map_and_keeps_the_id(tmp_path, section):
    path = write(tmp_path / "opencode.json", {section: {"local": LEGACY_MAC}, "model": "local/m"})
    config = OpencodeConfig.load(path)
    config.rename_provider("local", "  New name  ")
    config.save()
    saved = json.loads(path.read_text())
    assert "provider" not in saved, "whichever map it came from, one map gets the write"
    assert saved["providers"]["local"]["name"] == "New name"
    assert saved["model"] == "local/m", "a rename never touches the id opencode works with"
    # The backup is the file as it stood, still in the words it came in.
    assert json.loads(next(tmp_path.glob("*.bak-*")).read_text())[section]["local"] == LEGACY_MAC
    with pytest.raises(ConfigError):
        config.rename_provider("local", "  ")
    with pytest.raises(ConfigError):
        config.rename_provider("missing", "New name")


@pytest.mark.parametrize("sections", [("provider",), ("providers",), ("provider", "providers")])
def test_remove_provider_clears_shadowed_entries_and_references(tmp_path, sections):
    data = {section: {"local": LEGACY_MAC, "other": LEGACY_MAC} for section in sections}
    data.update({"model": "local/m", "small_model": "other/m",
                 "agent": {"build": {"model": "local/m", "prompt": "keep"},
                           "review": {"model": "local-other/m"}},
                 "mode": {"plan": {"model": "local/m"}},
                 "enabled_providers": ["local", "other"], "disabled_providers": ["else"],
                 "theme": "dark"})
    path = write(tmp_path / "opencode.json", data)
    config = OpencodeConfig.load(path)
    config.remove_provider("local")
    config.save()
    saved = OpencodeConfig.load(path)
    assert saved.provider("local") is None
    for section in sections:
        assert saved.data[section] == {"other": LEGACY_MAC}
    assert "model" not in saved.data
    assert saved.data["small_model"] == "other/m"
    assert saved.data["agent"] == {"build": {"prompt": "keep"}, "review": {"model": "local-other/m"}}
    assert saved.data["mode"] == {"plan": {}}
    assert saved.data["enabled_providers"] == ["other"]
    assert saved.data["disabled_providers"] == ["else"]
    assert saved.data["theme"] == "dark"
    assert json.loads(next(tmp_path.glob("*.bak-*")).read_text()) == data
    with pytest.raises(ConfigError):
        saved.remove_provider("local")


def test_a_write_drops_the_legacy_copy_a_current_entry_has_already_shadowed(tmp_path):
    """opencode reads one of the two and ignores the other, so the dead copy is not worth keeping —
    but only once something is actually written, never on a load."""
    path = write(
        tmp_path / "opencode.json",
        {
            "provider": {"local": LEGACY_MAC},
            "providers": {"local": {"settings": {"baseURL": "http://127.0.0.1:1234/v1"}, "models": {}}},
        },
    )
    config = OpencodeConfig.load(path)
    assert config.provider("local").base_url == "http://127.0.0.1:1234/v1"
    assert json.loads(path.read_text())["provider"], "reading alone never touches the file"

    config.rename_provider("local", "Live")
    config.save()
    saved = json.loads(path.read_text())
    assert "provider" not in saved
    assert saved["providers"]["local"]["settings"] == {"baseURL": "http://127.0.0.1:1234/v1"}, \
        "the copy opencode never read is gone, the one it reads is untouched"


def test_a_provider_of_the_current_map_written_in_the_old_words_is_only_reworded(tmp_path):
    """An entry can sit in ``providers`` and still be spelled ``npm``/``options``; it stays there,
    because moving it is not the point — saying it the way that map is read is."""
    path = write(tmp_path / "opencode.json", {"providers": {"mixed": dict(LEGACY_MAC)}})
    config = OpencodeConfig.load(path)
    assert config.provider("mixed").base_url == "http://192.168.1.10:11434/v1", "readable as it stands"
    config.set_model_tools("mixed", "qwen3.8:27b-mlx", False)
    config.save()
    saved = json.loads(path.read_text())["providers"]["mixed"]
    assert "npm" not in saved and "options" not in saved
    assert saved["package"] == "aisdk:@ai-sdk/openai-compatible"
    assert saved["settings"] == LEGACY_MAC["options"]
    assert saved["models"]["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx", "capabilities": {"tools": False}}


@pytest.mark.parametrize("operation", ["rename", "remove"])
def test_provider_edits_do_not_overwrite_jsonc(tmp_path, operation):
    path = tmp_path / "opencode.jsonc"
    original = '{/* keep */ "provider": {"local": {"name": "Local"}}}'
    path.write_text(original)
    config = OpencodeConfig.load(path)
    if operation == "rename":
        config.rename_provider("local", "New name")
    else:
        config.remove_provider("local")
    with pytest.raises(ConfigError):
        config.save()
    assert path.read_text() == original
