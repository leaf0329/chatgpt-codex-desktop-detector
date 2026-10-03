"""Whitelist-only extraction of transport metadata and supplied response bodies."""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

HEADERS = {'openai-model', 'x-request-id', 'content-type', 'upgrade', 'date'}
TARGETS = ('codex_api::endpoint::responses_websocket', 'codex_core::responses_retry')


def parse_response(text):
    """Accept a Responses JSON envelope or SSE stream, never interpret request model fields."""
    objects = []
    try:
        objects.append(json.loads(text))
    except ValueError:
        chunks = re.split(r'\r?\n\r?\n', text.strip())
        for chunk in chunks:
            data = '\n'.join(line[5:].lstrip() for line in chunk.splitlines() if line.startswith('data:'))
            if not data or data == '[DONE]':
                continue
            try:
                objects.append(json.loads(data))
            except ValueError:
                raise ValueError('SSE 数据不完整或不是有效 JSON')
    results = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        kind = obj.get('type')
        if kind in {'response.created', 'response.in_progress', 'response.completed', 'response.failed', 'response.incomplete'}:
            response = obj.get('response')
        elif obj.get('object') == 'response':
            response = obj
        else:
            continue
        if not isinstance(response, dict):
            continue
        result = {'event': kind or 'response', 'response_id': safe(response.get('id')),
                  'model': safe(response.get('model')), 'status': safe(response.get('status')),
                  'usage': {}}
        usage = response.get('usage')
        if isinstance(usage, dict):
            for key in ('input_tokens', 'output_tokens', 'total_tokens'):
                value = usage.get(key)
                if type(value) is int and value >= 0:
                    result['usage'][key] = value
        results.append(result)
    if not results:
        raise ValueError('没有发现 Responses 响应对象；请求体和本地 turn_context 不作为响应证据')
    return results


def safe(value):
    return value if isinstance(value, str) and len(value) <= 200 and re.fullmatch(r'[a-zA-Z0-9_.:/ -]+', value) else None


def communication(thread_id, home):
    path = home / 'logs_2.sqlite'
    result = {'available': False, 'source': str(path), 'handshakes': [], 'retries': [],
              'response_bodies': [], 'body_status': 'not_observed', 'error': None,
              'scope': '最近 500 条所选任务的通信模块日志；握手头不等于逐请求响应体'}
    if not thread_id or not path.is_file():
        result['error'] = '没有找到该任务可用的通信诊断数据库'
        return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            db.execute('PRAGMA query_only=ON')
            rows = db.execute('SELECT id, ts, target, feedback_log_body FROM logs '
                              'WHERE thread_id=? AND target IN (?, ?) ORDER BY id DESC LIMIT 500',
                              (thread_id, *TARGETS)).fetchall()
        result['available'] = True
        for row_id, timestamp, target, body in rows:
            body = body or ''
            base = {'row_id': row_id, 'timestamp': datetime.fromtimestamp(timestamp, timezone.utc).isoformat()}
            if target == 'codex_core::responses_retry' and 'stream disconnected - retrying' in body:
                result['retries'].append({**base, 'type': 'stream_disconnected_retry'})
            elif target == TARGETS[0] and 'headers' in body:
                # Match only explicitly allowed header names; cookies and authorization never leave this module.
                selected = {}
                for key in HEADERS:
                    match = re.search(r'"' + re.escape(key) + r'":\s*("(?:\\.|[^"\\])*")', body)
                    if match:
                        try:
                            value = json.loads(match.group(1))
                            if isinstance(value, str) and len(value) <= 200:
                                selected[key] = value
                        except ValueError:
                            pass
                if selected:
                    result['handshakes'].append({**base, 'headers': selected})
    except (sqlite3.Error, OSError, ValueError):
        result['error'] = '诊断数据库不可读或结构不兼容；未读取通信证据'
    return result
