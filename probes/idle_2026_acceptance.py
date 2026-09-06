import asyncio,json,subprocess,imageio_ffmpeg
from pathlib import Path
from playwright.async_api import async_playwright
out=Path('artifacts/neuro-2026')
async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  ctx=await browser.new_context(viewport={'width':1280,'height':720},record_video_dir=str(out/'raw'),record_video_size={'width':1280,'height':720})
  page=await ctx.new_page(); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  await page.goto('http://127.0.0.1:17870/stage')
  body=page.frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]')
  await body.wait_for(timeout=60000)
  geometry=await body.evaluate('el=>({width:innerWidth,height:innerHeight,state:el.dataset.performance})')
  await asyncio.sleep(26)
  await page.screenshot(path=str(out/'loaded.png'))
  await ctx.close(); await page.video.save_as(str(out/'idle.webm'));await browser.close()
  print(json.dumps({'page_errors':errors,'geometry':geometry,'recorded_seconds':26}))
 ff=imageio_ffmpeg.get_ffmpeg_exe()
 subprocess.run([ff,'-y','-i',str(out/'idle.webm'),'-an','-c:v','libx264','-threads','2','-preset','ultrafast','-crf','21',str(out/'idle.mp4')],capture_output=True,check=True)
 subprocess.run([ff,'-y','-i',str(out/'idle.mp4'),'-vf','fps=2,scale=320:180,tile=5x5','-frames:v','1',str(out/'idle-contact.png')],capture_output=True,check=True)
asyncio.run(main())
