"""Models an agent can run on: the ones opencode has connected, as ``opencode models`` lists them.

That list holds only names. The config and the models.dev catalog, which opencode itself uses, tell
which models are free, which can call tools and how long their context is. The catalog is a few
megabytes, so it is cached for a day and the cached copy is used when the site is down.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import OpencodeConfig, configured_visible, configured_tools

CATALOG_URL = "https://models.dev/api.json"
MAX_AGE = 24 * 3600


@dataclass
class ModelChoice:
    ref: str  # "provider/model", the form an agent's model field takes
    name: str
    provider: str
    free: bool | None = None
    tools: bool | None = None
    context: int | None = None
    local: bool = False


def cache_path(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if sys.platform == "win32" and env.get("LOCALAPPDATA"):
        base = Path(env["LOCALAPPDATA"])
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(env["XDG_CACHE_HOME"]) if env.get("XDG_CACHE_HOME") else Path.home() / ".cache"
    return base / "opencode-model-sync" / "models.json"


def load(path: Path, max_age: float = MAX_AGE, timeout: float = 30.0) -> dict[str, Any]:
    """The catalog from the cache while it is fresh, otherwise from models.dev; a stale cache beats nothing."""
    if path.is_file() and time.time() - path.stat().st_mtime < max_age:
        try:
            return _read(path)
        except (OSError, ValueError):
            pass
    try:
        request = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "opencode-model-sync"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("the catalog is not a JSON object")
    except (OSError, ValueError):
        if path.is_file():
            return _read(path)
        raise
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(handle, "wb") as file:
        file.write(raw)
    os.replace(temp, path)
    return data


def find_cli(env: Mapping[str, str] | None = None, platform: str = sys.platform) -> Path | None:
    """The opencode command line: on PATH, in an install script's folder, or inside OpenCode Desktop.

    An app started from the macOS Finder or a Linux menu gets a short PATH without the shell profile,
    so the usual install folders are checked by hand as well.
    """
    env = os.environ if env is None else env
    if env.get("OPENCODE_CLI"):
        path = Path(env["OPENCODE_CLI"]).expanduser()
        return path if path.is_file() else None
    for name in ("opencode", "opencode-cli"):
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return Path(found)
    home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    if platform == "win32":
        exe = ".exe"
        folders = [home / ".opencode" / "bin", home / "scoop" / "shims"]
        for variable in ("LOCALAPPDATA", "PROGRAMFILES"):
            if env.get(variable):
                for app in ("@opencodedesktop", "OpenCode"):
                    folders.append(Path(env[variable]) / ("Programs" if variable == "LOCALAPPDATA" else "") / app / "resources")
        if env.get("APPDATA"):
            folders.append(Path(env["APPDATA"]) / "npm")
    else:
        exe = ""
        folders = [home / ".opencode" / "bin", home / ".local" / "bin", home / ".bun" / "bin", home / ".npm-global" / "bin"]
        if platform == "darwin":
            folders += [
                home / "Applications" / "OpenCode.app" / "Contents" / "Resources",
                Path("/Applications/OpenCode.app/Contents/Resources"),
                Path("/opt/homebrew/bin"),
            ]
        else:
            folders += [Path("/opt/OpenCode/resources"), Path("/usr/lib/opencode/resources"), Path("/usr/lib/OpenCode/resources")]
        folders += [Path("/usr/local/bin"), Path("/usr/bin")]
    for folder in folders:
        for name in (f"opencode{exe}", f"opencode-cli{exe}", "opencode.cmd"):
            if (folder / name).is_file():
                return folder / name
    return None


def connected(cli: Path, timeout: float = 90.0) -> list[str]:
    """Every model opencode can use right now, as ``provider/model``: what ``opencode models`` prints."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [str(cli), "models"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=flags,
        check=False,
    )
    refs = [line.strip() for line in result.stdout.splitlines() if re.fullmatch(r"[^/\s]+/\S+", line.strip())]
    if result.returncode != 0 and not refs:
        raise OSError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit code {result.returncode}")
    return refs


def choices(config: OpencodeConfig, refs: list[str], catalog: Mapping[str, Any] | None = None) -> list[ModelChoice]:
    """The connected models, described from the config and the models.dev catalog where they know more."""
    catalog = catalog or {}
    providers = {provider.id: provider for provider in config.providers()}
    result: dict[str, ModelChoice] = {}
    for ref in refs:
        provider_id, model_id = ref.split("/", 1)
        provider = providers.get(provider_id)
        entry = provider.models.get(model_id, {}) if provider else {}
        if not configured_visible(entry):
            continue  # opencode offers a switched-off model to nobody, so an agent must not be sent to it
        info = _models(catalog.get(provider_id)).get(model_id, {})
        local = _is_local(provider.base_url if provider else None)
        tools = configured_tools(entry)
        limit = entry.get("limit") if isinstance(entry.get("limit"), dict) else {}
        free = _free(info)
        if local or re.search(r"[:-]free$", model_id) or model_id == "free":
            free = True
        result[ref] = ModelChoice(
            ref=ref,
            name=str(entry.get("name") or info.get("name") or model_id),
            # A provider entry without its own name only repeats the ID; the catalog knows the proper name.
            provider=provider.name
            if provider and provider.name != provider.id
            else str(_object(catalog.get(provider_id)).get("name") or provider_id),
            free=free,
            tools=tools if tools is not None else _bool(info.get("tool_call")),
            context=_int(limit.get("context")) or _context(info),
            local=local,
        )
    return sorted(result.values(), key=lambda item: (not item.local, item.free is not True, item.ref.lower()))


def from_config(config: OpencodeConfig) -> list[str]:
    """The models written in the config, for when the opencode command line is not available."""
    return [
        f"{provider.id}/{model_id}"
        for provider in config.providers()
        for model_id, entry in provider.models.items()
        if configured_visible(entry)
    ]


def find(items: list[ModelChoice], ref: str | None) -> ModelChoice | None:
    if not ref:
        return None
    base = ref.split("#", 1)[0]
    return next((item for item in items if item.ref == base), None)


def _read(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("the cached catalog is not a JSON object")
    return data


def _models(provider: Any) -> dict[str, dict[str, Any]]:
    models = _object(_object(provider).get("models"))
    return {key: value for key, value in models.items() if isinstance(value, dict)}


def _free(info: Mapping[str, Any]) -> bool | None:
    cost = info.get("cost")
    if not isinstance(cost, dict):
        return None
    return all(not cost.get(key) for key in ("input", "output"))


def _context(info: Mapping[str, Any]) -> int | None:
    return _int(_object(info.get("limit")).get("context"))


def _is_local(url: str | None) -> bool:
    """A server on this machine or the local network: running its models costs nothing per token."""
    host = urlparse(url or "").hostname
    if not host:
        return False
    if host == "localhost" or host.endswith((".local", ".lan", ".home.arpa")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
