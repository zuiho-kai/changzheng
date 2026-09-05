import io
import json
import wave

import httpx

from .secrets import get_key
from .local_speech import LocalSpeech

BASE = 'https://api.siliconflow.cn/v1'
FAST_MODEL = 'Qwen/Qwen3.5-35B-A3B'
TTS_MODEL = 'FunAudioLLM/CosyVoice2-0.5B'


class Provider:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), limits=httpx.Limits(max_connections=8))
        self.local_speech = LocalSpeech()

    def headers(self):
        key = get_key()
        if not key:
            raise RuntimeError('请先在设置中填写硅基流动 API Key')
        return {'Authorization': 'Bearer ' + key}

    async def check(self, response):
        if response.is_success:
            return
        await response.aread()
        detail = response.text[:200].replace(get_key() or '\0', '[已隐藏]')
        raise RuntimeError(f'模型服务返回 {response.status_code}：{detail}')

    async def chat(self, messages, model=FAST_MODEL, tools=None):
        body = {'model': model, 'messages': messages, 'enable_thinking': False, 'stream': True, 'max_tokens': 180}
        if tools:
            body['tools'] = tools
        async with self.client.stream('POST', BASE + '/chat/completions', headers=self.headers(), json=body) as response:
            await self.check(response)
            async for line in response.aiter_lines():
                if not line.startswith('data: '):
                    continue
                payload = line[6:]
                if payload == '[DONE]':
                    break
                item = json.loads(payload)
                if item.get('error'):
                    raise RuntimeError('模型流返回错误，请稍后重试')
                for choice in item.get('choices', []):
                    yield choice.get('delta', {})

    async def json_reply(self, messages, model=FAST_MODEL):
        response = await self.client.post(BASE + '/chat/completions', headers=self.headers(), json={
            'model': model, 'messages': messages, 'enable_thinking': False,
            'response_format': {'type': 'json_object'}, 'max_tokens': 700, 'temperature': 0})
        await self.check(response)
        return json.loads(response.json()['choices'][0]['message']['content'])

    async def speech(self, text, voice='claire'):
        if voice.startswith('local:'):
            return await self.local_speech.speech(text, voice[6:])
        response = await self.client.post(BASE + '/audio/speech', headers=self.headers(), json={
            'model': TTS_MODEL, 'voice': f'{TTS_MODEL}:{voice}', 'input': text,
            'response_format': 'wav', 'sample_rate': 24000, 'stream': False})
        await self.check(response)
        with wave.open(io.BytesIO(response.content), 'rb') as wav:
            rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
            pcm = wav.readframes(wav.getnframes())
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(width)
            wav.setframerate(rate)
            wav.writeframes(pcm)
        return out.getvalue(), len(pcm) / (rate * channels * width)

    async def transcribe(self, audio):
        response = await self.client.post(BASE + '/audio/transcriptions', headers=self.headers(),
            data={'model': 'FunAudioLLM/SenseVoiceSmall'}, files={'file': ('speech.wav', audio, 'audio/wav')})
        await self.check(response)
        return response.json().get('text', '').strip()

    async def embed(self, texts):
        response = await self.client.post(BASE + '/embeddings', headers=self.headers(), json={
            'model': 'Qwen/Qwen3-Embedding-0.6B', 'input': texts, 'encoding_format': 'float'})
        await self.check(response)
        return [item['embedding'] for item in sorted(response.json()['data'], key=lambda x:x['index'])]

    async def close(self):
        await self.local_speech.close()
        await self.client.aclose()
