"""Capability evidence, non-destructive config updates, and real HTTP/image probe contracts."""
import base64
import copy
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from opencode_model_sync import discovery, vision
from opencode_model_sync.config import ConfigError, OpencodeConfig, configured_vision
from opencode_model_sync.discovery import RemoteModel


@pytest.mark.parametrize("metadata,expected", [
    ({"id": "iq3_s", "owned_by": "strata", "meta": {"label": "Qwen3.8", "aliases": [], "gpus": [0]}}, None),
    ({"id": "vision-vlm-image-model"}, None),
    ({"capabilities": ["tools"]}, None),
    ({"capabilities": ["vision", "tools"]}, True),
    ({"capabilities": {"input": ["text", "image"]}}, True),
    ({"modalities": {"input": ["text", "audio"]}}, False),
    ({"architecture": {"input_modalities": ["image", "text"]}}, True),
    ({"input_modalities": ["text"]}, False),
    ({"input_modalities": []}, None),
    ({"input_modalities": ["TEXT", "IMAGE"]}, True),
    ({"input_modalities": ["undocumented"]}, None),
    ({"vision": False, "input_modalities": ["text", "image"]}, None),
    ({"input_modalities": "image"}, None),
    ({"vision": "false"}, None),
    ({"supports_vision": False}, False),
])
def test_metadata_is_evidence_not_a_name_guess(metadata, expected):
    assert discovery.metadata_vision(metadata) is expected


def test_native_ollama_and_lmstudio_capabilities(monkeypatch):
    class Client:
        def probe(self, url):
            if url.endswith('/api/tags'):
                return {"models": [{"model": "vlm"}, {"model": "unknown"}]}
            return {"data": [{"id": "vlm", "type": "vlm"}, {"id": "llm", "type": "llm"}]}
        def post(self, url, body):
            return {"capabilities": ["completion", "vision"]} if body['model'] == 'vlm' else {}
    assert {item.id: item.vision for item in discovery._ollama(Client(), 'http://host')} == {'vlm': True, 'unknown': None}
    assert {item.id: item.vision for item in discovery._lmstudio(Client(), 'http://host')} == {'vlm': True, 'llm': False}


def test_manual_vision_keeps_modality_tools_and_overrides(tmp_path):
    model = {"capabilities": {"input": ["text", "audio", "pdf"], "output": ["audio"], "tools": False},
             "limit": {"context": 65536, "output": 8192}, "settings": {"temperature": .4},
             "variants": [{"id": "custom", "settings": {"reasoningEffort": "high"}}]}
    data = {"providers": {"p": {"models": {"m": model}, "settings": {"apiKey": "secret"}}}, "username": "keep"}
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps(data))
    config = OpencodeConfig.load(path)
    config.set_model_vision('p', 'm', True)
    config.save()

    saved = json.loads(path.read_text())
    assert saved['username'] == 'keep'
    entry = saved['providers']['p']['models']['m']
    assert entry['capabilities']['input'] == ['text', 'audio', 'pdf', 'image'], "image joins, the chosen modalities stay"
    assert entry['capabilities']['output'] == ['audio'] and entry['capabilities']['tools'] is False
    assert entry['limit'] == {"context": 65536, "output": 8192}
    assert entry['settings'] == {"temperature": .4}
    assert entry['variants'] == [{'id': 'custom', 'settings': {'reasoningEffort': 'high'}}]
    assert saved['providers']['p']['settings'] == {'apiKey': 'secret'}

    before_second_write = path.read_text()
    config = OpencodeConfig.load(path)
    config.set_model_vision('p', 'm', False)
    config.save()
    again = json.loads(path.read_text())['providers']['p']['models']['m']
    assert again['capabilities'] == {'input': ['text', 'audio', 'pdf'], 'output': ['audio'], 'tools': False}, \
        "off again, and the entry the move produced is left exactly as it is otherwise"
    # A write backs up the file as it stood for it, not the one it has long since replaced.
    backup, = tmp_path.glob('*.bak-model-sync-*')
    assert backup.read_text() == before_second_write


