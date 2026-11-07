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


MAC = {
    "package": "aisdk:@ai-sdk/openai-compatible",
    "name": "Ollama MAC",
    "settings": {"baseURL": "http://192.168.1.10:11434/v1", "apiKey": "ollama"},
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


def test_the_old_provider_map_is_no_provider_at_all(tmp_path):
    """An app that speaks one map does not pretend to read the other: the old key is nobody's provider,
    and a write leaves it on disk alone — the user's file, the user's cleanup."""
    path = write(tmp_path / "opencode.json", {"provider": {"ollama-mac": {"npm": "@ai-sdk/openai-compatible"}}})
    config = OpencodeConfig.load(path)
    assert config.providers() == []
    assert config.provider("ollama-mac") is None
    config.add_provider("live", "Live", "http://h/v1", None)
    config.save()
    saved = json.loads(path.read_text())
    assert saved["provider"] == {"ollama-mac": {"npm": "@ai-sdk/openai-compatible"}}
    assert saved["providers"]["live"]["package"] == "aisdk:@ai-sdk/openai-compatible"


def test_models_are_written_as_the_map_reads_them(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"ollama-mac": dict(MAC)}})
    config = OpencodeConfig.load(path)
    entry = config.model_entry(None, 65536, True)
    config.add_models("ollama-mac", {"qwen3.6:latest": entry})
    config.save()

    saved = json.loads(path.read_text())
    mac = saved["providers"]["ollama-mac"]
    assert mac["settings"]["baseURL"] == "http://192.168.1.10:11434/v1"
    assert mac["models"]["qwen3.6:latest"] == {"capabilities": {"tools": True}, "limit": {"context": 65536, "output": 32768}}
    assert mac["models"]["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx"}


def test_existing_model_settings_are_kept(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"ollama-mac": dict(MAC)}})
    config = OpencodeConfig.load(path)
    config.add_models("ollama-mac", {"qwen3.8:27b-mlx": {"name": "overwritten?"}})
    assert config.provider("ollama-mac").models["qwen3.8:27b-mlx"] == {"name": "Qwen3.8-mlx"}


def test_remove_models(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"ollama-mac": dict(MAC)}})
    config = OpencodeConfig.load(path)
    config.remove_models("ollama-mac", ["qwen3.8:27b-mlx", "unknown"])
    assert config.provider("ollama-mac").models == {}


def test_save_backs_up_once_and_keeps_other_keys(tmp_path):
    path = write(tmp_path / "opencode.json", {"$schema": "x", "theme": "dark", "providers": {"m": dict(MAC)}})
    config = OpencodeConfig.load(path)
    config.remove_models("m", ["qwen3.8:27b-mlx"])
    config.save()
    config.save()
    backups = list(tmp_path.glob("opencode.json.bak-model-sync-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["providers"]["m"]["models"]
    assert json.loads(path.read_text())["theme"] == "dark"


def test_add_provider_writes_the_only_map(tmp_path):
    config = OpencodeConfig.load(tmp_path / "opencode.json")
    config.add_provider("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1/", "secret")
    config.save()
    saved = json.loads((tmp_path / "opencode.json").read_text())
    assert saved["providers"]["lmstudio"] == {
        "package": "aisdk:@ai-sdk/openai-compatible",
        "name": "LM Studio",
        "settings": {"baseURL": "http://127.0.0.1:1234/v1", "apiKey": "secret"},
        "models": {},
    }
    with pytest.raises(ConfigError):
        config.add_provider("lmstudio", "again", "http://x", None)
    with pytest.raises(ConfigError):
        config.add_provider("bad id", "x", "http://x", None)


def test_edit_provider_moves_the_connection_and_keeps_the_rest(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"local": {
        "package": "aisdk:@ai-sdk/openai-compatible",
        "name": "Local",
        "settings": {"baseURL": "http://old/v1", "apiKey": "old-key", "timeout": 5},
        "models": {"m": {"limit": {"context": 200000}}},
    }}})
    config = OpencodeConfig.load(path)
    assert config.connection("local") == ("http://old/v1", "old-key")
    config.edit_provider("local", "  Strata PC  ", "http://new:1234/v1/", None)  # an empty key is no news
    config.save()
    entry = json.loads(path.read_text())["providers"]["local"]
    assert entry["name"] == "Strata PC"
    assert entry["settings"] == {"baseURL": "http://new:1234/v1", "apiKey": "old-key", "timeout": 5}
    assert entry["models"] == {"m": {"limit": {"context": 200000}}}
    assert entry["package"] == "aisdk:@ai-sdk/openai-compatible"
    config.edit_provider("local", "Strata PC", "http://new:1234/v1", "fresh")
    assert config.connection("local") == ("http://new:1234/v1", "fresh")
    with pytest.raises(ConfigError):
        config.edit_provider("missing", "x", "http://y/v1", None)
    with pytest.raises(ConfigError):
        config.edit_provider("local", "  ", "http://y/v1", None)


