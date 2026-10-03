"""mitmproxy addon; forwards payload bytes unchanged and stores metadata only."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_core import Capture, SSE


class ModelMonitor:
    def __init__(self):
        self.capture = Capture()

    def observe(self, method, *args):
        try:
            method(*args)
        except Exception:
            # Diagnostics must never abort the user's response stream.
            try:
                (Path(__file__).resolve().parent / '.local' / 'capture-error.json').write_text(
                    '{"error":"metadata_capture_failed"}', encoding='utf-8')
            except OSError:
                pass

    def selected(self, flow):
        return (flow.request.pretty_host in ('chatgpt.com', 'api.openai.com') and
                flow.request.path.split('?', 1)[0].rstrip('/') in ('/backend-api/codex/responses', '/v1/responses'))

    def request(self, flow):
        if not self.selected(flow) or flow.request.headers.get('upgrade', '').lower() == 'websocket':
            return
        try:
            self.observe(self.capture.request, flow.id, json.loads(flow.request.content), 'http')
        except (ValueError, TypeError):
            pass

    def responseheaders(self, flow):
        if not self.selected(flow) or flow.response.status_code == 101:
            return
        if flow.response.status_code >= 400:
            self.observe(self.capture.fail, flow.id, 'http_error')
        if 'text/event-stream' in flow.response.headers.get('content-type', ''):
            if flow.response.headers.get('content-encoding', 'identity') != 'identity':
                self.observe(self.capture.fail, flow.id, 'parse_error')
                flow.response.stream = True
                return
            parser = SSE(lambda data: self.observe(self.capture.response, flow.id, data),
                         lambda: self.observe(self.capture.fail, flow.id, 'parse_error'))
            flow.response.stream = parser.feed

    def response(self, flow):
        if not self.selected(flow) or flow.response.status_code == 101:
            return
        if not flow.response.stream:
            try:
                self.observe(self.capture.response, flow.id, json.loads(flow.response.get_text()))
            except (ValueError, TypeError):
                self.observe(self.capture.fail, flow.id, 'parse_error')
        self.observe(self.capture.fail, flow.id)

    def websocket_message(self, flow):
        if not self.selected(flow):
            return
        message = flow.websocket.messages[-1]
        try:
            data = json.loads(message.content)
            if message.from_client:
                self.observe(self.capture.request, flow.id, data, 'websocket')
            else:
                self.observe(self.capture.response, flow.id, data)
        except (ValueError, TypeError):
            self.observe(self.capture.fail, flow.id, 'parse_error')
        # Only prior messages are discarded; the current message still forwards unchanged.
        del flow.websocket.messages[:-1]

    def websocket_end(self, flow):
        self.observe(self.capture.fail, flow.id)

    def error(self, flow):
        self.observe(self.capture.fail, flow.id)


addons = [ModelMonitor()]
