import asyncio,json,threading
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.async_api import async_playwright
from reference_rig import Handler,ROOT
OUT=ROOT/'artifacts/attention-review';OUT.mkdir(exist_ok=True)
class Candidate(Handler):
 def translate_path(self,path):
  prefix='/static/models/changzheng/'
  if urlsplit(path).path.startswith(prefix):return str(ROOT/'artifacts/runtime-expression-rig/bundle'/urlsplit(path).path[len(prefix):])
  return super().translate_path(path)
async def main():
 server=ThreadingHTTPServer(('127.0.0.1',0),Candidate);threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  async with async_playwright() as p:
   browser=await p.chromium.launch(args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
   page=await browser.new_page(viewport={'width':900,'height':900})
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   await page.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C});const f=C.prototype.update;C.prototype.update=function(t,m){window.performer=this;const result=f.call(this,t,m);window.values=result;return result;};}});''')
   await page.goto(f'http://127.0.0.1:{server.server_port}/static/live2d.html?model=changzheng&framing=portrait')
   await page.locator('body[data-ready=true]').wait_for(timeout=60000)
   await page.wait_for_function('window.performer && window.values')
   await page.evaluate('''()=>{performer.nextHop=performer.nextPose=performer.nextBlink=Infinity;performer.poseTarget={head:0,body:0,pitch:0};performer.action=null;performer.look(0,0,60000)}''')
   shots={}
   for name,x,y in [('center',0,0),('left',-.9,0),('right',.9,0),('up',0,.8),('down',0,-.8)]:
    await page.evaluate('a=>performer.look(a[0],a[1],60000)',[x,y]);await asyncio.sleep(.45)
    await page.screenshot(path=str(OUT/f'{name}.png'))
    shots[name]=await page.evaluate('''()=>({gaze:[values.ParamEyeBallX,values.ParamEyeBallY],params:performer.core._model.parameters.ids,vertices:Array.from(performer.core._model.drawables.vertexPositions[3])})''')
   await page.evaluate("()=>{performer.setExpression('happy');performer.look(.9,0,60000)}");await asyncio.sleep(.65);await page.screenshot(path=str(OUT/'closed.png'))
   closed=await page.evaluate('()=>values.ParamEyeLOpen')
   drift=await page.evaluate('''()=>{const core=performer.core;core.update();const before=Array.from(core._model.drawables.vertexPositions[3]);for(let i=0;i<200;i++)core.update();return Math.max(...before.map((v,i)=>Math.abs(v-core._model.drawables.vertexPositions[3][i])))}''')
   await browser.close()
   report={'errors':errors,'gaze':{k:v['gaze'] for k,v in shots.items()},'params':shots['center']['params'],'blink_eye_open':closed,'held_pose_vertex_drift':drift,'eye_vertices_change':shots['left']['vertices']!=shots['right']['vertices']}
   (OUT/'checks.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))
   assert not errors and drift<1e-6 and closed<.01 and report['eye_vertices_change']
 finally:server.shutdown();server.server_close()
asyncio.run(main())
