"""mitmproxy addon; forwards payload bytes unchanged and stores metadata only."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_core import Capture, SSE


class ModelMonitor:
    def __init__(self):
        self.capture = Capture()

    def selected(self, flow):
        return (flow.request.host in ('chatgpt.com', 'api.openai.com') and
                urlsplit(flow.request.url).path.rstrip('/') in ('/backend-api/codex/responses', '/v1/responses'))

    def request(self, flow):
        if not self.selected(flow) or flow.request.headers.get('upgrade', '').lower() == 'websocket':
            return
        try:
            self.capture.request(flow.id, json.loads(flow.request.content), 'http')
        except (ValueError, TypeError):
            pass

    def responseheaders(self, flow):
        if not self.selected(flow) or flow.response.status_code == 101:
            return
        if flow.response.status_code >= 400:
            self.capture.fail(flow.id, 'http_error')
        if 'text/event-stream' in flow.response.headers.get('content-type', ''):
            if flow.response.headers.get('content-encoding', 'identity') != 'identity':
                self.capture.fail(flow.id, 'parse_error')
                flow.response.stream = True
                return
            parser = SSE(lambda data: self.capture.response(flow.id, data),
                         lambda: self.capture.fail(flow.id, 'parse_error'))
            flow.response.stream = parser.feed

    def response(self, flow):
        if not self.selected(flow) or flow.response.status_code == 101:
            return
        if not flow.response.stream:
            try:
                self.capture.response(flow.id, json.loads(flow.response.get_text()))
            except (ValueError, TypeError):
                self.capture.fail(flow.id, 'parse_error')
        self.capture.fail(flow.id)

    def websocket_message(self, flow):
        if not self.selected(flow):
            return
        message = flow.websocket.messages[-1]
        try:
            data = json.loads(message.content)
            if message.from_client:
                self.capture.request(flow.id, data, 'websocket')
            else:
                self.capture.response(flow.id, data)
        except (ValueError, TypeError):
            self.capture.fail(flow.id, 'parse_error')
        # Only prior messages are discarded; the current message still forwards unchanged.
        del flow.websocket.messages[:-1]

    def websocket_end(self, flow):
        self.capture.fail(flow.id)

    def error(self, flow):
        self.capture.fail(flow.id)


addons = [ModelMonitor()]
