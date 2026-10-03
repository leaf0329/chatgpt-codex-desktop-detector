"""Offline end-to-end proxy test. Synthetic upstream, separate ports, temporary DB."""
import base64
import hashlib
import http.client
import json
import os
import socket
import ssl
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websocket
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent


def event(kind, model='test-model'):
    return {'type': kind, 'response': {'id': 'resp_test', 'model': model,
                                      'status': 'completed' if kind.endswith('completed') else 'in_progress',
                                      'output': 'PRIVATE_RESPONSE_SENTINEL'}}


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        assert json.loads(body)['input'] == 'PRIVATE_REQUEST_SENTINEL'
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for kind in ('response.created', 'response.completed'):
            self.wfile.write(('data: '+json.dumps(event(kind))+'\n\n').encode())
            self.wfile.flush()

    def do_GET(self):
        key = self.headers.get('Sec-WebSocket-Key')
        self.send_response(101)
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', base64.b64encode(hashlib.sha1(
            (key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode())
        self.end_headers()
        for _ in range(2):
            first = self.rfile.read(2)
            length = first[1] & 127
            if length == 126:
                length = struct.unpack('!H', self.rfile.read(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self.rfile.read(8))[0]
            mask = self.rfile.read(4)
            payload = self.rfile.read(length)
            request = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
            assert request['model'] == 'test-model'
            for kind in ('response.created', 'response.completed'):
                data = json.dumps(event(kind)).encode()
                self.wfile.write(b'\x81\x7e'+struct.pack('!H', len(data))+data)
                self.wfile.flush()


def main():
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    started = False
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'chatgpt.com')])
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1))
                    .not_valid_after(datetime.now(timezone.utc)+timedelta(days=1))
                    .add_extension(x509.SubjectAlternativeName([x509.DNSName('chatgpt.com')]), critical=False)
                    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                    .sign(key, hashes.SHA256()))
            cert_path, key_path = tmp / 'upstream.pem', tmp / 'upstream.key'
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert_path, key_path)
            upstream.socket = tls.wrap_socket(upstream.socket, server_side=True)
            threading.Thread(target=upstream.serve_forever, daemon=True).start()
            started = True
            hook = tmp / 'redirect.py'
            hook.write_text(f'def server_connect(data):\n    data.server.address = ("127.0.0.1", {upstream.server_port})')
            db = tmp / 'capture.sqlite'
            env = os.environ.copy()
            env['CODEX_MONITOR_DB'] = str(db)
            binary = Path(sys.executable).parent / ('mitmdump.exe' if os.name == 'nt' else 'mitmdump')
            proc = subprocess.Popen([str(binary), '-q', '-s', str(ROOT/'capture_addon.py'), '-s', str(hook),
                                     '--listen-host','127.0.0.1','--listen-port',str(port),
                                     '--set',f'confdir={tmp / "ca"}',
                                     '--set',f'ssl_verify_upstream_trusted_ca={cert_path}'], env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError('Test proxy exited')
                    try:
                        socket.create_connection(('127.0.0.1', port), .1).close()
                        break
                    except OSError:
                        time.sleep(.1)
                ca = tmp / 'ca' / 'mitmproxy-ca-cert.pem'
                client = http.client.HTTPSConnection('127.0.0.1',port,timeout=10,
                    context=ssl.create_default_context(cafile=str(ca)))
                client.set_tunnel('chatgpt.com', 443)
                request = {'model':'test-model','input':'PRIVATE_REQUEST_SENTINEL'}
                client.request('POST','/backend-api/codex/responses',json.dumps(request),{'Content-Type':'application/json'})
                response = client.getresponse()
                body = response.read()
                assert response.status == 200 and b'PRIVATE_RESPONSE_SENTINEL' in body
                client.close()
                ws = websocket.create_connection('wss://chatgpt.com/backend-api/codex/responses',
                    http_proxy_host='127.0.0.1', http_proxy_port=port, proxy_type='http', timeout=10,
                    sslopt={'ca_certs': str(ca), 'cert_reqs': ssl.CERT_REQUIRED})
                for _ in range(2):
                    ws.send(json.dumps({'type':'response.create',**request}))
                    assert json.loads(ws.recv())['type'] == 'response.created'
                    assert json.loads(ws.recv())['type'] == 'response.completed'
                ws.close()
                with sqlite3.connect(db) as conn:
                    rows = [json.loads(r[0]) for r in conn.execute('SELECT data FROM requests')]
                conn.close()
                assert len(rows) == 3, rows
                assert all(r['request_model'] == r['response_model'] == 'test-model' and r['status'] == 'completed' for r in rows), rows
                assert all('PRIVATE_' not in json.dumps(r) for r in rows)
                print('PASS: verified TLS chain, HTTPS SSE and two requests on one WSS connection; payload forwarded unchanged; metadata only persisted.')
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    finally:
        if started:
            upstream.shutdown()
        upstream.server_close()


if __name__ == '__main__':
    main()
