"""Installed Electron acceptance against isolated backend; never daily data."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
import httpx
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:17862'


async def main():
    report = {'checks': {}}
    log = (ROOT / 'artifacts/runtime-v2d/electron.log').open('w')
    proc = subprocess.Popen([str(ROOT / 'node_modules/electron/dist/electron.exe'),
        '--remote-debugging-port=17864', str(ROOT)], cwd=ROOT,
        env={**os.environ, 'CHANGZHENG_URL': BASE}, stdout=log, stderr=log)
    async with httpx.AsyncClient(base_url=BASE, timeout=20) as client:
        try:
            await client.post('/api/settings', json={'voice': 'local:Microsoft Huihui Desktop', 'audio_enabled': True, 'auto_memory': False})
            for _ in range(100):
                try:
                    r = await client.get('http://127.0.0.1:17864/json/version')
                    if r.is_success: break
                except httpx.HTTPError: pass
                await asyncio.sleep(.1)
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp('http://127.0.0.1:17864')
                page = browser.contexts[0].pages[0]
                await page.wait_for_function("document.querySelector('#connection')?.textContent==='已连接'")
                report['electron'] = json.loads((ROOT / 'node_modules/electron/package.json').read_text())['version']
                await page.locator('#compact-button').click()
                await page.wait_for_function("document.body.classList.contains('compact')&&outerWidth<400")
                report['checks']['actual_electron_compact'] = await page.evaluate('outerWidth<400 && outerHeight<500')
                await page.screenshot(path=str(ROOT / 'artifacts/desktop-compact-v2.png'))
                await page.locator('#compact-expand').click()
                await page.wait_for_function('outerWidth>900')
                report['checks']['expanded_after_compact'] = True
                await page.locator('#message').fill('只回答一个字：好')
                await page.locator('#chat-form .send-button').click()
                for _ in range(300):
                    state = (await client.get('/api/state')).json()
                    if state['status'] == 'idle' and any(m['role'] == 'assistant' for m in state['history']): break
                    await asyncio.sleep(.1)
                report['checks']['real_electron_audio_confirmed'] = state['status'] == 'idle' and any(m['role'] == 'assistant' for m in state['history'])
                report['audio_metrics'] = state['metrics']

                # UI failure display/retry, using synthetic metadata only.
                pending = [{'status': 'failed'}, {'status': 'pending'}]
                requests = []
                async def jobs(route):
                    requests.append(time.monotonic())
                    await route.fulfill(json=pending)
                async def retry(route):
                    pending.clear()
                    await route.fulfill(json={'retried': 1})
                await page.route('**/api/memory-jobs', jobs)
                await page.route('**/api/memory-jobs/retry', retry)
                # Enable the display's retry control; no source messages enqueued.
                await client.post('/api/settings', json={'auto_memory': True})
                await page.reload()
                await page.wait_for_function("document.querySelector('#connection').textContent==='已连接'")
                await page.locator('[data-page=memories]').click()
                await page.wait_for_function("document.querySelector('#memory-job-status').textContent.includes('1 条整理失败')")
                report['checks']['memory_failure_visible'] = await page.locator('#retry-memory-jobs').is_visible()
                await page.locator('#retry-memory-jobs').click()
                await page.wait_for_function("document.querySelector('#memory-job-status').textContent==='记忆已保存在本机'")
                report['checks']['memory_retry_updates_status'] = not await page.locator('#retry-memory-jobs').is_visible()
                await page.screenshot(path=str(ROOT / 'artifacts/memory-page-v2.png'))
                await page.locator('[data-page=home]').click()
                calls = len(requests)
                await page.wait_for_timeout(3300)
                report['checks']['memory_poll_stops_when_page_hidden'] = len(requests) == calls
                await browser.close()

                preview = await p.chromium.launch(headless=True)
                stage = await preview.new_page(viewport={'width': 1920, 'height': 1080})
                await stage.goto(BASE + '/stage')
                await stage.frame_locator('iframe').locator('.pet').wait_for()
                await stage.screenshot(path=str(ROOT / 'artifacts/stream-stage.png'))
                report['checks']['stage_1920_preview'] = await stage.locator('h1').inner_text() == '小征的房间'
                report['checks']['stage_uses_observer_only'] = '/overlay' in stage.frames[1].url
                await preview.close()
        finally:
            if proc.poll() is None:
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait(10)
            log.close()
    (ROOT / 'artifacts/desktop-v2-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(report['checks'].values())


if __name__ == '__main__': asyncio.run(main())
