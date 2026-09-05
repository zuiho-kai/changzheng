"""Independent local preview; does not stop or modify the daily instance."""
import os
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from companion.secrets import get_key
from companion.store import Store

os.environ['SILICONFLOW_API_KEY'] = get_key()
parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=17868)
parser.add_argument('--reload', action='store_true')
args = parser.parse_args()
folder = ROOT / 'artifacts' / ('runtime-live2d-preview' if args.port == 17868 else f'runtime-live2d-preview-{args.port}')
folder.mkdir(parents=True, exist_ok=True)
os.environ['CHANGZHENG_DATA_DIR'] = str(folder)
store = Store(folder / 'companion.db')
store.set_setting('avatar', 'live2d:hiyori')
store.set_setting('auto_memory', False)
store.set_setting('voice', 'local:Microsoft Huihui Desktop')
store.conn.close()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('companion.app:app', host='127.0.0.1', port=args.port, access_log=False,
                reload=args.reload, reload_dirs=[str(ROOT / 'companion')] if args.reload else None)
