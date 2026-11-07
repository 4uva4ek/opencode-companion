import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from opencode_model_sync.config import Provider
from opencode_model_sync.discovery import Discovery, RemoteModel, diff, discover


class Server:
    """A local HTTP server that answers fixed JSON per path, like Ollama or an OpenAI-compatible API."""

    def __init__(self, routes: dict[str, object], require_key: str | None = None) -> None:
        routes_ref = routes

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self):
                if require_key and self.headers.get("Authorization") != f"Bearer {require_key}":
                    self.send_response(401)
                    self.end_headers()
                    return
                key = self.path
                if self.command == "POST":
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    key = f"{self.path}:{body.get('model')}"
                if key not in routes_ref:
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = json.dumps(routes_ref[key]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = _reply
            do_POST = _reply

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()


@pytest.fixture
def server():
    created = []

    def make(routes, require_key=None):
        instance = Server(routes, require_key)
        created.append(instance)
        return instance

    yield make
    for instance in created:
        instance.close()


def test_ollama_uses_native_api_and_skips_embeddings(server):
    srv = server(
        {
            "/api/tags": {"models": [{"model": "coder:30b"}, {"model": "nomic-embed:latest"}, {"model": "old:1b"}]},
            "/api/show:coder:30b": {
                "capabilities": ["completion", "tools"],
                "parameters": "num_ctx                        65536\ntemperature 0.7",
                "model_info": {"qwen3.context_length": 262144},
            },
            "/api/show:nomic-embed:latest": {"capabilities": ["embedding"]},
            "/api/show:old:1b": {"capabilities": ["completion"], "model_info": {"llama.context_length": 8192}},
        }
    )
    result = discover(f"{srv.url}/v1")
    assert result.ok and result.server == "ollama"
    assert result.models == [
        RemoteModel(id="coder:30b", context=65536, tools=True, vision=False),
        RemoteModel(id="old:1b", context=8192, tools=False, vision=False),
    ]


def test_openai_compatible_listing_with_key(server):
    srv = server(
        {
            "/v1/models": {
                "data": [
                    {"id": "big-model", "name": "Big Model", "context_length": 131072},
                    {"id": "text-embedding-3-small"},
                    {"id": "plain"},
                ]
            }
        },
        require_key="k",
    )
    result = discover(f"{srv.url}/v1", api_key="k")
    assert result.ok and result.server == "openai"
    assert result.models == [RemoteModel(id="big-model", name="Big Model", context=131072), RemoteModel(id="plain")]
    assert discover(f"{srv.url}/v1", api_key="wrong").error == "HTTP 401: Unauthorized"


def test_lmstudio_native_listing(server):
    srv = server(
        {
            "/api/v0/models": {
                "data": [
                    {"id": "qwen", "type": "llm", "max_context_length": 32768, "capabilities": ["tool_use"]},
                    {"id": "embed", "type": "embeddings"},
                ]
            }
        }
    )
    result = discover(f"{srv.url}/v1")
    assert result.server == "lmstudio"
    assert result.models == [RemoteModel(id="qwen", context=32768, tools=True, vision=False)]


def test_unreachable_server_reports_error():
    result = discover("http://127.0.0.1:9/v1", timeout=1)
    assert not result.ok and result.error


def test_diff_marks_new_configured_and_missing():
    provider = Provider("p", "P", "http://h/v1", None, {"kept": {"name": "Kept"}, "gone": {}})
    rows = diff(provider, Discovery(ok=True, models=[RemoteModel(id="kept"), RemoteModel(id="fresh")]))
    assert [(row.id, row.status) for row in rows] == [("fresh", "new"), ("kept", "configured"), ("gone", "missing")]


def test_diff_does_not_call_models_missing_when_server_is_down():
    provider = Provider("p", "P", "http://h/v1", None, {"kept": {}})
    rows = diff(provider, Discovery(ok=False, error="down"))
    assert [(row.id, row.status) for row in rows] == [("kept", "configured")]


def test_config_tool_choice_wins_over_server():
    provider = Provider("p", "P", "http://h/v1", None, {"m": {"capabilities": {"tools": False}}})
    [row] = diff(provider, Discovery(ok=True, models=[RemoteModel(id="m", tools=True)]))
    assert row.in_config and row.tools is False


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_native_endpoint_failure_does_not_hide_openai_models(server, monkeypatch, status):
    import urllib.error
    from opencode_model_sync.discovery import _Client

    srv = server({"/v1/models": {"data": [{"id": "strata-model"}]}})
    original = _Client.get

    def get(self, url):
        if "/api/" in url:
            raise urllib.error.HTTPError(url, status, "native endpoint unavailable", {}, None)
        return original(self, url)

    monkeypatch.setattr(_Client, "get", get)
    result = discover(f"{srv.url}/v1")
    assert result.ok
    assert [model.id for model in result.models] == ["strata-model"]
