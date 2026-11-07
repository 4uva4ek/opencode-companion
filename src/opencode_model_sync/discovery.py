"""Asking model servers which models they serve.

Ollama and LM Studio expose richer native endpoints than their OpenAI-compatible ``/v1/models``:
context length, tool support and whether a model is an embedding model. Those are tried first; any
other server falls back to the OpenAI-compatible listing.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .config import OpencodeConfig, Provider, configured_context, configured_visible, configured_tools, configured_vision, vision_unset

# Embedding, speech, image and moderation models share the listing but cannot drive a chat session.
NON_CHAT = re.compile(r"embed|whisper|tts|dall-e|moderation|transcribe|rerank|(^|[-/])image", re.IGNORECASE)

LOCAL_SERVERS = (
    ("ollama", "Ollama", "http://127.0.0.1:11434/v1"),
    ("lmstudio", "LM Studio", "http://127.0.0.1:1234/v1"),
    ("vllm", "vLLM", "http://127.0.0.1:8000/v1"),
    ("llamacpp", "llama.cpp", "http://127.0.0.1:8080/v1"),
)


@dataclass
class RemoteModel:
    id: str
    name: str | None = None
    context: int | None = None
    tools: bool | None = None
    vision: bool | None = None


@dataclass
class Discovery:
    ok: bool
    server: str = "openai"
    models: list[RemoteModel] = field(default_factory=list)
    error: str | None = None


@dataclass
class ModelRow:
    id: str
    name: str
    status: str  # "configured", "new" or "missing"
    remote: RemoteModel | None = None
    configured_tools: bool | None = None
    configured_visible: bool = True
    configured_vision: bool | None = None
    configured_context: int | None = None

    @property
    def in_config(self) -> bool:
        return self.status != "new"

    @property
    def context(self) -> int | None:
        """The config's number wins over what the server happens to report today."""
        if self.configured_context is not None:
            return self.configured_context
        return self.remote.context if self.remote else None

    @property
    def visible(self) -> bool:
        """Whether opencode offers this model; a switched-off one keeps its place in the config."""
        return self.configured_visible

    @property
    def tools(self) -> bool | None:
        """The config's choice wins over what the server reports."""
        if self.configured_tools is not None:
            return self.configured_tools
        return self.remote.tools if self.remote else None

    @property
    def vision(self) -> bool | None:
        if self.configured_vision is not None:
            return self.configured_vision
        return self.remote.vision if self.remote else None


@dataclass
class Suggestion:
    id: str
    name: str
    base_url: str
    count: int


def discover(base_url: str, api_key: str | None = None, timeout: float = 6.0) -> Discovery:
    base = base_url.rstrip("/")
    root = re.sub(r"/(v1|api|api/v0|api/v1)$", "", base)
    client = _Client(api_key, timeout)
    try:
        ollama = _ollama(client, root)
        if ollama is not None:
            return Discovery(ok=True, server="ollama", models=ollama)
        lmstudio = _lmstudio(client, root)
        if lmstudio is not None:
            return Discovery(ok=True, server="lmstudio", models=lmstudio)
        return Discovery(ok=True, server="openai", models=_openai(client, base))
    except (OSError, ValueError, urllib.error.URLError) as error:
        return Discovery(ok=False, error=_describe(error))


def diff(provider: Provider, discovery: Discovery) -> list[ModelRow]:
    remote = {model.id: model for model in discovery.models}
    rows = [
        ModelRow(
            id=model_id,
            name=str(entry.get("name") or model_id),
            status="configured" if model_id in remote or not discovery.ok else "missing",
            remote=remote.get(model_id),
            configured_tools=configured_tools(entry),
            configured_vision=configured_vision(entry),
            configured_visible=configured_visible(entry),
            configured_context=configured_context(entry),
        )
        for model_id, entry in provider.models.items()
    ]
    rows += [
        ModelRow(id=model.id, name=model.name or model.id, status="new", remote=model)
        for model in discovery.models
        if model.id not in provider.models
    ]
    order = {"new": 0, "configured": 1, "missing": 2}
    return sorted(rows, key=lambda row: (order[row.status], row.name.lower()))


def apply(config: OpencodeConfig, provider_id: str, add: list[RemoteModel], remove: list[str]) -> None:
    config.add_models(
        provider_id,
        {model.id: config.model_entry(model.name, model.context, model.tools, model.vision) for model in add},
    )
    for model in add:
        if model.vision is not None:
            config.set_model_vision(provider_id, model.id, model.vision, overwrite=False)
    config.remove_models(provider_id, remove)
    config.save()


def sync_candidates(provider: Provider, result: Discovery) -> list[RemoteModel]:
    return [model for model in result.models if model.id not in provider.models or
            model.vision is not None and vision_unset(provider.models[model.id])]


def metadata_vision(item: dict) -> bool | None:
    """Only explicit capability metadata is evidence; names and missing fields are not."""
    capabilities = item.get("capabilities")
    evidence: set[bool] = set()
    sources = [item, capabilities] if isinstance(capabilities, dict) else [item]
    for source in sources:
        for key in ("vision", "supports_vision"):
            if isinstance(source.get(key), bool):
                evidence.add(source[key])
    candidates = [item.get("input_modalities")]
    for key, field in (("modalities", "input"), ("capabilities", "input"), ("architecture", "input_modalities")):
        value = item.get(key)
        if isinstance(value, dict):
            candidates.append(value.get(field))
    for value in candidates:
        if isinstance(value, list) and value and all(isinstance(part, str) for part in value):
            modalities = {part.lower() for part in value}
            if "image" in modalities:
                evidence.add(True)
            elif modalities <= {"text", "audio", "video", "pdf"}:
                evidence.add(False)
    if isinstance(capabilities, list) and "vision" in capabilities:
        evidence.add(True)
    return next(iter(evidence)) if len(evidence) == 1 else None


