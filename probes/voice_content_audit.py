"""Content verification only: ASR is not a substitute for listening to voice quality."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from companion.providers import Provider

async def main():
    folder=Path(__file__).resolve().parents[1]/'artifacts/voice-review'
    provider=Provider()
    names=['audition-diana-tease.wav','audition-diana-curious.wav','audition-bella-tease.wav','audition-claire-tease.wav','short-style-simple.wav']
    async def one(name):
        try:
            async with asyncio.timeout(20):
                text=await provider.transcribe((folder/name).read_bytes())
            row={'file':name,'asr':text}
        except Exception as exc:
            row={'file':name,'error':type(exc).__name__+': '+str(exc)[:160]}
        print(json.dumps(row,ensure_ascii=False),flush=True)
        return row
    try:
        rows=await asyncio.gather(*(one(name) for name in names))
        (folder/'asr-short-prompt-audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    finally:
        await provider.close()

if __name__=='__main__':
    asyncio.run(main())