def test_context_limit_is_written_and_let_go(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"local": {"models": {
        "big": {"limit": {"context": 200000, "output": 8192}},
        "plain": {},
    }}}})
    config = OpencodeConfig.load(path)
    assert config.model_context("local", "big") == 200000
    config.set_model_context("local", "big", 131072)  # a modest output the owner wrote stays
    config.set_model_context("local", "plain", 128000)  # a fresh window derives its output
    config.save()
    models = json.loads(path.read_text())["providers"]["local"]["models"]
    assert models["big"] == {"limit": {"context": 131072, "output": 8192}}
    assert models["plain"] == {"limit": {"context": 128000, "output": 32768}}
    config.set_model_context("local", "big", 4096)  # an output too big for the window is rederived
    assert config.model_context("local", "big") == 4096
    assert config._entry("local")["models"]["big"]["limit"]["output"] == 2048
    config.set_model_context("local", "big", None)  # opencode decides again
    config.save()
    assert "limit" not in json.loads(path.read_text())["providers"]["local"]["models"]["big"]
    assert config.model_context("local", "big") is None


def test_the_model_window_writes_its_entry_as_a_whole(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"local": {"models": {
        "m": {"name": "Qwen", "settings": {"temperature": 0.7}, "disabled": True}}}}})
    config = OpencodeConfig.load(path)
    entry = config.read_model_entry("local", "m")
    assert entry == {"name": "Qwen", "settings": {"temperature": 0.7}, "disabled": True}
    entry["settings"]["temperature"] = 0.2  # what the editor does to its copy is not the config's
    assert config.read_model_entry("local", "m")["settings"]["temperature"] == 0.7
    config.set_model_entry("local", "m", {"name": "Qwen", "settings": {"temperature": 0.2},
                                         "headers": {}, "limit": None, "disabled": False})
    config.save()
    assert json.loads(path.read_text())["providers"]["local"]["models"]["m"] == {
        "name": "Qwen", "settings": {"temperature": 0.2}, "disabled": False}, (
        "a field left empty leaves the file; a refusal is a word opencode has to read")
    config.set_model_entry("local", "m", {})
    config.save()
    assert json.loads(path.read_text())["providers"]["local"]["models"]["m"] == {}, (
        "the model itself stays in the map even with nothing said about it")


def test_jsonc_is_read_but_not_overwritten(tmp_path):
    path = tmp_path / "opencode.jsonc"
    path.write_text('{\n  // keep me\n  "providers": {"m": {"settings": {"baseURL": "http://a//b"},},},\n}\n')
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
        {"providers": {"m": {"settings": {"baseURL": "http://h/v1", "apiKey": "{env:MY_KEY}"}}}},
    )
    assert OpencodeConfig.load(path).provider("m").api_key == "secret"


def test_set_model_tools_writes_the_one_shape(tmp_path):
    path = write(
        tmp_path / "opencode.json",
        {"providers": {"new": {"settings": {"baseURL": "http://h/v1"}, "models": {"m": {"name": "M"}}}}},
    )
    config = OpencodeConfig.load(path)
    config.set_model_tools("new", "m", False)
    assert config.provider("new").models["m"] == {"name": "M", "capabilities": {"tools": False}}
    with pytest.raises(ConfigError):
        config.set_model_tools("new", "unknown", True)


def test_configured_tools_reads_the_one_word():
    from opencode_model_sync.config import configured_tools

    assert configured_tools({"tool_call": False}) is None, "the old word means nothing here"
    assert configured_tools({"capabilities": {"tools": True}}) is True
    assert configured_tools({"name": "x"}) is None


