import asyncio,audioop,io,json,sys,wave
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from companion.providers import Provider
async def main():
 p=Provider();rows=[]
 try:
  for name in ['audition-diana-tease.wav','audition-diana-curious.wav','audition-bella-tease.wav','audition-claire-tease.wav']:
   with wave.open(str(Path('artifacts/voice-review')/name),'rb') as w: rate=w.getframerate();ch=w.getnchannels();width=w.getsampwidth();raw=w.readframes(w.getnframes())
   pcm=audioop.ratecv(raw,width,ch,rate,8000,None)[0];out=io.BytesIO()
   with wave.open(out,'wb') as w:w.setnchannels(ch);w.setsampwidth(width);w.setframerate(8000);w.writeframes(pcm)
   try:
    async with asyncio.timeout(15): row={'file':name,'asr_input_rate':8000,'asr':await p.transcribe(out.getvalue())}
   except Exception as e:row={'file':name,'error':type(e).__name__}
   print(json.dumps(row,ensure_ascii=False),flush=True);rows.append(row)
 finally:
  await p.close();Path('artifacts/voice-review/asr-low-bandwidth-audit.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
asyncio.run(main())
