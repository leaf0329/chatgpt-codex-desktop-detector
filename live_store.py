"""Bounded metadata journal. No headers, prompts, output text or credentials."""
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PATH = Path(os.environ.get('CODEX_MONITOR_DB', Path(__file__).resolve().parent / '.local' / 'live.sqlite'))


class Store:
    def __init__(self, path=PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, updated REAL, data TEXT)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=3)

    def put(self, record):
        record['updated'] = time.time()
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO requests VALUES(?,?,?)',
                       (record['id'], record['updated'], json.dumps(record, ensure_ascii=False)))
            db.execute('DELETE FROM requests WHERE id NOT IN (SELECT id FROM requests ORDER BY updated DESC LIMIT 1000)')

    def recent(self, limit=30):
        with closing(self.connect()) as db:
            return [json.loads(row[0]) for row in db.execute(
                'SELECT data FROM requests ORDER BY updated DESC LIMIT ?', (limit,))]


def verdict(record):
    if record.get('status') in ('failed', 'incomplete', 'disconnected', 'http_error', 'parse_error'):
        return '请求异常'
    if record.get('association') == 'uncertain':
        return '配对不确定'
    if record.get('response_model') and record.get('request_model'):
        return '名称一致' if record['response_model'] == record['request_model'] else '名称不同'
    if record.get('status') == 'completed':
        return '响应未提供模型'
    return '等待响应'
