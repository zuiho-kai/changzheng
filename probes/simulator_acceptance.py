"""Exercise the offline rehearsal UI, never the production port."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path('artifacts/runtime-simulator')


async def main():
    report = {'origin': 'http://127.0.0.1:17874', 'errors': [], 'external_requests': []}
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=['--autoplay-policy=no-user-gesture-required',
            '--enable-unsafe-swiftshader'])
        page = await browser.new_page(viewport={'width': 1560, 'height': 1050})
        page.on('pageerror', lambda error: report['errors'].append(str(error)))
        page.on('request', lambda request: report['external_requests'].append(request.url)
            if request.url.startswith('http') and not request.url.startswith(report['origin'] + '/') else None)
        await page.add_init_script('''Object.defineProperty(window,'AvatarPerformance',{configurable:true,set(C){Object.defineProperty(window,'AvatarPerformance',{value:C});const update=C.prototype.update;C.prototype.update=function(...args){window.simPerformer=this;return update.apply(this,args)}}});''')
        await page.goto(report['origin'] + '/sim')
        body = page.frame_locator('#stage').frame_locator('#avatar').frame_locator('#live2d-frame').locator('body[data-ready=true]')
        await body.wait_for(timeout=60000)
        await asyncio.sleep(2)
        await page.locator('#text').fill('这条弹幕只在模拟器里出现')
        await page.get_by_role('button', name='发送到排练画面 ↗').click()
        await asyncio.sleep(2)
        report['chat_visible'] = await page.frame_locator('#stage').get_by_text('这条弹幕只在模拟器里出现', exact=True).count() == 1
        report['chat_notice'] = await body.evaluate('()=>Number.isFinite(window.simPerformer.noticeAt)')
        await page.get_by_role('button', name='倾听', exact=True).click()
        await asyncio.sleep(.4)
        report['listening'] = (await (await page.request.get(report['origin']+'/sim/status')).json())['status'] == 'listening'
        await page.get_by_role('button', name='好奇追问', exact=True).click()
        mouths = []
        for _ in range(16):
            mouths.append(float(await body.get_attribute('data-mouth')))
            await asyncio.sleep(.1)
        report['mouth_max'] = max(mouths)
        await page.get_by_role('button', name='■ 打断', exact=True).click()
        await asyncio.sleep(.4)
        report['mouth_after_stop'] = float(await body.get_attribute('data-mouth'))
        await page.get_by_role('button', name='录制 30 秒动作', exact=True).click()
        for _ in range(60):
            data = await (await page.request.get(report['origin']+'/sim/status')).json()
            if data['recording']['state'] in ('recording','error'):
                break
            await asyncio.sleep(.5)
        assert data['recording']['state'] == 'recording', data['recording']
        await page.get_by_role('button', name='▶ 30 秒自动排练', exact=True).click()
        await asyncio.sleep(12)
        await page.screenshot(path=str(OUT / 'simulator.png'))
        await asyncio.sleep(20)
        for _ in range(90):
            data = await (await page.request.get(report['origin']+'/sim/status')).json()
            if data['recording']['state'] in ('done','error'):
                break
            await asyncio.sleep(.5)
        report['recording'] = data['recording']
        report['scenario_complete'] = any(e['detail'] == '排练结束' for e in data['events'])
        report['playback_acks'] = sum(e['detail'] == '浏览器已确认播完' for e in data['events'])
        report['final_mouth'] = float(await body.get_attribute('data-mouth'))
        report['events'] = data['events']
        if data['recording']['state'] == 'done':
            result = await page.request.get(report['origin'] + data['recording']['url'])
            report['download_bytes'] = len(await result.body())
        await browser.close()
    (OUT / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False))
    assert not report['errors'] and not report['external_requests']
    assert report['chat_visible'] and report['chat_notice'] and report['listening']
    assert report['mouth_max'] > .1 and report['mouth_after_stop'] == 0 and report['final_mouth'] == 0
    assert report['scenario_complete'] and report['playback_acks'] >= 2
    assert report['download_bytes'] > 100000


asyncio.run(main())
