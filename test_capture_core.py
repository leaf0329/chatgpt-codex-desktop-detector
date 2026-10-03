import copy
import json
import unittest
from capture_core import Capture, SSE
from live_store import verdict


class Memory:
    def __init__(self):
        self.rows = {}

    def put(self, record):
        self.rows[record['id']] = copy.deepcopy(record)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.store = Memory()
        self.capture = Capture(self.store)

    def request(self, model='a', conn='socket'):
        self.capture.request(conn, {'type': 'response.create', 'model': model,
                                  'input': 'secret question', 'client_metadata': {'thread_id': 'thread-1'}}, 'websocket')

    def response(self, model=None, conn='socket', event='response.completed', rid='resp_1'):
        self.capture.response(conn, {'type': event, 'response': {'id': rid, 'model': model, 'output': 'private output'}})

    def test_pair_and_privacy(self):
        self.request()
        self.response('a', event='response.created')
        self.response('a')
        row = next(iter(self.store.rows.values()))
        self.assertEqual(verdict(row), '名称一致')
        self.assertEqual(row['thread_id'], 'thread-1')
        self.assertNotIn('secret', json.dumps(self.store.rows))
        self.assertNotIn('private output', json.dumps(self.store.rows))
        self.assertFalse(self.capture.records)

    def test_missing_mismatch_and_disconnect(self):
        self.request()
        self.response()
        self.assertEqual(verdict(list(self.store.rows.values())[-1]), '响应未提供模型')
        self.request()
        self.response('b')
        self.assertEqual(verdict(list(self.store.rows.values())[-1]), '名称不同')
        self.request()
        self.capture.fail('socket')
        self.assertEqual(verdict(list(self.store.rows.values())[-1]), '请求异常')

    def test_concurrent_connections_and_ambiguous(self):
        self.request('a', 'first')
        self.request('b', 'second')
        self.response('b', 'second')
        self.response('a', 'first')
        self.assertTrue(all(verdict(r) == '名称一致' for r in self.store.rows.values()))
        self.request('a', 'same')
        self.request('b', 'same')
        self.response('b', 'same')
        self.assertEqual(verdict(list(self.store.rows.values())[-1]), '配对不确定')

    def test_sse_split_multibyte_preserves_bytes(self):
        events, errors = [], []
        parser = SSE(events.append, lambda: errors.append(True))
        data = 'data: {"type":"response.completed","response":{"model":"a","output":"中文"}}\r\n\r\ndata: [DONE]\n\n'.encode()
        output = b''.join(parser.feed(data[i:i+1]) for i in range(len(data))) + parser.feed(b'')
        self.assertEqual(output, data)
        self.assertEqual(len(events), 1)
        self.assertFalse(errors)

    def test_incomplete_sse(self):
        errors = []
        parser = SSE(lambda _: None, lambda: errors.append(True))
        parser.feed(b'data: {')
        parser.feed(b'')
        self.assertTrue(errors)

    def test_warmup_is_not_request(self):
        self.capture.request('s', {'type':'response.create', 'model':'a', 'generate':False}, 'websocket')
        self.assertFalse(self.store.rows)
