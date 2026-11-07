import json
import os
import sys
import time
from pathlib import Path

import pytest

from opencode_model_sync import catalog
from opencode_model_sync.config import OpencodeConfig

CATALOG = {
    "openrouter": {
        "name": "OpenRouter",
        "models": {
            "google/gemma-4-31b-it:free": {"name": "Gemma 4 31B", "tool_call": True, "cost": {"input": 0, "output": 0}, "limit": {"context": 131072}},
            "anthropic/claude-x": {"name": "Claude X", "tool_call": True, "cost": {"input": 3, "output": 15}},
        },
    },
    "opencode": {"name": "OpenCode Zen", "models": {"big-pickle": {"name": "Big Pickle", "tool_call": True, "cost": {"input": 0, "output": 0}}}},
}


def config(tmp_path: Path) -> OpencodeConfig:
    path = tmp_path / "opencode.json"
    path.write_text(
        json.dumps(
            {
                "providers": {
                    "lmstudio": {
                        "settings": {"baseURL": "http://127.0.0.1:1234/v1"},
                        "models": {"qwen-coder": {"name": "Qwen Coder", "capabilities": {"tools": False}, "limit": {"context": 65536, "output": 1}}},
                    },
                    "remote": {
                        "settings": {"baseURL": "https://api.example.com/v1"},
                        "models": {"m": {}, "off": {"disabled": True}},
                    },
                    "openrouter": {"models": {"anthropic/claude-x": {"disabled": True}}},
                },
            }
        ),
        encoding="utf-8",
    )
    return OpencodeConfig.load(path)


def test_choices_cover_only_connected_models(tmp_path):
    refs = ["lmstudio/qwen-coder", "openrouter/google/gemma-4-31b-it:free", "opencode/big-pickle", "opencode/unknown-free"]
    items = {item.ref: item for item in catalog.choices(config(tmp_path), refs, CATALOG)}
    assert list(items) == ["lmstudio/qwen-coder", "opencode/big-pickle", "opencode/unknown-free", "openrouter/google/gemma-4-31b-it:free"]
    local = items["lmstudio/qwen-coder"]
    assert local.local and local.free and local.tools is False and local.context == 65536 and local.name == "Qwen Coder"
    gemma = items["openrouter/google/gemma-4-31b-it:free"]
    assert gemma.free and gemma.tools and gemma.context == 131072 and gemma.provider == "OpenRouter"
    assert items["opencode/big-pickle"].provider == "OpenCode Zen"
    assert items["opencode/unknown-free"].free is True and items["opencode/unknown-free"].tools is None
    assert catalog.find(list(items.values()), "opencode/big-pickle#high").name == "Big Pickle"


def test_from_config_skips_disabled_models(tmp_path):
    assert catalog.from_config(config(tmp_path)) == ["lmstudio/qwen-coder", "remote/m"]


def test_a_switched_off_model_is_not_offered_to_an_agent(tmp_path):
    """``opencode models`` lists such a model, so the config has to have the last word."""
    refs = ["remote/m", "remote/off", "openrouter/anthropic/claude-x"]
    assert [item.ref for item in catalog.choices(config(tmp_path), refs, CATALOG)] == ["remote/m"]


def test_connected_parses_cli_output(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text(
        "import sys\nprint('Loading…')\nprint('lmstudio/qwen/qwen3-coder-30b')\nprint('opencode/big-pickle')\nprint('')\n",
        encoding="utf-8",
    )
    if sys.platform == "win32":
        cli = tmp_path / "opencode.cmd"
        cli.write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
    else:
        cli = tmp_path / "opencode"
        cli.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        cli.chmod(0o755)
    assert catalog.connected(cli) == ["lmstudio/qwen/qwen3-coder-30b", "opencode/big-pickle"]


@pytest.mark.parametrize(
    ("platform", "relative"),
    [
        ("win32", "AppData/Local/Programs/@opencodedesktop/resources/opencode-cli.exe"),
        ("win32", ".opencode/bin/opencode.exe"),
        ("darwin", "Applications/OpenCode.app/Contents/Resources/opencode-cli"),
        ("darwin", ".opencode/bin/opencode"),
        ("linux", ".local/bin/opencode"),
        ("linux", ".bun/bin/opencode"),
    ],
)
def test_find_cli_looks_in_install_folders(tmp_path, platform, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text("")
    env = {"PATH": str(tmp_path / "empty"), "HOME": str(tmp_path), "LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}
    assert catalog.find_cli(env, platform) == target


def test_find_cli_honours_override(tmp_path):
    cli = tmp_path / "my-opencode"
    cli.write_text("")
    assert catalog.find_cli({"OPENCODE_CLI": str(cli), "PATH": ""}) == cli
    assert catalog.find_cli({"OPENCODE_CLI": str(tmp_path / "missing"), "PATH": ""}) is None


def test_load_uses_fresh_cache_and_falls_back_to_stale(tmp_path, monkeypatch):
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps(CATALOG), encoding="utf-8")
    assert catalog.load(cache) == CATALOG

    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(catalog.urllib.request, "urlopen", offline)
    old = time.time() - 3 * 24 * 3600
    os.utime(cache, (old, old))
    assert catalog.load(cache) == CATALOG
    cache.unlink()
    with pytest.raises(OSError):
        catalog.load(cache)


def test_local_addresses():
    assert catalog._is_local("http://127.0.0.1:1234/v1")
    assert catalog._is_local("http://192.168.1.10:11434/v1")
    assert catalog._is_local("http://localhost:8080")
    assert not catalog._is_local("https://openrouter.ai/api/v1")