def test_sync_enriches_existing_models_without_overriding_explicit_input(tmp_path):
    original = {'name': 'Keep', 'limit': {'context': 123, 'output': 45}, 'capabilities': {'output': ['audio'], 'tools': False}}
    explicit = {'capabilities': {'input': ['text'], 'output': ['text']}}
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'p': {'models': {'existing': original, 'manual': explicit, 'unknown': {}}}}}))
    models = [RemoteModel('existing', context=999, tools=True, vision=True), RemoteModel('manual', vision=True),
              RemoteModel('new', vision=True), RemoteModel('unknown')]
    config = OpencodeConfig.load(path)
    candidates = discovery.sync_candidates(config.provider('p'), discovery.Discovery(True, models=models))
    assert [model.id for model in candidates] == ['existing', 'new']
    discovery.apply(config, 'p', models, [])
    saved = OpencodeConfig.load(path)
    assert set(saved.data) == {'providers'}
    existing = saved.provider('p').models['existing']
    assert existing == {'name': 'Keep', 'limit': {'context': 123, 'output': 45},
                        'capabilities': {'output': ['audio'], 'tools': False, 'input': ['text', 'image']}}
    assert saved.provider('p').models['manual'] == {'capabilities': {'input': ['text'], 'output': ['text']}}, \
        "an explicit choice is not enriched"
    assert saved.provider('p').models['unknown'] == {}
    assert saved.provider('p').models['new']['capabilities'] == {'input': ['text', 'image'], 'output': ['text']}
    assert discovery.sync_candidates(saved.provider('p'), discovery.Discovery(True, models=models)) == []
    assert configured_vision(explicit) is False


def test_malformed_explicit_modalities_are_not_overwritten(tmp_path):
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'p': {'models': {'m': {'capabilities': {'input': 'custom'}}}}}}))
    config = OpencodeConfig.load(path)
    assert not config.set_model_vision('p', 'm', True, overwrite=False)
    with pytest.raises(ConfigError):
        config.set_model_vision('p', 'm', True)


def read_image_answer(body):
    content = body['messages'][0]['content']
    assert content[0]['text'] == vision.PROMPT
    encoded = content[1]['image_url']['url']
    assert encoded.startswith('data:image/png;base64,')
    image = Image.open(io.BytesIO(base64.b64decode(encoded.split(',')[1]))).convert('RGB')
    assert image.size == (256, 256)
    names = {rgb: name for name, rgb in vision.COLORS.items()}
    answer = []
    for cx, cy in [(64, 64), (192, 64), (64, 192), (192, 192)]:
        rgb = image.getpixel((cx, cy))
        shape = ('square' if image.getpixel((cx + 35, cy - 35)) == rgb else
                 'circle' if image.getpixel((cx + 20, cy - 20)) == rgb else 'triangle')
        answer.append(names[rgb] + ' ' + shape)
    return answer


@pytest.fixture
def image_server():
    state = {'requests': [], 'mode': 'vision'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append((self.path, body, self.headers.get('Authorization')))
            answer = read_image_answer(body)
            status = 422 if state['mode'] == 'unsupported' else 200
            if state['mode'] == 'blind' or state['mode'] == 'second-wrong' and len(state['requests']) == 2:
                answer = ['cannot see the image']
            data = json.dumps({'choices': [{'message': {'content': json.dumps(answer)}}]}).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}/v1', state
    server.shutdown()
    server.server_close()
    thread.join()


def test_probe_checks_actual_pixels_twice_and_uses_auth(image_server):
    url, state = image_server
    assert vision.probe(url, 'iq3_s', 'test-key').supported is True
    assert len(state['requests']) == 2
    for path, body, auth in state['requests']:
        assert path == '/v1/chat/completions' and body['model'] == 'iq3_s'
        assert auth == 'Bearer test-key'
        assert body['stream'] is False and body['max_tokens'] == 192


@pytest.mark.parametrize('mode', ['blind', 'second-wrong', 'unsupported'])
def test_200_or_partial_success_does_not_prove_vision(image_server, mode):
    url, state = image_server
    state['mode'] = mode
    assert vision.probe(url, 'iq3_s').supported is None


def test_network_failures_remain_unknown(monkeypatch):
    def fail(*args, **kwargs): raise TimeoutError('timed out')
    monkeypatch.setattr(discovery._Client, 'post', fail)
    assert vision.probe('http://server/v1', 'm').supported is None


@pytest.mark.parametrize('payload', [{}, {'choices': []}, {'choices': [{'message': {'content': None}}]}])
def test_malformed_responses_remain_unknown(monkeypatch, payload):
    monkeypatch.setattr(discovery._Client, 'post', lambda *a, **kw: payload)
    assert vision.probe('http://server/v1', 'm').supported is None