def test_switching_a_model_off_leaves_the_mark_opencode_reads(tmp_path):
    """Only ``disabled`` keeps a model out of the list opencode works from."""
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
    assert configured_visible(models["on"])
    assert not configured_visible(models["off"])

    config.set_model_visible("local", "on", False)
    config.set_model_visible("local", "off", True)
    config.save()

    saved = json.loads(path.read_text())["providers"]["local"]["models"]
    assert saved["on"] == {"disabled": True}
    assert saved["off"] == {"capabilities": {"tools": True}}, "switching on clears the mark and leaves the rest alone"
    with pytest.raises(ConfigError):
        config.set_model_visible("local", "unknown", True)


def test_only_disabled_carries_a_decision():
    assert configured_visible({"status": "deprecated"}), "the old word means nothing to opencode 2.x"
    assert not configured_visible({"disabled": True})


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_add_sync_and_toggle_end_in_one_format_on_every_platform(tmp_path, monkeypatch, platform):
    import sys
    monkeypatch.setattr(sys, "platform", platform)
    path = write(tmp_path / "opencode.json", {"model": "strata-pc/model"})
    config = OpencodeConfig.load(path)
    config.add_provider("strata-pc", "Strata PC", "http://localhost:1234/v1/", "key")
    config.add_models("strata-pc", {"model": config.model_entry("Model", 8192, True)})
    config.save()
    original = json.loads(path.read_text())["providers"]["strata-pc"]
    assert original["package"] == "aisdk:@ai-sdk/openai-compatible"
    assert original["settings"] == {"baseURL": "http://localhost:1234/v1", "apiKey": "key"}
    assert original["models"]["model"]["capabilities"] == {"tools": True}
    config.set_model_visible("strata-pc", "model", False)
    config.save()
    saved = json.loads(path.read_text())
    assert saved["model"] == "strata-pc/model"
    assert saved["providers"]["strata-pc"]["models"]["model"]["disabled"] is True
    config.set_model_visible("strata-pc", "model", True)
    config.save()
    assert json.loads(path.read_text())["providers"]["strata-pc"] == original, "off and on again, the same entry"
    assert len(list(tmp_path.glob("opencode.json.bak-model-sync-*"))) == 1


def test_rename_provider_writes_the_map_and_keeps_the_id(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"local": dict(MAC)}, "model": "local/m"})
    config = OpencodeConfig.load(path)
    config.rename_provider("local", "  New name  ")
    config.save()
    saved = json.loads(path.read_text())
    assert saved["providers"]["local"]["name"] == "New name"
    assert saved["model"] == "local/m", "a rename never touches the id opencode works with"
    assert json.loads(next(tmp_path.glob("*.bak-*")).read_text())["providers"]["local"] == MAC
    with pytest.raises(ConfigError):
        config.rename_provider("local", "  ")
    with pytest.raises(ConfigError):
        config.rename_provider("missing", "New name")


def test_remove_provider_clears_references_to_the_model_it_held(tmp_path):
    data = {
        "providers": {"local": dict(MAC), "other": dict(MAC)},
        "model": "local/m",
        "agents": {"build": {"model": "local/m", "system": "keep"}, "review": {"model": "local-other/m"}},
        "theme": "dark",
    }
    path = write(tmp_path / "opencode.json", data)
    config = OpencodeConfig.load(path)
    config.remove_provider("local")
    config.save()
    saved = OpencodeConfig.load(path)
    assert saved.provider("local") is None
    assert saved.data["providers"] == {"other": MAC}
    assert "model" not in saved.data
    assert saved.data["agents"] == {"build": {"system": "keep"}, "review": {"model": "local-other/m"}}
    assert saved.data["theme"] == "dark"
    assert json.loads(next(tmp_path.glob("*.bak-*")).read_text()) == data
    with pytest.raises(ConfigError):
        saved.remove_provider("local")


def test_an_empty_providers_map_leaves_no_trace(tmp_path):
    path = write(tmp_path / "opencode.json", {"providers": {"local": dict(MAC)}})
    config = OpencodeConfig.load(path)
    config.remove_provider("local")
    config.save()
    assert "providers" not in json.loads(path.read_text()), "an empty map only invites the next reader to doubt itself"


@pytest.mark.parametrize("operation", ["rename", "remove"])
def test_provider_edits_do_not_overwrite_jsonc(tmp_path, operation):
    path = tmp_path / "opencode.jsonc"
    original = '{/* keep */ "providers": {"local": {"name": "Local"}}}'
    path.write_text(original)
    config = OpencodeConfig.load(path)
    if operation == "rename":
        config.rename_provider("local", "New name")
    else:
        config.remove_provider("local")
    with pytest.raises(ConfigError):
        config.save()
    assert path.read_text() == original
