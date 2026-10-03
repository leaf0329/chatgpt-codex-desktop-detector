import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from response_evidence import communication, parse_response


class ResponseEvidenceTests(unittest.TestCase):
    def test_actual_body_whitelist(self):
        result = parse_response(json.dumps({'type': 'response.completed', 'response': {
            'id': 'resp_123', 'model': 'model-a', 'status': 'completed',
            'output': [{'text': 'private text'}], 'usage': {'input_tokens': 5}}}))
        self.assertEqual(result[0]['model'], 'model-a')
        self.assertNotIn('private text', json.dumps(result))

    def test_request_is_not_response(self):
        for obj in [{'model': 'model-a'}, {'type': 'response.create', 'model': 'model-a'},
                    {'type': 'turn_context', 'payload': {'model': 'model-a'}}]:
            with self.assertRaises(ValueError):
                parse_response(json.dumps(obj))

    def test_sse_and_missing_model(self):
        result = parse_response('data: {"type":"response.created","response":{"id":"resp_a"}}\n\ndata: [DONE]\n\n')
        self.assertIsNone(result[0]['model'])
        with self.assertRaises(ValueError):
            parse_response('data: {bad}\n\n')

    def test_thread_filter_and_no_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            with sqlite3.connect(home / 'logs_2.sqlite') as db:
                db.execute('create table logs(id integer, ts integer, target text, feedback_log_body text, thread_id text)')
                db.execute('insert into logs values(1,1,?,?,?)',
                           ('codex_api::endpoint::responses_websocket',
                            'model=requested headers={"upgrade": "websocket", "set-cookie": "secret", "openai-model":"reported"}', 'mine'))
                db.execute('insert into logs values(2,1,?,?,?)',
                           ('codex_core::responses_retry', 'stream disconnected - retrying', 'other'))
            db.close()
            result = communication('mine', home)
            self.assertEqual(result['handshakes'][0]['headers']['openai-model'], 'reported')
            self.assertEqual(result['retries'], [])
            self.assertNotIn('secret', json.dumps(result))
            self.assertNotIn('requested', json.dumps(result))