def test_test_images_match_expected_labels(monkeypatch):
    class Samples:
        offset = 0
        def sample(self, values, count):
            result = [values[(self.offset + index) % len(values)] for index in range(count)]
            self.offset += count
            return result
    samples = Samples()
    monkeypatch.setattr(vision.secrets, 'SystemRandom', lambda: samples)
    for _ in range(5):
        item = vision.challenge()
        body = {'messages': [{'content': [{'text': vision.PROMPT},
                {'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(item.png).decode()}}]}]}
        assert tuple(read_image_answer(body)) == item.answer
        assert vision.matches('```json\n' + json.dumps(item.answer) + '\n```', item.answer)
        assert not vision.matches('I think ' + json.dumps(item.answer), item.answer)


def test_probe_merges_unrelated_edits_into_the_entry_it_writes(tmp_path, monkeypatch):
    path = tmp_path / 'opencode.json'
    original = {'providers': {'strata-pc': {'settings': {'baseURL': 'http://server/v1', 'apiKey': 'key'},
        'models': {'alias': {'modelID': 'iq3_s', 'capabilities': {'input': ['text', 'audio'], 'output': ['text']},
                             'limit': {'context': 123}, 'settings': {'temperature': 0.2}}}}}}
    path.write_text(json.dumps(original))
    def probe(url, model, api_key, **kwargs):
        # The alias is only a key: the probe runs under the model opencode would actually call.
        assert (url, model, api_key) == ('http://server/v1', 'iq3_s', 'key')
        changed = json.loads(path.read_text())
        changed['username'] = 'external'
        changed['providers']['strata-pc']['models']['sibling'] = {'name': 'Added externally'}
        path.write_text(json.dumps(changed))
        return vision.ProbeResult(True)
    monkeypatch.setattr(vision, 'probe', probe)
    assert vision.probe_and_enable(path, 'strata-pc', 'alias').supported is True
    # The probe result applies to the file as it is now, not as it was: the external edits survive,
    # and the entry gains image input next to the settings its owner wrote.
    merged = copy.deepcopy(original['providers']['strata-pc'])
    merged['models']['sibling'] = {'name': 'Added externally'}
    merged['models']['alias']['capabilities']['input'].append('image')
    assert json.loads(path.read_text()) == {'username': 'external', 'providers': {'strata-pc': merged}}
    assert list(tmp_path.glob('*.bak-model-sync-*'))


@pytest.mark.parametrize('conflict', [False, True])
def test_unknown_or_conflict_never_writes(tmp_path, monkeypatch, conflict):
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'p': {'settings': {'baseURL': 'http://server/v1'},
                                                    'models': {'m': {'capabilities': {'input': ['text']}}}}}}))
    before = path.read_text()
    def probe(*args, **kwargs):
        if conflict:
            changed = json.loads(before)
            changed['providers']['p']['models']['m']['name'] = 'external change'
            path.write_text(json.dumps(changed))
        return vision.ProbeResult(True if conflict else None)
    monkeypatch.setattr(vision, 'probe', probe)
    if conflict:
        with pytest.raises(ConfigError): vision.probe_and_enable(path, 'p', 'm')
        assert json.loads(path.read_text())['providers']['p']['models']['m']['name'] == 'external change'
    else:
        assert vision.probe_and_enable(path, 'p', 'm').supported is None
        assert path.read_text() == before
    assert not list(tmp_path.glob('*.bak-model-sync-*'))


def test_jsonc_is_refused_before_generation(tmp_path, monkeypatch):
    path = tmp_path / 'opencode.jsonc'
    original = '{/* keep comments */ "providers": {"p": {"models": {"m": {}}}}}'
    path.write_text(original)
    monkeypatch.setattr(vision, 'probe', lambda *a, **kw: pytest.fail('must not generate for unsavable config'))
    with pytest.raises(ConfigError): vision.probe_and_enable(path, 'p', 'm')
    assert path.read_text() == original


def test_strata_listing_without_vision_stays_unknown_and_never_generates(monkeypatch):
    monkeypatch.setattr(discovery._Client, 'probe', lambda *a: None)
    monkeypatch.setattr(discovery._Client, 'get', lambda *a: {'data': [
        {'id': 'iq3_s', 'owned_by': 'strata', 'meta': {'label': 'Qwen3.8-Flash-Next IQ3_S', 'gpus': [0]}}]})
    monkeypatch.setattr(discovery._Client, 'post', lambda *a: pytest.fail('listing must not generate'))
    result = discovery.discover('http://strata/v1')
    assert result.ok
    assert result.models[0].id == 'iq3_s' and result.models[0].vision is None


def test_real_probe_enables_strata_style_existing_model(image_server, tmp_path):
    url, state = image_server
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'strata-pc': {'settings': {'baseURL': url}, 'models': {'iq3_s': {
        'name': 'Qwen3.8-Flash-Next IQ3_S', 'limit': {'context': 64000, 'output': 8000}}}}}}))
    before = path.read_text()
    assert vision.probe_and_enable(path, 'strata-pc', 'iq3_s').supported is True
    saved = json.loads(path.read_text())['providers']['strata-pc']['models']['iq3_s']
    assert saved['capabilities']['input'] == ['text', 'image']
    assert saved['limit'] == {'context': 64000, 'output': 8000}
    assert len(state['requests']) == 2
    backup, = tmp_path.glob('*.bak-model-sync-*')
    assert backup.read_text() == before


