"""Read-only local comparison of the supplied VTube Studio model and our rig."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(r'G:\SteamLibrary\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\2000_vts')


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = unquote(urlsplit(path).path)
        if path.startswith('/reference/'):
            base, relative = REFERENCE, path.removeprefix('/reference/')
        elif path.startswith('/static/'):
            base, relative = ROOT / 'web', path.removeprefix('/static/')
        elif path == '/':
            base, relative = ROOT / 'web', 'reference-review.html'
        else:
            return str(ROOT / 'artifacts/runtime-reference-rig/not-found')
        target = (base / relative).resolve()
        return str(target if target.is_relative_to(base.resolve()) else ROOT / 'artifacts/runtime-reference-rig/not-found')

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=17871)
    args = parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
