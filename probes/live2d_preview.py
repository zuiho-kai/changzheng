"""Independent local preview; does not stop or modify the daily instance."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion.secrets import get_key
from companion.store import Store

os.environ['SILICONFLOW_API_KEY'] = get_key()
folder = ROOT / 'artifacts/runtime-live2d-preview'
folder.mkdir(parents=True, exist_ok=True)
os.environ['CHANGZHENG_DATA_DIR'] = str(folder)
store = Store(folder / 'companion.db')
store.set_setting('avatar', 'live2d:hiyori')
store.set_setting('auto_memory', False)
store.set_setting('voice', 'local:Microsoft Huihui Desktop')
store.conn.close()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('companion.app:app', host='127.0.0.1', port=17868, access_log=False)
