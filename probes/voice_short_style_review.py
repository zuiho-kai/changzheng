import asyncio,io,json,sys,time,wave
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from companion.providers import Provider,BASE,TTS_MODEL
async def main():
 p=Provider(); rows=[]
 try:
  for label,style in [('simple','用年轻明亮的少女音，调皮轻快地说话。'),('happy','用开心的情感说话。'),('none','')]:
   text='等一下，说谁呆呢？'
   start=time.perf_counter()
   r=await p.client.post(BASE+'/audio/speech',headers=p.headers(),json={'model':TTS_MODEL,'voice':TTS_MODEL+':diana','input':(style+'<|endofprompt|>' if style else '')+text,'response_format':'wav','sample_rate':24000,'stream':False,'speed':1.07})
   await p.check(r)
   with wave.open(io.BytesIO(r.content),'rb') as wav: params=wav.getparams();pcm=wav.readframes(wav.getnframes())
   name=f'short-style-{label}.wav'
   with wave.open(str(Path('artifacts/voice-review')/name),'wb') as wav: wav.setparams(params);wav.writeframes(pcm)
   row={'style':style,'file':name,'duration':len(pcm)/(params.framerate*params.nchannels*params.sampwidth),'ready_ms':round((time.perf_counter()-start)*1000)};rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
 finally:
  await p.close();Path('artifacts/voice-review/short-style-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
asyncio.run(main())
