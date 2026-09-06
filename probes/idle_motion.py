import asyncio,json,math
from pathlib import Path
from playwright.async_api import async_playwright
ROOT=Path(__file__).resolve().parents[1]
async def main():
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  context=await browser.new_context(viewport={'width':1280,'height':720},record_video_dir=str(ROOT/'artifacts/runtime-idle-video'),record_video_size={'width':1280,'height':720})
  await context.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C,writable:true,configurable:true});const update=C.prototype.update;C.prototype.update=function(t,m){const values=update.call(this,t,m);if(!window.motionSamples)window.motionSamples=[];if(!this.probeAt||t-this.probeAt>100){this.probeAt=t;const a=this.core._model.drawables.vertexPositions[9];let x=0,y=0;for(let i=0;i<a.length;i+=2){x+=a[i];y+=a[i+1]}window.motionSamples.push({t,values,mouthX:x/(a.length/2),mouthY:y/(a.length/2)});}return values;};}});''')
  page=await context.new_page();await page.goto('http://127.0.0.1:17870/stage')
  model=page.frame_locator('#avatar').frame_locator('#live2d-frame')
  await model.locator('body[data-ready=true]').wait_for(timeout=60000)
  for i in range(6):
   await page.wait_for_timeout(3000)
   await page.screenshot(path=str(ROOT/f'artifacts/idle-room-{i}.png'))
  rows=await model.locator('body').evaluate('()=>window.motionSamples.slice(10)')
  span=lambda key:max(r['values'][key] for r in rows)-min(r['values'][key] for r in rows)
  report={'sample_count':len(rows),'duration_seconds':round((rows[-1]['t']-rows[0]['t'])/1000,2),'parameter_ranges':{k:round(span(k),3) for k in ['ParamAngleY','ParamAngleZ','ParamBodyAngleZ','ParamHairSway']},'face_motion_model_units':{k:round(max(r[k] for r in rows)-min(r[k] for r in rows),4) for k in ['mouthX','mouthY']},'checks':{'idle_mouth_closed':all(r['values']['ParamMouthOpenY']==0 for r in rows),'yaw_stays_zero':all(r['values']['ParamAngleX']==0 for r in rows),'horizontal_face_motion_visible':max(r['mouthX'] for r in rows)-min(r['mouthX'] for r in rows)>.025,'vertical_face_motion_visible':max(r['mouthY'] for r in rows)-min(r['mouthY'] for r in rows)>.01}}
  await context.close();await page.video.save_as(str(ROOT/'artifacts/changzheng-idle-room.webm'));await browser.close()
  (ROOT/'artifacts/changzheng-idle-check.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));assert all(report['checks'].values())
asyncio.run(main())
