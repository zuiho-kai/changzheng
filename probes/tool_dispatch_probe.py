import asyncio
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from companion.store import Store
from companion.runtime import Runtime
from companion.providers import Provider
from companion.codex import CodexBridge


async def main():
    folder=ROOT/'artifacts/runtime-dispatch'; folder.mkdir(exist_ok=True)
    marker='FRESH-'+str(time.time_ns()); (folder/'fresh.txt').write_text(marker)
    store=Store(':memory:'); store.set_setting('cwd',str(folder)); store.set_setting('auto_memory',False)
    provider=Provider(); events=[]
    async def emit(event):
        events.append(event)
        if event['type']=='segment':await runtime.ack(event['turn_id'],event['id'])
    runtime=Runtime(store,provider,emit); bridge=CodexBridge(store,emit)
    async def dispatch(prompt,cwd):return await bridge.launch(prompt,cwd,read_only=True)
    runtime.dispatch_task=dispatch
    try:
        await runtime.new_session('work')
        await runtime.message('请调用Codex，只读查看工作目录中的fresh.txt。你现在不知道文件内容，必须执行读取后再报告。',voice=False)
        for _ in range(60):
            if store.tasks():break
            if any(e['type']=='turn_finished' for e in events):break
            await asyncio.sleep(.5)
        assert store.tasks(), 'Fast model did not dispatch a task: '+str([e for e in events if e['type'] in ('error','turn_finished')])
        print('Fast model called run_codex',flush=True)
        for _ in range(100):
            task=store.tasks()[0]
            if task['status'] in ('completed','failed'):break
            await asyncio.sleep(2)
        result={'fast_model_dispatched_codex':True,'real_fresh_file_read':task['status']=='completed' and marker in task['summary']}
        (ROOT/'artifacts/tool-dispatch-probe.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(result)
        assert all(result.values())
    finally:
        await runtime.close(); await bridge.close(); await provider.close(); store.close()


if __name__=='__main__':asyncio.run(main())
