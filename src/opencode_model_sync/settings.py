"""Versioned OpenCode configuration schema, validation and conflict-safe patches."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from jsonschema import Draft202012Validator

from .config import ConfigError, OpencodeConfig, strip_jsonc

MISSING = object()
CATEGORIES = {
    "general": ("$schema", "shell", "model", "default_agent", "update", "share", "enterprise", "username"),
    "models": ("providers",),
    "agents": ("agents", "commands"),
    "context": ("compaction", "warming", "media", "tool_output"),
    "workspace": ("snapshots", "watcher", "formatter", "lsp", "worktree"),
    "sources": ("skills", "instructions", "references"),
    "integrations": ("plugins", "websearch"),
    "permissions": ("permissions", "policies"),
    "experimental": ("experimental",),
    "mcp": ("mcp",),
}


@lru_cache
def schema() -> dict:
    return json.loads(Path(__file__).with_name("settings_schema.json").read_text(encoding="utf-8"))


def resolve(info: dict) -> dict:
    if "$ref" not in info:
        return info
    key = info["$ref"].removeprefix("#/$defs/")
    return {**resolve(schema()["$defs"][key]), **{k: v for k, v in info.items() if k != "$ref"}}


def model_schema() -> dict:
    """The node that describes one entry of ``providers.<id>.models.<model>``.

    A model editor built on this node lists what opencode reads rather than what this app guesses.
    """
    provider = resolve(schema()["properties"]["providers"]["additionalProperties"])
    models = resolve(provider["properties"]["models"])
    return resolve(models["additionalProperties"])


@dataclass(frozen=True)
class Field:
    path: tuple[str, ...]
    info: dict
    category: str

    @property
    def key(self) -> str:
        return ".".join(self.path)


def fields() -> list[Field]:
    result = []
    def visit(path, info, category):
        info = resolve(info)
        if info.get("properties") and info.get("additionalProperties") is False and not info.get("anyOf"):
            for name, child in info["properties"].items():
                visit((*path, name), child, category)
        else:
            result.append(Field(path, info, category))
    for name, info in schema()["properties"].items():
        category = next((key for key, names in CATEGORIES.items() if name in names), "general")
        visit((name,), info, category)
    return result


def get(data: dict, path: tuple[str, ...]):
    value = data
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def equal(a, b) -> bool:
    if a is MISSING or b is MISSING:
        return a is b
    # Python considers False == 0; JSON configuration does not.
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


def put(data: dict, path: tuple[str, ...], value) -> None:
    target = data
    parents = []
    for key in path[:-1]:
        if key not in target:
            if value is MISSING:
                return
            target[key] = {}
        if not isinstance(target[key], dict):
            raise ConfigError(".".join(path))
        parents.append((target, key))
        target = target[key]
    if value is MISSING:
        target.pop(path[-1], None)
        for parent, key in reversed(parents):
            if parent[key] == {}:
                del parent[key]
            else:
                break
    else:
        target[path[-1]] = deepcopy(value)


def validation_errors(value, info: dict) -> list[str]:
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError):
        return ["value: JSON"]
    validator = Draft202012Validator({**info, "$defs": schema()["$defs"]})
    return [f"{'.'.join(str(p) for p in error.absolute_path) or 'value'}: {error.validator}"
            for error in validator.iter_errors(value)]


def variants(info: dict) -> list[dict]:
    info = resolve(info)
    return [resolve(item) for item in info.get("anyOf", [info])]


def effect(path: tuple[str, ...]) -> str:
    root = path[0]
    if root in ("model", "default_agent", "agents", "small_model", "commands"):
        return "session"
    if root == "shell":
        return "terminal"
    if root in ("mcp", "lsp", "formatter", "plugins", "references"):
        return "services"
    return "live"


class Conflict(ConfigError):
    pass


def merge(base: dict, latest: dict, changes: dict[tuple[str, ...], object]) -> dict:
    result = deepcopy(latest)
    for path, value in changes.items():
        if not equal(get(base, path), get(latest, path)) and not equal(value, get(latest, path)):
            raise Conflict(".".join(path))
        put(result, path, value)
    for root in {path[0] for path in changes}:
        if root in result:
            errors = validation_errors(result[root], schema()["properties"][root])
            if errors:
                raise ConfigError(f"{root}: {'; '.join(errors[:4])}")
    return result


def _spans(text: str):
    """Parse JSONC object member/value spans; retain every untouched byte."""
    decoder = json.JSONDecoder()
    nodes = {}
    def skip(i):
        while i < len(text):
            if text[i].isspace(): i += 1
            elif text.startswith("//", i):
                end = text.find("\n", i)
                i = len(text) if end < 0 else end
            elif text.startswith("/*", i):
                end = text.find("*/", i + 2)
                if end < 0: raise ValueError("comment")
                i = end + 2
            else: break
        return i
    def value(i, path):
        start = i = skip(i)
        members = {}
        if text[i] == "{":
            i = skip(i + 1)
            while text[i] != "}":
                key_start = i
                key, end = decoder.raw_decode(text, i)
                i = skip(end)
                if text[i] != ":": raise ValueError("colon")
                value_start = skip(i + 1)
                i = value(value_start, (*path, key))
                value_end = i
                i = skip(i)
                comma = i if text[i] == "," else None
                members[key] = (key_start, value_start, value_end, comma)
                if comma is None: break
                i = skip(i + 1)
            if text[i] != "}": raise ValueError("object")
            end = i + 1
        elif text[i] == "[":
            i = skip(i + 1)
            index = 0
            while text[i] != "]":
                i = skip(value(i, (*path, index)))
                index += 1
                if text[i] != ",": break
                i = skip(i + 1)
            if text[i] != "]": raise ValueError("array")
            end = i + 1
        else:
            _parsed, end = decoder.raw_decode(text, i)
        nodes[path] = (start, end, members)
        return end
    value(0, ())
    return nodes


def patch_text(text: str, target: dict) -> str:
    current = json.loads(strip_jsonc(text)) if text.strip() else {}
    if not text.strip():
        return json.dumps(target, ensure_ascii=False, indent=2) + "\n"
    # One edit at a time avoids overlapping spans for adjacent removed members.
    def differences(old, new, path=()):
        if isinstance(old, dict) and isinstance(new, dict):
            for key in old:
                if key not in new: yield (*path, key), MISSING
                else: yield from differences(old[key], new[key], (*path, key))
            for key in new:
                if key not in old: yield (*path, key), new[key]
        elif not equal(old, new):
            yield path, new
    for path, new in differences(current, target):
        nodes = _spans(text)
        start, end, members = nodes[path[:-1]]
        key = path[-1]
        if key in members:
            key_start, val_start, val_end, comma = members[key]
            if new is not MISSING:
                indent = re.match(r"[ \t]*", text[text.rfind("\n", 0, key_start) + 1:key_start]).group()
                encoded = json.dumps(new, ensure_ascii=False, indent=2).replace("\n", "\n" + indent)
                text = text[:val_start] + encoded + text[val_end:]
            elif comma is not None:
                text = text[:key_start] + text[comma + 1:]
            else:
                keys = list(members)
                previous = members[keys[keys.index(key) - 1]][3] if keys.index(key) else None
                text = text[:key_start] + text[val_end:]
                if previous is not None:
                    text = text[:previous] + text[previous + 1:]
        else:
            indent = "  " * len(path)
            encoded = json.dumps(new, ensure_ascii=False, indent=2).replace("\n", "\n" + indent)
            insert = f"\n{indent}{json.dumps(key, ensure_ascii=False)}: {encoded}\n" + "  " * (len(path) - 1)
            # Put the missing comma directly after the last value, before any comment.
            last = next(reversed(members.values()), None)
            if last and last[3] is None:
                text = text[:end - 1] + insert + text[end - 1:]
                text = text[:last[2]] + "," + text[last[2]:]
            else:
                text = text[:end - 1] + insert + text[end - 1:]
    if not equal(json.loads(strip_jsonc(text)), target):
        raise ConfigError("JSONC patch verification failed")
    return text


def reset(path: Path) -> None:
    """Empty the config, its old bytes kept beside it: the way out when the file and the editors disagree."""
    if path.exists():
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, path.with_name(f"{path.name}.bak-model-sync-{stamp}"))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".model-sync-reset-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write("{}\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def save(path: Path, base: dict, changes: dict[tuple[str, ...], object]) -> dict:
    def read_exact():
        if not path.exists(): return ""
        with path.open(encoding="utf-8", newline="") as file:
            return file.read()
    latest_text = read_exact()
    latest = json.loads(strip_jsonc(latest_text)) if latest_text.strip() else {}
    if not isinstance(latest, dict):
        raise ConfigError("Configuration must be a JSON object")
    target = merge(base, latest, changes)
    if equal(target, latest): return target
    updated = patch_text(latest_text, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".model-sync-settings-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as file:
            file.write(updated)
        # Recheck immediately before replacing; never knowingly overwrite a concurrent save.
        if read_exact() != latest_text:
            raise Conflict(str(path))
        if path.exists():
            backup = path.with_name(f"{path.name}.bak-model-sync-{time.time_ns()}")
            with backup.open("x", encoding="utf-8", newline="") as file:
                file.write(latest_text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target