def test_probe_can_add_a_new_selected_model(tmp_path, monkeypatch):
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'p': {'settings': {'baseURL': 'http://server/v1'}, 'models': {}}}}))
    monkeypatch.setattr(vision, 'probe', lambda *a, **kw: vision.ProbeResult(True))
    result = vision.probe_and_enable(path, 'p', 'new', RemoteModel('new', context=8192, tools=True))
    assert result.supported is True
    model = json.loads(path.read_text())['providers']['p']['models']['new']
    assert model['capabilities']['input'] == ['text', 'image']
    assert model['capabilities']['tools'] is True and model['limit']['context'] == 8192


def test_failed_probe_preserves_enabled_vision(tmp_path, monkeypatch):
    path = tmp_path / 'opencode.json'
    path.write_text(json.dumps({'providers': {'p': {'settings': {'baseURL': 'http://server/v1'}, 'models': {
        'm': {'capabilities': {'input': ['text', 'image'], 'output': ['text']}}}}}}))
    before = path.read_bytes()
    monkeypatch.setattr(vision, 'probe', lambda *a, **kw: vision.ProbeResult(None, 'timed out'))
    vision.probe_and_enable(path, 'p', 'm')
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('*.bak-model-sync-*'))


def test_model_endpoint_and_custom_auth_overrides_are_used(tmp_path, monkeypatch):
    monkeypatch.setenv('VISION_TEST_KEY', 'example-key')
    path = tmp_path / 'opencode.json'
    data = {'providers': {'p': {'settings': {'baseURL': 'http://default/v1', 'apiKey': 'fallback'},
                                'headers': {'X-Provider': 'keep'},
        'models': {'alias': {'modelID': 'actual-model',
                             'settings': {'baseURL': 'http://override/v1',
                                          'headers': {'Authorization': 'Bearer {env:VISION_TEST_KEY}'}},
                             'headers': {'X-Model': 'keep'}}}}}}
    path.write_text(json.dumps(data))
    def probe(url, model, key, *, headers):
        assert (url, model, key) == ('http://override/v1', 'actual-model', 'fallback')
        assert headers == {'X-Provider': 'keep', 'Authorization': 'Bearer example-key', 'X-Model': 'keep'}
        assert discovery._Client(key, 1, headers=headers)._headers()['Authorization'] == 'Bearer example-key'
        return vision.ProbeResult(True)
    monkeypatch.setattr(vision, 'probe', probe)
    vision.probe_and_enable(path, 'p', 'alias')
    # The probe already saw the overridden endpoint, key and headers; what is left to prove is that
    # enabling vision changed nothing of them, since a lost override means another server.
    provider = json.loads(path.read_text())['providers']['p']
    assert provider['settings'] == {'baseURL': 'http://default/v1', 'apiKey': 'fallback'}
    assert provider['headers'] == {'X-Provider': 'keep'}
    alias = provider['models']['alias']
    assert alias['modelID'] == 'actual-model'
    assert alias['settings']['baseURL'] == 'http://override/v1'
    assert alias['settings']['headers'] == {'Authorization': 'Bearer {env:VISION_TEST_KEY}'}
    assert alias['headers'] == {'X-Model': 'keep'}
    assert alias['capabilities']['input'] == ['text', 'image']
