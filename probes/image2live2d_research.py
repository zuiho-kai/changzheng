"""Load an independently generated MOC3 in our existing Cubism browser runtime.

Requires .reference/image2live2d-research and its generated sample under artifacts/runtime-image2live2d.
This tests separated synthetic layers, not single-image decomposition or production art quality.
"""
import asyncio
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'artifacts/runtime-image2live2d'


async def main():
    for name in ('pixi-6.5.10.min.js','live2dcubismcore.min.js','cubism4-0.4.0.min.js'):
        shutil.copy2(ROOT/'web/vendor'/name,FOLDER/name)
    (FOLDER/'index.html').write_text('''<!doctype html><html><body style="margin:0;background:#e9eedf">
<script src="pixi-6.5.10.min.js"></script><script src="live2dcubismcore.min.js"></script><script src="cubism4-0.4.0.min.js"></script>
<script>
(async()=>{try {
const app=new PIXI.Application({width:640,height:800,backgroundAlpha:0});document.body.append(app.view);
const model=await PIXI.live2d.Live2DModel.from('native-bundle/model.model3.json',{autoUpdate:false,autoInteract:false});
app.stage.addChild(model);app.ticker.stop();model.anchor.set(.5,1);model.scale.set(Math.min(620/model.width,780/model.height));model.position.set(320,790);
const core=model.internalModel.coreModel;
window.pose=value=>{core.setParameterValueById('ParamMouthOpenY',value);core.update();app.renderer.render(app.stage);return core.getParameterValueById('ParamMouthOpenY')};
window.modelStats={drawables:core._model.drawables.count,parameters:core._model.parameters.count};window.pose(0);document.body.dataset.ready='true';
}catch(e){document.body.dataset.error=String(e);}})();
</script></body></html>''',encoding='utf-8')
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(FOLDER)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    report={'source_commit':'b3fea7536f2d680897dbf5cce5a13046da75803c','input':'upstream generated separated sample layers, not a flat illustration','checks':{}}
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch()
            page=await browser.new_page(viewport={'width':640,'height':800})
            await page.goto(f'http://127.0.0.1:{server.server_port}/')
            await page.wait_for_function("document.body.dataset.ready||document.body.dataset.error",timeout=30000)
            error=await page.locator('body').get_attribute('data-error')
            report['error']=error
            report['checks']['loads_in_existing_cubism_core']=not error
            if not error:
                report['model']=await page.evaluate('modelStats')
                closed=await page.screenshot(path=str(ROOT/'artifacts/image2live2d-sample-closed.png'))
                report['mouth_parameter_value']=await page.evaluate('pose(1)')
                opened=await page.screenshot(path=str(ROOT/'artifacts/image2live2d-sample-open.png'))
                report['checks']['mouth_parameter_changes_render']=closed!=opened
            report['checks']['default_cli_has_no_moc3']=not list((FOLDER/'default-bundle').glob('*.moc3'))
            report['native_moc3_bytes']=(FOLDER/'native-bundle/model.moc3').stat().st_size
            await browser.close()
    finally:
        server.shutdown();server.server_close()
        (ROOT/'artifacts/image2live2d-research.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': asyncio.run(main())
