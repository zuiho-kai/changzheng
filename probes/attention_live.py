import asyncio,json,subprocess,imageio_ffmpeg,time,math
from pathlib import Path
from playwright.async_api import async_playwright
OUT=Path('artifacts/attention-review')
async def main():
 report={'source':'Actual /stage observer; one page-local synthetic chat update, no server message or audio injection','errors':[]}
 added=False
 async with async_playwright() as p:
  b=await p.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  ctx=await b.new_context(viewport={'width':1280,'height':720},record_video_dir=str(OUT/'raw'),record_video_size={'width':1280,'height':720})
  await ctx.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C});const f=C.prototype.update;C.prototype.update=function(t,m){window.performer=this;const v=f.call(this,t,m);if(!window.samples)window.samples=[];window.samples.push({t,gaze:v.ParamEyeBallX,head:v.ParamAngleZ,body:v.ParamBodyAngleZ,mouth:m,action:this.action?.name,notice:this.noticeAt,offset:this.offset.y});return v;};}});''')
  page=await ctx.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
  async def status(route):
   response=await route.fetch();data=await response.json()
   if added:data['messages']=(data.get('messages',[])+[{'user':'动作联调','text':'这是一条仅用于此录像的视线反应样本','event_id':'attention-local-sample'}])[-5:]
   await route.fulfill(response=response,json=data)
  await page.route('**/api/live/status',status)
  await page.goto('http://127.0.0.1:17870/stage')
  body=page.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]');await body.wait_for(timeout=60000)
  await asyncio.sleep(10);added=True
  await asyncio.sleep(2)
  await page.screenshot(path=str(OUT/'notice-live.png'))
  await asyncio.sleep(14)
  rows=await body.evaluate('()=>window.samples')
  report['frames']=len(rows);report['duration_s']=(rows[-1]['t']-rows[0]['t'])/1000
  report['average_fps']=round(len(rows)/report['duration_s'],1)
  report['gaze_range']=[min(r['gaze'] for r in rows),max(r['gaze'] for r in rows)]
  report['real_notice_path']=any(r['notice'] is not None and math.isfinite(r['notice']) for r in rows)
  report['closed_mouth']=all(r['mouth']==0 for r in rows)
  report['model_parameters']=await body.evaluate('()=>Array.from(performer.core._model.parameters.ids)')
  (OUT/'live-check.json').write_text(json.dumps(report,indent=2),encoding='utf8')
  (OUT/'live-samples.json').write_text(json.dumps(rows),encoding='utf8')
  await ctx.close();await page.video.save_as(str(OUT/'live.webm'));await b.close()
 print(json.dumps(report))
 ff=imageio_ffmpeg.get_ffmpeg_exe()
 subprocess.run([ff,'-y','-i',str(OUT/'live.webm'),'-an','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','21',str(OUT/'live.mp4')],capture_output=True,check=True)
 subprocess.run([ff,'-y','-i',str(OUT/'live.mp4'),'-vf','fps=2,scale=320:180,tile=5x6','-frames:v','1',str(OUT/'live-contact.png')],capture_output=True,check=True)
 assert not report['errors'] and report['real_notice_path'] and report['closed_mouth'] and report['gaze_range'][1]>.7 and 'ParamEyeBallX' in report['model_parameters']
asyncio.run(main())
