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
    if record.get('association') == 'uncertain':
        return '配对不确定'
    if record.get('response_model') and record.get('request_model'):
        return '名称一致' if record['response_model'] == record['request_model'] else '名称不同'
    if record.get('status') in ('completed', 'failed', 'incomplete', 'disconnected', 'http_error', 'parse_error'):
        return '响应未提供模型'
    return '等待响应'


REQUEST_STATES = {
    'pending': ('等待响应', '已观察到请求，尚未取得响应。'),
    'in_progress': ('响应中', '已观察到响应，尚未取得完成事件。'),
    'completed': ('已完成', '已观察到响应完成事件。'),
    'failed': ('服务端报错', '收到服务端错误或失败状态；不代表模型名称不一致。'),
    'incomplete': ('响应未完成', '服务端声明响应未完成，具体原因未采集。'),
    'disconnected': ('连接中断', '连接结束时尚未采集到完成事件；可能断线、取消或重试，不能确认具体原因。'),
    'http_error': ('HTTP 错误', '收到 HTTP 错误状态，无法据此判断模型降级。'),
    'parse_error': ('采集解析异常', '采集器无法解析响应；不代表 Codex 请求一定失败。'),
}


def request_state(record):
    return REQUEST_STATES.get(record.get('status'), ('状态未知', '未识别的请求状态。'))[0]


def request_detail(record):
    return REQUEST_STATES.get(record.get('status'), ('状态未知', '未识别的请求状态。'))[1]
