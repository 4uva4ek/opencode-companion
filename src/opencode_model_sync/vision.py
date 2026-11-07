"""Opt-in visual capability checks. A transport success is never proof of vision."""
from __future__ import annotations

import base64
import copy
import json
import re
import secrets
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from .config import PROVIDERS, ConfigError, OpencodeConfig, resolve_variables
from .discovery import RemoteModel, _Client, _describe
from .i18n import tr

COLORS = {"red": (230, 30, 30), "green": (20, 170, 40), "blue": (30, 60, 230),
          "yellow": (245, 215, 15), "magenta": (210, 30, 200), "cyan": (10, 200, 210)}
SHAPES = ("circle", "square", "triangle")
PROMPT = (
    "Read the attached image. It contains four colored shapes in a 2 by 2 grid on white. "
    "Return ONLY a JSON array of four strings in top-left, top-right, bottom-left, bottom-right order. "
    "Each string must be 'color shape'. Colors: red, green, blue, yellow, magenta, cyan. "
    "Shapes: circle, square, triangle. Identify what is actually visible; do not guess if no image is available."
)


@dataclass(frozen=True)
class Challenge:
    png: bytes
    answer: tuple[str, ...]


def challenge() -> Challenge:
    """Randomize colors AND shapes; the answer never appears in the text prompt."""
    answer = tuple(secrets.SystemRandom().sample([f"{color} {shape}" for color in COLORS for shape in SHAPES], 4))
    size = 256
    pixels = bytearray([255]) * (size * size * 3)
    for index, item in enumerate(answer):
        color, shape = item.split()
        cx, cy = (64 + 128 * (index % 2), 64 + 128 * (index // 2))
        for dy in range(-40, 41):
            for dx in range(-40, 41):
                inside = shape == "square" or (shape == "circle" and dx * dx + dy * dy <= 1600) or (
                    shape == "triangle" and abs(dx) <= (dy + 40) / 2)
                if inside:
                    offset = ((cy + dy) * size + cx + dx) * 3
                    pixels[offset:offset + 3] = bytes(COLORS[color])
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + pixels[y * size * 3:(y + 1) * size * 3] for y in range(size))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 2, 0, 0, 0)) +
           chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return Challenge(png, answer)


@dataclass(frozen=True)
class ProbeResult:
    supported: bool | None
    reason: str = ""


def matches(content: object, expected: tuple[str, ...]) -> bool:
    if not isinstance(content, str):
        return False
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        answer = json.loads(text)
    except (ValueError, TypeError):
        return False
    return isinstance(answer, list) and len(answer) == len(expected) and all(
        isinstance(actual, str) and actual.strip().lower() == wanted for actual, wanted in zip(answer, expected)
    )


def probe(base_url: str, model_id: str, api_key: str | None = None, *, headers: dict | None = None,
          timeout: float = 60.0) -> ProbeResult:
    client = _Client(api_key, timeout, headers=headers)
    try:
        for _ in range(2):
            image = challenge()
            response = client.post(base_url.rstrip("/") + "/chat/completions", {
                "model": model_id, "stream": False, "max_tokens": 192, "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/png;base64," + base64.b64encode(image.png).decode("ascii")}},
                ]}],
            })
            content = response["choices"][0]["message"]["content"]
            if not matches(content, image.answer):
                return ProbeResult(None, tr("vision.inconclusive"))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        return ProbeResult(None, _describe(error))
    return ProbeResult(True)


def _snapshot(config: OpencodeConfig, provider_id: str, model_id: str) -> tuple:
    provider = config.provider(provider_id)
    if provider is None:
        raise ConfigError(tr("error.missing", id=provider_id))
    entry = config.data[PROVIDERS][provider_id]
    return (copy.deepcopy({key: value for key, value in entry.items() if key != "models"}),
            copy.deepcopy(provider.models.get(model_id)))


def _target(snapshot: tuple, model_id: str) -> tuple[str, str, str | None, dict]:
    provider, model = snapshot
    model = model or {}
    provider_options, model_options = provider.get("settings", {}), model.get("settings", {})
    options = {**provider_options, **model_options}
    # Honor endpoint and API model ID overrides without changing them in the config.
    base = options.get("baseURL")
    name = model.get("modelID") or model_id
    headers = {**provider_options.get("headers", {}), **provider.get("headers", {}),
               **model_options.get("headers", {}), **model.get("headers", {})}
    if not isinstance(base, str) or not base or not isinstance(name, str):
        raise ConfigError(tr("vision.noEndpoint"))
    key_value = options.get("apiKey")
    return (resolve_variables(base), name, resolve_variables(key_value) if isinstance(key_value, str) else None,
            {key: resolve_variables(value) for key, value in headers.items() if isinstance(value, str)})


def probe_and_enable(path: Path, provider_id: str, model_id: str, remote: RemoteModel | None = None) -> ProbeResult:
    config = OpencodeConfig.load(path)
    if config.has_comments:
        raise ConfigError(tr("error.comments", file=path.name))
    before = _snapshot(config, provider_id, model_id)
    if before[1] is None and (remote is None or remote.id != model_id):
        raise ConfigError(tr("error.missing", id=model_id))
    base, name, key, headers = _target(before, model_id)
    result = probe(base, name, key, headers=headers)
    if result.supported is not True:
        return result
    # Merge unrelated external edits; do not apply a result to a changed model/provider.
    fresh = OpencodeConfig.load(path)
    if _snapshot(fresh, provider_id, model_id) != before:
        raise ConfigError(tr("vision.changed"))
    if before[1] is None:
        if remote is None or remote.id != model_id:
            raise ConfigError(tr("error.missing", id=model_id))
        fresh.add_models(provider_id, {model_id: fresh.model_entry(
            remote.name, remote.context, remote.tools)})
    fresh.set_model_vision(provider_id, model_id, True)
    fresh.save()
    return result
