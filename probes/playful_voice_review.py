"""Small same-text auditions. Creates files without playing on the live output."""
import asyncio
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion.providers import Provider, SPEECH_STYLES

SAMPLES = [
    ('tease', '等一下，说谁呆呢？我刚才那叫深思熟虑。好吧，其实在发呆。', 'playful'),
    ('curious', '哎？你说的那个，我还真没见过。快讲讲，后来呢？', 'curious'),
]

async def main():
    folder = ROOT / 'artifacts/voice-review'
    folder.mkdir(parents=True, exist_ok=True)
    provider = Provider()
    rows = []
    try:
        for voice in ['diana', 'bella', 'claire']:
            for label, text, style in SAMPLES:
                started = time.perf_counter()
                row = {'voice': voice, 'text': text, 'style': style}
                try:
                    data, duration = await provider.speech(text, voice, style=style)
                    name = f'audition-{voice}-{label}.wav'
                    (folder / name).write_bytes(data)
                    row.update(file=name, duration=round(duration, 3),
                               ready_ms=round((time.perf_counter()-started)*1000))
                except Exception as exc:
                    row['error'] = str(exc)[:160]
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        await provider.close()
        (folder / 'audition-comparison.json').write_text(json.dumps(
            {'styles': SPEECH_STYLES, 'samples': rows, 'subjective_listening': 'not_verified'},
            ensure_ascii=False, indent=2), encoding='utf8')

if __name__ == '__main__':
    asyncio.run(main())
