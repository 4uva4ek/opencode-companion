"""Reading and writing the global opencode config.

opencode reads ``opencode.json`` and ``opencode.jsonc`` from its config directory and lets the later
name win. Providers live in the ``providers`` map: a package specifier, its settings and headers, and
a models map where each model carries its capabilities, limits and cost tiers.

Only this map is read and written. What an older opencode spelled in the ``provider`` map is not
read at all: an old-format config is the user's to rewrite, and an unknown map is simply no provider.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from .i18n import tr

CONFIG_NAMES = ("opencode.json", "opencode.jsonc")
PROVIDERS = "providers"
OPENAI_COMPATIBLE = "@ai-sdk/openai-compatible"

# The map names an AI SDK provider by the SDK that loads it.
AISDK = "aisdk:"


class ConfigError(Exception):
    """The config cannot be read or safely written."""


@dataclass
class Provider:
    id: str
    name: str
    base_url: str | None
    api_key: str | None
    models: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.name or self.id


def config_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    if env.get("OPENCODE_CONFIG_DIR"):
        return Path(env["OPENCODE_CONFIG_DIR"])
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "opencode"


def config_path(directory: Path | None = None) -> Path:
    directory = directory or config_dir()
    existing = [directory / name for name in CONFIG_NAMES if (directory / name).is_file()]
    return existing[-1] if existing else directory / "opencode.json"


class OpencodeConfig:
    def __init__(self, path: Path, data: dict[str, Any], has_comments: bool) -> None:
        self.path = path
        self.data = data
        self.has_comments = has_comments
        self._backed_up = False

    @classmethod
    def load(cls, path: Path | None = None) -> OpencodeConfig:
        path = path or config_path()
        if not path.exists():
            return cls(path, {"$schema": "https://opencode.ai/config.json"}, has_comments=False)
        text = path.read_text(encoding="utf-8")
        try:
            return cls(path, _as_object(json.loads(text) if text.strip() else {}), has_comments=False)
        except json.JSONDecodeError:
            pass
        try:
            return cls(path, _as_object(json.loads(strip_jsonc(text))), has_comments=True)
        except json.JSONDecodeError as error:
            raise ConfigError(tr("error.invalidJson", file=path, error=error)) from error

    def providers(self) -> list[Provider]:
        current = _as_object(self.data.get(PROVIDERS, {}))
        result = [self._provider(pid, entry) for pid, entry in current.items() if isinstance(entry, dict)]
        return sorted(result, key=lambda provider: provider.title.lower())

    def provider(self, provider_id: str) -> Provider | None:
        return next((item for item in self.providers() if item.id == provider_id), None)

    def add_models(self, provider_id: str, models: dict[str, dict[str, Any]]) -> None:
        entry = self._entry(provider_id)
        target = entry.setdefault("models", {})
        for model_id, model in models.items():
            target.setdefault(model_id, model)

    def remove_models(self, provider_id: str, model_ids: list[str]) -> None:
        models = self._entry(provider_id).get("models", {})
        for model_id in model_ids:
            models.pop(model_id, None)

    def set_model_tools(self, provider_id: str, model_id: str, tools: bool) -> None:
        """Turn tool calling on or off for a model already in the config."""
        entry = self._model(provider_id, model_id)
        entry.setdefault("capabilities", {})["tools"] = tools

    def set_model_vision(self, provider_id: str, model_id: str, enabled: bool, *, overwrite: bool = True) -> bool:
        entry = self._model(provider_id, model_id)
        if not overwrite and not vision_unset(entry):
            return False
        _set_vision(entry, enabled)
        return True

    def set_model_visible(self, provider_id: str, model_id: str, enabled: bool) -> None:
        """Show or hide a model in the backend catalog.

        The Desktop dropdown preference is managed separately by OpenCode.

        ``disabled`` is the one word opencode reads; showing a model again clears the word without
        leaving a ``disabled: false`` behind.
        """
        entry = self._model(provider_id, model_id)
        if enabled:
            entry.pop("disabled", None)
        else:
            entry["disabled"] = True

    def model_context(self, provider_id: str, model_id: str) -> int | None:
        """The context limit as the config writes it, for the editor to start from."""
        return configured_context(self._model(provider_id, model_id))

    def set_model_context(self, provider_id: str, model_id: str, context: int | None) -> None:
        """The context window in tokens; ``None`` drops the limit and lets opencode decide.

        An output limit that no longer fits inside the window is rederived the way a fresh entry
        gets one; a modest one the owner wrote is left alone.
        """
        entry = self._model(provider_id, model_id)
        if context is None:
            entry.pop("limit", None)
            return
        limit = entry.get("limit") if isinstance(entry.get("limit"), dict) else {}
        limit["context"] = context
        output = limit.get("output")
        if not isinstance(output, int) or isinstance(output, bool) or not 0 < output < context:
            limit["output"] = min(32768, context // 2)
        entry["limit"] = limit

    def read_model_entry(self, provider_id: str, model_id: str) -> dict[str, Any]:
        """Everything the config says about one model, for the editor to start from."""
        return deepcopy(self._model(provider_id, model_id))

    def set_model_entry(self, provider_id: str, model_id: str, entry: dict[str, Any]) -> None:
        """Write the whole entry the editor showed.

        A field left empty is dropped rather than written as an empty map: absence is what makes
        opencode decide that one itself, while ``{}`` would be the owner saying "nothing here".
        """
        empty = (dict, list, str)
        keep = {key: value for key, value in entry.items()
                if value is not None and not (isinstance(value, empty) and not value)}
        self._entry(provider_id).setdefault("models", {})[model_id] = keep

    def add_provider(self, provider_id: str, name: str, base_url: str, api_key: str | None) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", provider_id):
            raise ConfigError(tr("error.badId"))
        if self.provider(provider_id):
            raise ConfigError(tr("error.exists", id=provider_id))
        settings: dict[str, Any] = {"baseURL": base_url.rstrip("/")}
        if api_key:
            settings["apiKey"] = api_key
        self.data.setdefault(PROVIDERS, {})[provider_id] = {
            "package": f"{AISDK}{OPENAI_COMPATIBLE}",
            "name": name or provider_id,
            "settings": settings,
            "models": {},
        }

    def rename_provider(self, provider_id: str, name: str) -> None:
        """Change the display name without invalidating provider/model IDs."""
        name = name.strip()
        if not name:
            raise ConfigError(tr("error.emptyName"))
        self._entry(provider_id)["name"] = name

    def connection(self, provider_id: str) -> tuple[str, str | None]:
        """The stored words as written, unresolved: an edit must not quietly replace an env reference."""
        entry = _as_object(_as_object(self.data.get(PROVIDERS)).get(provider_id))
        settings = _as_object(entry.get("settings"))
        base_url = settings.get("baseURL")
        api_key = settings.get("apiKey")
        return (
            base_url if isinstance(base_url, str) else "",
            api_key if isinstance(api_key, str) else None,
        )

    def edit_provider(self, provider_id: str, name: str, base_url: str, api_key: str | None) -> None:
        """New words for a provider that exists: the name and the connection.

        Everything else the entry holds — models, package, settings no editor knows about — stays
        as its owner wrote it. An empty key is no news: the saved key is what the server still gets.
        """
        name = name.strip()
        if not name:
            raise ConfigError(tr("error.emptyName"))
        entry = self._entry(provider_id)
        entry["name"] = name
        settings = _as_object(entry.get("settings"))
        settings["baseURL"] = base_url.rstrip("/")
        if api_key:
            settings["apiKey"] = api_key
        entry["settings"] = settings

    def remove_provider(self, provider_id: str) -> None:
        if not self.provider(provider_id):
            raise ConfigError(tr("error.missing", id=provider_id))
        current = _as_object(self.data.get(PROVIDERS))
        current.pop(provider_id, None)
        if not current:
            self.data.pop(PROVIDERS, None)
        # Let opencode choose a fallback instead of retaining an unavailable model.
        def clear_models(entry: dict[str, Any]) -> None:
            value = entry.get("model")
            if isinstance(value, str) and value.startswith(provider_id + "/"):
                entry.pop("model")

        clear_models(self.data)
        for entry in _as_object(self.data.get("agents")).values():
            if isinstance(entry, dict):
                clear_models(entry)

    def save(self) -> None:
        if self.has_comments:
            raise ConfigError(tr("error.comments", file=self.path.name))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self._backed_up:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.path, self.path.with_name(f"{self.path.name}.bak-model-sync-{stamp}"))
            self._backed_up = True
        text = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        # Write beside the target and swap, so opencode's watcher never reads a half-written file.
        handle, temp = tempfile.mkstemp(dir=self.path.parent, prefix=".opencode-model-sync-", suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(text)
            os.replace(temp, self.path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise

    def model_entry(self, name: str | None, context: int | None, tools: bool | None, vision: bool | None = None) -> dict:
        """A model definition spelled the way the ``providers`` map wants it."""
        entry: dict[str, Any] = {}
        if name:
            entry["name"] = name
        if tools is not None:
            entry["capabilities"] = {"tools": tools}
        if vision is not None:
            _set_vision(entry, vision)
        if context:
            entry["limit"] = {"context": context, "output": min(32768, context // 2)}
        return entry

    def _provider(self, provider_id: str, entry: dict[str, Any]) -> Provider:
        settings = _as_object(entry.get("settings"))
        base_url = settings.get("baseURL")
        api_key = settings.get("apiKey")
        return Provider(
            id=provider_id,
            name=str(entry.get("name") or provider_id),
            base_url=resolve_variables(base_url) if isinstance(base_url, str) and base_url else None,
            api_key=resolve_variables(api_key) if isinstance(api_key, str) and api_key else None,
            models={key: value for key, value in _as_object(entry.get("models", {})).items() if isinstance(value, dict)},
        )

    def _entry(self, provider_id: str) -> dict[str, Any]:
        provider = self.provider(provider_id)
        if not provider:
            raise ConfigError(tr("error.missing", id=provider_id))
        return _as_object(self.data.setdefault(PROVIDERS, {}))[provider_id]

    def _model(self, provider_id: str, model_id: str) -> dict[str, Any]:
        entry = _as_object(self._entry(provider_id).get("models", {})).get(model_id)
        if not isinstance(entry, dict):
            raise ConfigError(tr("error.missing", id=f"{provider_id}/{model_id}"))
        return entry


def configured_vision(entry: dict[str, Any]) -> bool | None:
    inputs = _as_object(entry.get("capabilities")).get("input")
    if isinstance(inputs, list) and all(isinstance(item, str) for item in inputs):
        return "image" in inputs
    return None


def vision_unset(entry: dict[str, Any]) -> bool:
    """Automatic enrichment never overrides an explicit (even malformed) user choice."""
    value = entry.get("capabilities", {})
    return isinstance(value, dict) and "input" not in value and _valid_modalities(value)


def _valid_modalities(value: dict) -> bool:
    return all(key not in value or isinstance(value[key], list) and
               all(isinstance(item, str) for item in value[key]) for key in ("input", "output"))


def _set_vision(entry: dict, enabled: bool) -> None:
    value = entry.get("capabilities", {})
    if not isinstance(value, dict) or not _valid_modalities(value):
        raise ConfigError(tr("vision.invalidConfig"))
    value = dict(value)
    inputs = list(value.get("input", ["text"]))
    if enabled and "image" not in inputs:
        inputs.append("image")
    elif not enabled:
        inputs = [item for item in inputs if item != "image"]
    value["input"] = inputs
    value.setdefault("output", ["text"])
    entry["capabilities"] = value


def configured_tools(entry: dict[str, Any]) -> bool | None:
    """Tool calling as written in a model entry; None when the config does not say."""
    tools = _as_object(entry.get("capabilities", {})).get("tools")
    return tools if isinstance(tools, bool) else None


def configured_context(entry: dict[str, Any]) -> int | None:
    """The context limit as written; None when the config leaves it to opencode."""
    value = _as_object(entry.get("limit")).get("context")
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def configured_visible(entry: dict[str, Any]) -> bool:
    """Whether opencode offers a model: only ``disabled`` carries a decision, and only opencode 2.x reads it."""
    return entry.get("disabled") is not True


def resolve_variables(value: str) -> str:
    """Expand opencode's ``{env:NAME}`` placeholders; unknown variables become empty."""
    return re.sub(r"\{env:([^}]+)\}", lambda match: os.environ.get(match.group(1).strip(), ""), value)


def strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas outside strings."""
    out: list[str] = []
    index = 0
    in_string = False
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if char == "\\" and index + 1 < len(text):
                out.append(text[index + 1])
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            out.append(char)
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = len(text) if newline == -1 else newline
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end == -1 else end + 2
            continue
        else:
            out.append(char)
        index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _as_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
