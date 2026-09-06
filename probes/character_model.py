"""Render a generated character bundle and exercise mouth, eyes and head independently."""
import asyncio
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / os.environ.get('CHANGZHENG_MODEL_WORK', 'artifacts/runtime-changzheng-model')
PREFIX = os.environ.get('CHANGZHENG_MODEL_PREFIX', 'changzheng')


async def main():
    for name in ('pixi-6.5.10.min.js', 'live2dcubismcore.min.js', 'cubism4-0.4.0.min.js'):
        shutil.copy2(ROOT / 'web/vendor' / name, FOLDER / name)
    (FOLDER / 'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>长征酱 · 模型验收</title>
<body style="margin:0;background:#edf0e7"><script src="pixi-6.5.10.min.js"></script>
<script src="live2dcubismcore.min.js"></script><script src="cubism4-0.4.0.min.js"></script><script>
(async()=>{try {
const app=new PIXI.Application({width:768,height:1024,backgroundAlpha:0,antialias:true});document.body.append(app.view);
const model=await PIXI.live2d.Live2DModel.from('bundle/model.model3.json',{autoUpdate:false,autoInteract:false});
app.stage.addChild(model);app.ticker.stop();model.anchor.set(.5,1);model.scale.set(Math.min(740/model.width,1000/model.height));model.position.set(384,1010);
const core=model.internalModel.coreModel;
window.pose=values=>{for(const [id,value] of Object.entries(values))core.setParameterValueById(id,value);core.update();app.renderer.render(app.stage);};
window.stats={drawables:core._model.drawables.count,parameters:core._model.parameters.count};
window.pose({ParamMouthOpenY:0,ParamEyeLOpen:1,ParamEyeROpen:1});document.body.dataset.ready='true';
}catch(e){document.body.dataset.error=String(e);}})();</script>''', encoding='utf-8')
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(FOLDER)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {'checks': {}, 'errors': []}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={'width': 768, 'height': 1024})
            page.on('pageerror', lambda error: report['errors'].append(str(error)))
            await page.goto(f'http://127.0.0.1:{server.server_port}/')
            await page.wait_for_function('document.body.dataset.ready||document.body.dataset.error', timeout=60000)
            report['load_error'] = await page.locator('body').get_attribute('data-error')
            if report['load_error']:
                raise RuntimeError(report['load_error'])
            report['model'] = await page.evaluate('stats')
            neutral = await page.screenshot(path=str(ROOT / f'artifacts/{PREFIX}-neutral.png'))
            for name, values in [('mouth', {'ParamMouthOpenY': 1}), ('blink', {'ParamMouthOpenY': 0, 'ParamEyeLOpen': 0, 'ParamEyeROpen': 0}), ('head', {'ParamEyeLOpen': 1, 'ParamEyeROpen': 1, 'ParamAngleX': 15})]:
                await page.evaluate('v=>pose(v)', values)
                shot = await page.screenshot(path=str(ROOT / f'artifacts/{PREFIX}-{name}.png'))
                report['checks'][name + '_changes_render'] = shot != neutral
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (ROOT / f'artifacts/{PREFIX}-model-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
