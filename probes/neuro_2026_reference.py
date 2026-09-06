import httpx,json,subprocess,imageio_ffmpeg
from pathlib import Path
out=Path('artifacts/neuro-2026');out.mkdir(exist_ok=True)
bv='BV18c8j6rERT'; headers={'User-Agent':'Mozilla/5.0','Referer':f'https://www.bilibili.com/video/{bv}/'}
with httpx.Client(headers=headers,timeout=20) as h:
 d=h.get('https://api.bilibili.com/x/web-interface/view',params={'bvid':bv}).json()['data']; p=d['pages'][1]
 (out/'source.json').write_text(json.dumps({'url':headers['Referer']+'?p=2','title':d['title'],'pubdate':d['pubdate'],'part':p,'interval':[30,60]},ensure_ascii=False,indent=2),encoding='utf8')
 play=h.get('https://api.bilibili.com/x/player/playurl',params={'bvid':bv,'cid':p['cid'],'qn':64,'fnval':1}).json()
 if play.get('code')!=0:raise RuntimeError(play.get('message'))
 url=play['data']['durl'][0]['url']; ff=imageio_ffmpeg.get_ffmpeg_exe()
 cmd=[ff,'-y','-headers','User-Agent: Mozilla/5.0\r\nReferer: https://www.bilibili.com/\r\n','-ss','30','-i',url,'-t','30','-an','-vf','scale=960:-2','-c:v','libx264','-threads','2','-preset','fast',str(out/'reference.mp4')]
 r=subprocess.run(cmd,capture_output=True,timeout=90)
 print(json.dumps({'title':d['title'],'part':p['part'],'returncode':r.returncode,'bytes':(out/'reference.mp4').stat().st_size if (out/'reference.mp4').exists() else 0},ensure_ascii=False))
 if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace')[-500:])
 subprocess.run([ff,'-y','-i',str(out/'reference.mp4'),'-vf','fps=1,scale=320:-2,tile=5x6','-frames:v','1',str(out/'contact.png')],capture_output=True,check=True)
