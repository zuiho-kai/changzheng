import asyncio
import json
from types import SimpleNamespace

import companion.app as app_module


def prepare(monkeypatch, tmp_path, *, scene='live', age=0):
    path = tmp_path/'artifacts/runtime-bilibili'
    path.mkdir(parents=True)
    (path/'status.json').write_text(json.dumps({
        'updated_at':100-age, 'state':'connected', 'room_id':837764,
        'received':1, 'forwarded':1,
        'messages':[{'user':'观众','text':'你好','event_id':'one'}],
    }), encoding='utf8')
    monkeypatch.setattr(app_module, 'ROOT', tmp_path)
    monkeypatch.setattr(app_module.time, 'time', lambda:100)
    monkeypatch.setattr(app_module, 'runtime', SimpleNamespace(
        controller_present=False, player_audio_state='uninitialized',
        scene=scene, status='idle', settings=lambda:{'audio_enabled':True}))


def test_receiving_chat_does_not_claim_audio_player_is_ready(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path)
    result = asyncio.run(app_module.live_status())
    assert result['connected'] and result['messages'][0]['text'] == '你好'
    assert not result['player_connected'] and result['audio_state'] == 'uninitialized'


def test_stale_receiver_file_is_not_online(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path, age=6)
    assert not asyncio.run(app_module.live_status())['connected']


def test_private_scene_has_no_public_chat_list(monkeypatch, tmp_path):
    prepare(monkeypatch, tmp_path, scene='chat')
    assert asyncio.run(app_module.live_status())['messages'] == []
