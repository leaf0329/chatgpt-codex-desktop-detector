"""Model metadata extraction and conservative request/response association."""
import json
import re
import time
import uuid
from collections import defaultdict

from live_store import Store


def token(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', value) else None


class Capture:
    def __init__(self, store=None):
        self.store = store if store is not None else Store()
        self.pending = defaultdict(list)
        self.responses = {}
        self.ignored_responses = set()
        self.records = {}

    def request(self, connection, data, transport):
        if not isinstance(data, dict):
            return
        if transport == 'websocket' and data.get('type') != 'response.create':
            return
        if data.get('generate') is False:
            self.pending[connection].append(None)
            return
        meta = data.get('client_metadata')
        meta = meta if isinstance(meta, dict) else {}
        reasoning = data.get('reasoning')
        reasoning = reasoning if isinstance(reasoning, dict) else {}
        record = {'id': str(uuid.uuid4()), 'started': time.time(), 'transport': transport,
                  'request_model': token(data.get('model')), 'response_model': None,
                  'response_id': None, 'thread_id': token(meta.get('thread_id')),
                  'turn_id': token(meta.get('turn_id')), 'effort': token(reasoning.get('effort')),
                  'status': 'pending', 'association': 'pending', 'usage': {}}
        self.pending[connection].append(record['id'])
        self.records[record['id']] = record
        self.store.put(record)

    def response(self, connection, data):
        if not isinstance(data, dict):
            return
        event = data.get('type')
        if event == 'error':
            self.fail(connection, 'failed')
            return
        if event not in ('response.created', 'response.in_progress', 'response.completed', 'response.failed', 'response.incomplete'):
            if data.get('object') != 'response':
                return
            response = data
        else:
            response = data.get('response')
        if not isinstance(response, dict):
            return
        rid = token(response.get('id'))
        pair = (connection, rid)
        terminal = response.get('status') in ('completed', 'failed', 'incomplete') or event in (
            'response.completed', 'response.failed', 'response.incomplete')
        if pair in self.ignored_responses:
            if terminal:
                self.ignored_responses.discard(pair)
            return
        record_id = self.responses.get(pair) if rid else None
        if not record_id:
            pending = self.pending.get(connection, [])
            if len(pending) == 1:
                record_id = pending.pop()
                if record_id is None:
                    if not terminal:
                        self.ignored_responses.add(pair)
                    return
                self.records[record_id]['association'] = 'single_pending_request'
            else:
                record_id = str(uuid.uuid4())
                self.records[record_id] = {'id': record_id, 'started': time.time(), 'transport': 'unknown',
                                           'request_model': None, 'response_model': None,
                                           'association': 'uncertain', 'usage': {}}
            if rid:
                self.responses[pair] = record_id
        record = self.records[record_id]
        record['response_id'] = rid
        model = token(response.get('model'))
        if model:
            record['response_model'] = model
        status = response.get('status') or (event or '').removeprefix('response.')
        record['status'] = status if status in ('completed', 'failed', 'incomplete') else 'in_progress'
        usage = response.get('usage')
        if isinstance(usage, dict):
            record['usage'] = {k: v for k, v in usage.items()
                               if k in ('input_tokens', 'output_tokens', 'total_tokens') and type(v) is int and v >= 0}
        self.store.put(record)
        if record['status'] in ('completed', 'failed', 'incomplete'):
            self.responses.pop(pair, None)
            self.records.pop(record_id, None)

    def fail(self, connection, status='disconnected'):
        ids = set(self.pending.pop(connection, []))
        self.ignored_responses = {pair for pair in self.ignored_responses if pair[0] != connection}
        for pair in list(self.responses):
            if pair[0] == connection:
                ids.add(self.responses.pop(pair))
        for record_id in ids:
            record = self.records.pop(record_id, None)
            if record:
                record['status'] = status
                self.store.put(record)


class SSE:
    def __init__(self, callback, on_error):
        self.buffer = b''
        self.callback = callback
        self.on_error = on_error

    def feed(self, chunk):
        self.buffer += chunk
        if len(self.buffer) > 8 * 1024 * 1024:
            self.buffer = b''
            self.on_error()
            return chunk
        while True:
            match = re.search(b'\r?\n\r?\n', self.buffer)
            if not match:
                break
            frame, self.buffer = self.buffer[:match.start()], self.buffer[match.end():]
            data = b'\n'.join(line[5:].lstrip() for line in frame.splitlines() if line.startswith(b'data:'))
            if data and data != b'[DONE]':
                try:
                    self.callback(json.loads(data))
                except (ValueError, UnicodeError):
                    self.on_error()
        if not chunk and self.buffer.strip():
            self.on_error()
            self.buffer = b''
        return chunk
