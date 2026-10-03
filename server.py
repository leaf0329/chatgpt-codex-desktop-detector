import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from detector import catalog, config, inspect
from response_evidence import parse_response


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin') != origin:
            self.send_error(403)
            return
        if self.path != '/api/response':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 5 * 1024 * 1024:
                raise ValueError('响应文件须小于 5 MB')
            evidence = parse_response(self.rfile.read(length).decode('utf-8-sig'))
            body = {'source': '用户导入响应文件（来源未经自动核验）', 'responses': evidence}
            code = 200
        except (ValueError, UnicodeError) as exc:
            body = {'error': str(exc)}
            code = 400
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        host = self.headers.get('Host', '')
        if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
            self.send_error(403)
            return
        request = urlparse(self.path)
        try:
            if request.path == '/':
                body = Path(__file__).with_name('index.html').read_bytes()
                mime = 'text/html; charset=utf-8'
            elif request.path == '/api/sessions':
                body = {'sessions': catalog(), 'config': config()}
                mime = 'application/json; charset=utf-8'
            elif request.path == '/api/inspect':
                query = parse_qs(request.query)
                body = inspect(query.get('key', [''])[0], query.get('target', [''])[0])
                mime = 'application/json; charset=utf-8'
            else:
                self.send_error(404)
                return
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        except (OSError, ValueError):
            self.send_error(400, 'Local record unavailable or invalid')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8900)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Codex Desktop Detector: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
