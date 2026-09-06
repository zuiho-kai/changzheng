"""Exercise visible expressions, gestures and the production avatar message bridge."""
import asyncio
import io
import json
from pathlib import Path
import threading
from http.server import ThreadingHTTPServer

from PIL import Image
from playwright.async_api import async_playwright
from reference_rig import Handler

ROOT = Path(__file__).resolve().parents[1]
SOFTWARE = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader']


async def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    report = {'checks': {}, 'errors': [], 'renderer': 'ANGLE SwiftShader'}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=SOFTWARE)
            page = await browser.new_page(viewport={'width': 1220, 'height': 1030})
            page.on('pageerror', lambda e: report['errors'].append(str(e)))
            await page.goto(base)
            await page.wait_for_function('window.reviewReady', timeout=60000)
            await page.evaluate('performanceReview.entries.forEach(e=>e.performer.nextBlink=performance.now()+60000)')
            snapshots = {}
            for name in ['auto', 'happy', 'curious', 'surprised', 'serious']:
                await page.locator(f'button[data-expression="{name}"]').click()
                await page.wait_for_timeout(850)
                shot = await page.screenshot(path=str(ROOT / f'artifacts/expression-{name}.png'))
                snapshots[name] = await page.evaluate('performanceReview.entries[1].values')
                pixels = Image.open(io.BytesIO(shot)).convert('RGB').crop((660, 170, 1160, 650))
                report['checks'][name + '_visible'] = sum(max(p) < 160 for p in pixels.get_flattened_data()) > 1500
            report['checks']['happy_closes_smile_eyes'] = snapshots['happy']['ParamEyeLOpen'] < .03 and snapshots['happy']['ParamEyeLSmile'] > .95
            report['checks']['surprise_uses_dedicated_art'] = snapshots['surprised']['ParamSurprised'] > .95
            report['checks']['all_expressions_keep_yaw_zero'] = all(v['ParamAngleX'] == 0 for v in snapshots.values())
            await page.locator('#stop').click()
            await page.wait_for_timeout(700)
            for name, parameter in [('nod', 'ParamAngleY'), ('tilt', 'ParamAngleZ')]:
                await page.locator(f'button[data-gesture="{name}"]').click()
                await page.wait_for_timeout(280)
                value = await page.evaluate(f'performanceReview.entries[1].values.{parameter}')
                report['checks'][name + '_moves_model'] = abs(value) > 4
                await page.wait_for_timeout(1800)
                report['checks'][name + '_returns_to_idle_motion'] = await page.evaluate('performanceReview.entries[1].performer.action===null')
            await page.locator('button[data-gesture="wink"]').click()
            await page.wait_for_function('performanceReview.entries[1].values.ParamEyeLOpen<.15 && performanceReview.entries[1].values.ParamEyeROpen>.85', timeout=2000)
            wink = await page.evaluate('performanceReview.entries[1].values')
            report['checks']['wink_independent_eyes'] = wink['ParamEyeLOpen'] < .15 and wink['ParamEyeROpen'] > .85
            report['checks']['review_context_valid'] = not await page.evaluate('document.querySelector("canvas").getContext("webgl2").isContextLost()')
            await page.goto(base + '/static/live2d.html?model=changzheng&framing=portrait')
            await page.locator('body[data-ready=true]').wait_for(timeout=60000)
            for state in ['listening', 'thinking', 'speaking', 'idle']:
                await page.evaluate('state=>postMessage({type:"performance",state},location.origin)', state)
                await page.locator(f'body[data-performance="{state}"]').wait_for()
                await page.wait_for_timeout(600)
                report['checks']['production_' + state] = await page.locator('body').get_attribute('data-yaw') == '0'
                if state in ['listening', 'thinking']:
                    await page.screenshot(path=str(ROOT / f'artifacts/expression-state-{state}.png'))
            await page.evaluate('postMessage({type:"mouth",value:.8},location.origin)')
            await page.wait_for_function('Number(document.body.dataset.mouth)>.2')
            await page.evaluate('postMessage({type:"performance",state:"idle",reset:true},location.origin)')
            await page.locator('body[data-mouth="0"]').wait_for()
            report['checks']['production_reset_closes_mouth'] = True
            await page.evaluate('postMessage({type:"mouth",value:.8},location.origin)')
            await page.wait_for_timeout(400)
            report['checks']['stale_audio_closes_mouth'] = await page.locator('body').get_attribute('data-mouth') == '0'
            await page.close()
            context = await browser.new_context(viewport={'width':1220,'height':1030}, record_video_dir=str(ROOT/'artifacts/runtime-expression-rig/video'), record_video_size={'width':1220,'height':1030})
            page = await context.new_page()
            await page.goto(base)
            await page.wait_for_function('window.reviewReady', timeout=60000)
            await page.locator('#demo').click()
            await page.wait_for_timeout(18500)
            await page.locator('#stop').click()
            await page.wait_for_timeout(650)
            report['checks']['recording_context_valid'] = not await page.evaluate('document.querySelector("canvas").getContext("webgl2").isContextLost()')
            await context.close()
            await page.video.save_as(str(ROOT/'artifacts/changzheng-expression-demo.webm'))
            await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (ROOT/'artifacts/changzheng-expression-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not report['errors'] and all(report['checks'].values())


if __name__ == '__main__':
    asyncio.run(main())