def scan_local(config: OpencodeConfig, timeout: float = 1.5) -> list[Suggestion]:
    """Local servers that answer on their default port but are not in the config yet."""
    known = {_normalize(provider.base_url) for provider in config.providers() if provider.base_url}
    candidates = [server for server in LOCAL_SERVERS if _normalize(server[2]) not in known]
    with ThreadPoolExecutor(max_workers=len(LOCAL_SERVERS)) as pool:
        found = list(pool.map(lambda server: (server, discover(server[2], timeout=timeout)), candidates))
    return [
        Suggestion(id=sid, name=name, base_url=url, count=len(result.models))
        for (sid, name, url), result in found
        if result.ok
    ]


class _Client:
    def __init__(self, api_key: str | None, timeout: float, *, headers: dict | None = None) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.headers = headers or {}

    def get(self, url: str) -> Any:
        return self._send(urllib.request.Request(url, headers=self._headers()))

    def post(self, url: str, body: dict[str, Any]) -> Any:
        data = json.dumps(body).encode()
        headers = {**self._headers(), "Content-Type": "application/json"}
        return self._send(urllib.request.Request(url, data=data, headers=headers, method="POST"))

    def probe(self, url: str) -> Any | None:
        """Like get, but a missing endpoint is an answer rather than a failure."""
        try:
            return self.get(url)
        except urllib.error.HTTPError as error:
            if error.code in (400, 404, 405):
                return None
            raise
        except ValueError:
            return None

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "opencode-model-sync", **self.headers}
        if self.api_key and not any(key.lower() == "authorization" for key in headers):
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _send(self, request: urllib.request.Request) -> Any:
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def _ollama(client: _Client, root: str) -> list[RemoteModel] | None:
    tags = client.probe(f"{root}/api/tags")
    if not isinstance(tags, dict) or not isinstance(tags.get("models"), list):
        return None
    names = sorted({str(item.get("model") or item.get("name")) for item in tags["models"] if isinstance(item, dict)})

    def show(name: str) -> RemoteModel | None:
        try:
            info = client.post(f"{root}/api/show", {"model": name})
        except (OSError, ValueError, urllib.error.URLError):
            return RemoteModel(id=name)
        capabilities = info.get("capabilities") or []
        if capabilities and "completion" not in capabilities:
            return None
        # Ollama serves a model with its num_ctx parameter; context_length is only the architecture's ceiling.
        configured = re.search(r"^num_ctx\s+(\d+)", str(info.get("parameters") or ""), re.MULTILINE)
        contexts = [int(configured.group(1))] if configured else []
        contexts += [
            value
            for key, value in (info.get("model_info") or {}).items()
            if key.endswith(".context_length") and isinstance(value, int) and value > 0
        ]
        return RemoteModel(
            id=name,
            context=contexts[0] if contexts else None,
            tools=("tools" in capabilities) if capabilities else None,
            vision=("vision" in capabilities) if capabilities else None,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [model for model in pool.map(show, names) if model]


def _lmstudio(client: _Client, root: str) -> list[RemoteModel] | None:
    listing = client.probe(f"{root}/api/v0/models")
    if not isinstance(listing, dict) or not isinstance(listing.get("data"), list):
        return None
    return [
        RemoteModel(
            id=str(item["id"]),
            context=item.get("max_context_length") if isinstance(item.get("max_context_length"), int) else None,
            tools="tool_use" in (item.get("capabilities") or []),
            vision=True if item.get("type") == "vlm" else (metadata_vision(item) if metadata_vision(item) is not None else False),
        )
        for item in listing["data"]
        if isinstance(item, dict) and item.get("id") and item.get("type") in ("llm", "vlm")
    ]


def _openai(client: _Client, base: str) -> list[RemoteModel]:
    listing = client.get(f"{base}/models")
    items = listing.get("data") if isinstance(listing, dict) else None
    if not isinstance(items, list):
        raise ValueError("the server did not return a model list")
    models = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or NON_CHAT.search(str(item["id"])):
            continue
        context = item.get("context_length") or item.get("max_model_len") or item.get("context_window")
        name = item.get("display_name") or item.get("name")
        models.append(
            RemoteModel(
                id=str(item["id"]),
                name=str(name) if name and name != item["id"] else None,
                context=context if isinstance(context, int) else None,
                vision=metadata_vision(item),
            )
        )
    return sorted(models, key=lambda model: model.id.lower())


def _normalize(url: str | None) -> str:
    return re.sub(r"/(v1|api)?/*$", "", (url or "").strip().lower()).replace("localhost", "127.0.0.1")


def _describe(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}: {error.reason}"
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        return str(reason.strerror if isinstance(reason, OSError) and reason.strerror else reason)
    if isinstance(error, TimeoutError):
        return "timed out"
    return str(error) or error.__class__.__name__
