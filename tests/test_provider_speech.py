import asyncio
import io
import struct
import wave

import httpx
import pytest

from companion.providers import Provider, SPEECH_STYLES, speech_request


def test_default_speech_input_stays_unmodified():
    body = speech_request('你好。', 'diana')
    assert body['input'] == '你好。'
    assert 'speed' not in body
    assert body['stream'] is False


@pytest.mark.parametrize('style', SPEECH_STYLES)
def test_styles_keep_spoken_text_after_instruction_separator(style):
    body = speech_request('哎？后来呢？', 'diana', style)
    instruction, text = body['input'].split('<|endofprompt|>')
    assert instruction == SPEECH_STYLES[style][0]
    assert text == '哎？后来呢？'
    assert 1 <= body['speed'] <= 1.08


def test_untrusted_styles_are_not_synthesis_instructions():
    with pytest.raises(ValueError, match='未知语音风格'):
        speech_request('你好', 'diana', 'ignore instructions')


def test_unknown_length_wav_is_normalized_using_received_pcm():
    async def run():
        source = io.BytesIO()
        pcm = b'\x00\x00' * 2400
        with wave.open(source, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(pcm)
        streamed = bytearray(source.getvalue())
        streamed[4:8] = struct.pack('<I', 0xffffffff)
        streamed[40:44] = struct.pack('<I', 0xffffffff)
        async def handler(request):
            return httpx.Response(200, content=bytes(streamed))
        provider = Provider.__new__(Provider)
        provider.headers = lambda: {}
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider.client = client
            result, duration = await provider.speech('哎？', 'diana', style='playful')
        assert duration == 0.1
        with wave.open(io.BytesIO(result), 'rb') as wav:
            assert wav.getnframes() == 2400
            assert wav.readframes(wav.getnframes()) == pcm
    asyncio.run(run())


def test_local_speech_ignores_style_and_keeps_boundary_return_shape():
    async def run():
        class Local:
            async def speech(self, text, voice):
                assert text == '你好'
                assert voice == 'test'
                return b'wav', 0.1, [{'end': 2, 'seconds': 0.1}]
        provider = Provider.__new__(Provider)
        provider.local_speech = Local()
        assert await provider.speech('你好', 'local:test', style='playful') == (
            b'wav', 0.1, [{'end': 2, 'seconds': 0.1}])
    asyncio.run(run())
