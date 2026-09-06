"""Visual/component checks: /stage stays an observer; fixture comments are not sent to live."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts'
BASE = 'http://127.0.0.1:17870'

async def main():
    report = {'checks': {}, 'errors': [], 'fixture_note': 'Screenshots ending fixture use local route-mocked chat and caption DOM. No live messages or audio were submitted.'}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})
        page.on('pageerror', lambda e: report['errors'].append(str(e)))
        await page.goto(BASE + '/stage')
        model = page.frame_locator('#avatar').frame_locator('#live2d-frame')
        await model.locator('body[data-ready=true]').wait_for(timeout=60000)
        await page.wait_for_timeout(1200)
        await page.screenshot(path=str(OUT / 'stage-upgrade-1280-live.png'))
        report['checks']['observer_iframe'] = await page.locator('#avatar').get_attribute('src') == '/overlay'
        report['checks']['actual_model_ready'] = True
        report['live_label'] = await page.locator('.label').inner_text()
        fixture = {'connected': True, 'scene': 'live', 'player_connected': True, 'audio_enabled': True, 'audio_state': 'running', 'status': 'speaking', 'received': 5, 'messages': [
            {'user': '橘子汽水', 'text': '新来的，小征今天在聊什么呀？'},
            {'user': '晚风', 'text': '刚下班就赶上了，好耶'},
            {'user': '半糖', 'text': '你是不是又在偷偷看弹幕哈哈哈哈'},
            {'user': '路过的小猫', 'text': '给你出道题：奶茶和可乐选哪个？'},
            {'user': '今天也要早睡', 'text': '这表情一看就没憋什么好话'}], 'attention': [{'user': '路过的小猫', 'text': '奶茶和可乐选哪个？'}, {'user': '今天也要早睡', 'text': '这表情一看就没憋什么好话'}]}
        async def status_route(route):
            await route.fulfill(json=fixture)
        await page.route('**/api/live/status', status_route)
        await page.wait_for_function("document.querySelectorAll('.chat-row').length===5")
        bubble = page.frame_locator('#avatar').locator('.speech-bubble')
        await bubble.evaluate("el=>{el.hidden=false;el.textContent='不是，选奶茶还是可乐？小孩子才做选择——我先看看谁请客。';}")
        await page.wait_for_timeout(350)
        await page.screenshot(path=str(OUT / 'stage-upgrade-1280-fixture.png'))
        report['checks']['caption_matches_confirmed_source'] = await page.locator('#caption').text_content() == await bubble.text_content()
        report['checks']['attention_is_group_context'] = (await page.locator('#reply-context').inner_text()).startswith('这轮在聊 · ') and '路过的小猫' not in await page.locator('#reply-context').inner_text()
        await page.evaluate("window.keptChatRow=document.querySelectorAll('.chat-row')[1]")
        fixture['messages'].append({'user': '奶茶续杯', 'text': '被你发现了，今天可没有人请客！'})
        await page.wait_for_function("document.querySelector('.chat-row:last-child').textContent.includes('奶茶续杯')")
        report['checks']['existing_rows_keep_dom_identity'] = await page.evaluate("document.querySelector('.chat-row')===window.keptChatRow")
        report['checks']['only_five_rows'] = await page.locator('.chat-row').count() == 5
        await page.set_viewport_size({'width': 1920, 'height': 1080})
        await page.wait_for_timeout(750)
        await page.screenshot(path=str(OUT / 'stage-upgrade-1920-fixture.png'))
        report['checks']['chat_within_canvas'] = await page.locator('.paper').evaluate("e=>{const r=e.getBoundingClientRect();return r.right<=innerWidth && r.bottom<=innerHeight;}")
        fixture['status'] = 'idle'
        fixture['attention'] = []
        await page.wait_for_function("document.querySelector('#reply-context').hidden")
        report['checks']['idle_hides_attention'] = True
        await bubble.evaluate("el=>{el.hidden=true;}")
        await page.wait_for_function("!document.querySelector('#caption').textContent")
        report['checks']['hidden_source_clears_caption'] = True
        await page.close()
        # Isolated synthetic iframe: this page must never connect a second audio owner.
        errorpage = await browser.new_page(viewport={'width': 1280, 'height': 720})
        await errorpage.route('**/?broadcast=1', lambda route: route.fulfill(content_type='text/html', body='<html><head></head><body><div class="speech-bubble" hidden></div></body></html>'))
        await errorpage.route('**/api/live/status', status_route)
        await errorpage.goto(BASE + '/stage?audio=1')
        await errorpage.wait_for_timeout(1200)
        iframe = errorpage.frame_locator('#avatar')
        await iframe.locator('body').evaluate("()=>parent.postMessage({type:'broadcast-error',message:'fixture audio failed'},location.origin)")
        await errorpage.wait_for_timeout(2200)
        report['checks']['audio_error_survives_status_refresh'] = '声音未就绪' in await errorpage.locator('.label').inner_text()
        await iframe.locator('body').evaluate("()=>parent.postMessage({type:'broadcast-state',connected:true,audio:'running'},location.origin)")
        await errorpage.wait_for_timeout(150)
        report['checks']['audio_error_clears_after_recovery'] = '声音未就绪' not in await errorpage.locator('.label').inner_text()
        await browser.close()
    (OUT / 'stage-upgrade-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(report['checks'].values()) and not report['errors']

asyncio.run(main())
